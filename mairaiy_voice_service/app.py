from __future__ import annotations

import asyncio
import io
import os
import re
import secrets
import urllib.request
from pathlib import Path
from typing import Literal

import numpy as np
import soundfile as sf
from fastapi import Depends, FastAPI, Header, HTTPException
from fastapi.responses import Response
from kokoro_onnx import Kokoro
from misaki import espeak
from misaki.espeak import EspeakG2P
from pydantic import BaseModel, Field

MODEL_URL = (
    "https://github.com/thewh1teagle/kokoro-onnx/releases/download/"
    "model-files-v1.0/kokoro-v1.0.onnx"
)
VOICES_URL = (
    "https://github.com/thewh1teagle/kokoro-onnx/releases/download/"
    "model-files-v1.0/voices-v1.0.bin"
)

DATA_DIR = Path(os.getenv("MAIRAIY_KOKORO_DIR", "/models")).resolve()
MODEL_PATH = DATA_DIR / "kokoro-v1.0.onnx"
VOICES_PATH = DATA_DIR / "voices-v1.0.bin"
VOICE_NAME = str(os.getenv("MAIRAIY_KOKORO_VOICE", "ff_siwis") or "ff_siwis").strip()
LANGUAGE = str(os.getenv("MAIRAIY_KOKORO_LANGUAGE", "fr-fr") or "fr-fr").strip()
API_KEY = str(os.getenv("OMNIVOICE_API_KEY", "") or "").strip()
DEFAULT_SPEED = float(os.getenv("MAIRAIY_KOKORO_SPEED", "1.0") or "1.0")
MAX_CHARS = max(120, min(520, int(os.getenv("MAIRAIY_KOKORO_CHUNK_CHARS", "430") or "430")))

app = FastAPI(title="Mairaiy Voice", version="1.0.0")
_load_lock = asyncio.Lock()
_synth_lock = asyncio.Lock()
_kokoro: Kokoro | None = None
_g2p: EspeakG2P | None = None


class SpeechRequest(BaseModel):
    model: str = "kokoro"
    input: str = Field(..., min_length=1, max_length=4096)
    voice: str | dict = "mairaiy"
    response_format: Literal["wav", "pcm"] = "wav"
    speed: float = Field(default=1.0, ge=0.25, le=4.0)
    language: str | None = None
    instructions: str | None = None
    instruct: str | None = None


def _auth(authorization: str | None = Header(default=None)) -> None:
    if not API_KEY:
        raise HTTPException(503, "OMNIVOICE_API_KEY is not configured")
    header = str(authorization or "")
    token = header[7:].strip() if header.lower().startswith("bearer ") else ""
    if not token or not secrets.compare_digest(token, API_KEY):
        raise HTTPException(401, "invalid voice token")


def _download(url: str, target: Path) -> None:
    target.parent.mkdir(parents=True, exist_ok=True)
    partial = target.with_suffix(target.suffix + ".part")
    partial.unlink(missing_ok=True)
    with urllib.request.urlopen(url, timeout=60) as source, partial.open("wb") as output:
        while True:
            chunk = source.read(1024 * 1024)
            if not chunk:
                break
            output.write(chunk)
    if partial.stat().st_size < 1024:
        partial.unlink(missing_ok=True)
        raise RuntimeError("downloaded voice asset is empty")
    partial.replace(target)


def _chunks(text: str) -> list[str]:
    clean = " ".join(str(text or "").replace("\n", " ").split()).strip()
    if not clean:
        return []
    sentences = re.findall(r"[^.!?…]+[.!?…]+|[^.!?…]+$", clean) or [clean]
    out: list[str] = []
    current = ""
    for raw in sentences:
        sentence = raw.strip()
        if not sentence:
            continue
        if len(sentence) > MAX_CHARS:
            if current:
                out.append(current)
                current = ""
            words = sentence.split()
            part = ""
            for word in words:
                candidate = f"{part} {word}".strip()
                if len(candidate) <= MAX_CHARS:
                    part = candidate
                else:
                    if part:
                        out.append(part)
                    part = word
            if part:
                out.append(part)
            continue
        candidate = f"{current} {sentence}".strip()
        if len(candidate) <= MAX_CHARS:
            current = candidate
        else:
            if current:
                out.append(current)
            current = sentence
    if current:
        out.append(current)
    return out


async def _ensure_loaded() -> tuple[Kokoro, EspeakG2P]:
    global _kokoro, _g2p
    if _kokoro is not None and _g2p is not None:
        return _kokoro, _g2p

    async with _load_lock:
        if _kokoro is not None and _g2p is not None:
            return _kokoro, _g2p

        if not MODEL_PATH.exists():
            await asyncio.to_thread(_download, MODEL_URL, MODEL_PATH)
        if not VOICES_PATH.exists():
            await asyncio.to_thread(_download, VOICES_URL, VOICES_PATH)

        def load() -> tuple[Kokoro, EspeakG2P]:
            espeak.EspeakFallback(british=False)
            g2p = EspeakG2P(language=LANGUAGE)
            kokoro = Kokoro(str(MODEL_PATH), str(VOICES_PATH))
            voices = set(kokoro.get_voices())
            if VOICE_NAME not in voices:
                raise RuntimeError(f"voice {VOICE_NAME!r} is missing from Kokoro voice pack")
            return kokoro, g2p

        _kokoro, _g2p = await asyncio.to_thread(load)
        return _kokoro, _g2p


def _normalize_voice(value: str | dict) -> str:
    if isinstance(value, dict):
        value = str(value.get("id") or "")
    voice = str(value or "").strip().lower()
    allowed = {"mairaiy", "default", VOICE_NAME.lower(), "alloy", "nova", "shimmer"}
    if voice not in allowed:
        raise HTTPException(400, f"unsupported voice {voice!r}; Mairaiy identity is locked")
    return VOICE_NAME


def _generate(text: str, speed: float) -> tuple[np.ndarray, int]:
    assert _kokoro is not None
    assert _g2p is not None
    pieces: list[np.ndarray] = []
    sample_rate = 24000
    for chunk in _chunks(text):
        phonemes, _ = _g2p(chunk)
        audio, sample_rate = _kokoro.create(
            phonemes,
            voice=VOICE_NAME,
            speed=max(0.72, min(1.45, speed * DEFAULT_SPEED)),
            is_phonemes=True,
        )
        pieces.append(np.asarray(audio, dtype=np.float32))
        pieces.append(np.zeros(int(sample_rate * 0.10), dtype=np.float32))
    if not pieces:
        raise ValueError("empty text")
    return np.concatenate(pieces), int(sample_rate)


@app.get("/health")
async def health():
    return {
        "status": "ok",
        "service": "mairaiy-kokoro",
        "engine": "kokoro-onnx",
        "voice": VOICE_NAME,
        "language": LANGUAGE,
        "model_ready": MODEL_PATH.exists() and VOICES_PATH.exists(),
        "identity_locked": True,
    }


@app.get("/.well-known/voicestudio-speech", dependencies=[Depends(_auth)])
async def discovery():
    return {
        "schema": "voicestudio-speech-compatible-v1",
        "provider": "AURA Mairaiy Kokoro",
        "openai_compatible_base": "/v1",
        "tts": True,
        "voices": "/v1/audio/voices",
        "models": "/v1/models",
        "speech": "/v1/audio/speech",
        "identity": "Mairaiy",
    }


@app.get("/v1/audio/voices", dependencies=[Depends(_auth)])
async def voices():
    return {
        "voices": [
            {
                "voice_id": "mairaiy",
                "name": "Mairaiy",
                "type": "profile",
                "language": "fr",
                "engine_voice": VOICE_NAME,
            }
        ],
        "engines": [
            {
                "id": "kokoro",
                "name": "Kokoro ONNX",
                "cloning": False,
                "device": "cpu",
            }
        ],
    }


@app.get("/v1/models", dependencies=[Depends(_auth)])
async def models():
    return {
        "object": "list",
        "data": [
            {
                "id": "kokoro",
                "object": "model",
                "owned_by": "aura",
                "voice": VOICE_NAME,
            },
            {
                "id": "omnivoice",
                "object": "model",
                "owned_by": "compatibility-alias",
                "voice": VOICE_NAME,
            },
        ],
    }


@app.post("/v1/audio/speech", dependencies=[Depends(_auth)])
async def speech(payload: SpeechRequest):
    model = payload.model.strip().lower()
    if model not in {"kokoro", "tts-1", "tts-1-hd", "omnivoice", "omnivoice-gguf"}:
        raise HTTPException(400, f"unsupported model {model!r}")

    _normalize_voice(payload.voice)
    await _ensure_loaded()

    async with _synth_lock:
        try:
            audio, sample_rate = await asyncio.wait_for(
                asyncio.to_thread(_generate, payload.input, payload.speed),
                timeout=45,
            )
        except asyncio.TimeoutError as exc:
            raise HTTPException(504, "Mairaiy synthesis timeout") from exc
        except Exception as exc:
            raise HTTPException(500, f"Mairaiy synthesis failed: {exc}") from exc

    if payload.response_format == "pcm":
        pcm = np.clip(audio, -1.0, 1.0)
        data = (pcm * 32767.0).astype("<i2").tobytes()
        return Response(content=data, media_type=f"audio/pcm;rate={sample_rate}")

    buf = io.BytesIO()
    sf.write(buf, audio, sample_rate, format="WAV", subtype="PCM_16")
    return Response(content=buf.getvalue(), media_type="audio/wav")

from pathlib import Path
import ast
import subprocess

ROOT = Path(__file__).resolve().parents[1]


def read(path: str) -> str:
    return (ROOT / path).read_text(encoding="utf-8")


def test_mairaiy_voice_compose_is_private_and_uses_historical_kokoro():
    compose = read("docker-compose.hostinger.yml")
    assert "mairaiy-voice:" in compose
    assert 'profiles: ["voice"]' in compose
    assert "dockerfile: Dockerfile.mairaiy-voice" in compose
    assert "MAIRAIY_KOKORO_VOICE:" in compose and "ff_siwis" in compose
    assert "MAIRAIY_KOKORO_LANGUAGE:" in compose and "fr-fr" in compose
    assert 'expose:' in compose and '"3900"' in compose
    assert "3900:3900" not in compose
    assert "horizon_mairaiy_voice_data" in compose
    assert "horizon_mairaiy_hf_cache" not in compose


def test_nginx_voice_proxy_is_lazy_and_not_publicly_bound_to_container_port():
    nginx = read("hostinger/evidence-nginx.conf")
    assert "location /voice/" in nginx
    assert "resolver 127.0.0.11" in nginx
    assert "set $mairaiy_voice_backend http://mairaiy-voice:3900;" in nginx
    assert "proxy_set_header Authorization $http_authorization;" in nginx
    assert "proxy_buffering off;" in nginx
    assert "client_max_body_size 24m;" in nginx


def test_managed_node_proxy_exposes_only_minimal_voice_contract():
    source = read("src/mairaiy_voice_proxy.js")
    assert "GET /health" in source
    assert "GET /.well-known/voicestudio-speech" in source
    assert "GET /v1/audio/voices" in source
    assert "GET /v1/models" in source
    assert "POST /v1/audio/speech" in source
    assert "synthesizeMairaiyNode" in source
    assert "consumeMairaiyQuota" in source
    assert "mairaiyNodeStatus" in source
    assert "config.mairaiyVoice.upstreamApiKey" in source
    assert "redirect: 'error'" in source
    assert "url.protocol !== 'https:'" in source
    assert "Readable.fromWeb(upstream.body).pipe(res)" in source
    assert "quantic-mairaiy-voice-proxy-v3" in source
    assert "mode: 'node-native'" in source
    assert "kokoro-onnx-node" not in source or "native Node Kokoro" in source
    assert "identity_locked" in source
    assert "model_ready" in source

    server = read("server_core.js")
    assert "installMairaiyVoiceProxy(app);" in server
    assert server.index("installMairaiyVoiceProxy(app);") < server.index(
        "app.use(requireQuanticIdentity);"
    )


def test_voice_deploy_script_has_resource_and_secret_guards():
    script = read("scripts/hostinger_deploy.sh")
    assert "MAIRAIY_VOICE_ENABLED" in script
    assert "OMNIVOICE_API_KEY" in script
    assert "2097152" in script
    assert "--profile voice" in script
    assert "/voice/health" in script
    subprocess.run(
        ["bash", "-n", str(ROOT / "scripts/hostinger_deploy.sh")],
        check=True,
    )


def test_voice_environment_contract_is_documented():
    vps_env = read(".env.hostinger.example")
    node_env = read(".env.node.hostinger.example")
    assert "MAIRAIY_KOKORO_VOICE=ff_siwis" in vps_env
    assert "MAIRAIY_KOKORO_LANGUAGE=fr-fr" in vps_env
    assert "OMNIVOICE_API_KEY=" in vps_env
    assert "MAIRAIY_NODE_NATIVE_ENABLED=true" in node_env
    assert "MAIRAIY_PUBLIC_SPEECH_ENABLED=true" in node_env
    assert "MAIRAIY_KOKORO_DTYPE=q8" in node_env
    assert "MAIRAIY_PUBLIC_REQUESTS_PER_MINUTE=6" in node_env
    assert "MAIRAIY_PUBLIC_REQUESTS_PER_DAY=240" in node_env


def test_mairaiy_python_service_is_voice_locked_and_syntax_valid():
    service = read("mairaiy_voice_service/app.py")
    ast.parse(service)
    assert 'VOICE_NAME = str(os.getenv("MAIRAIY_KOKORO_VOICE", "ff_siwis")' in service
    assert '"name": "Mairaiy"' in service
    assert '"type": "profile"' in service
    assert '"engine": "kokoro-onnx"' in service
    assert "identity_locked" in service
    assert "secrets.compare_digest" in service
    assert '@app.post("/v1/audio/speech"' in service
    assert "response_format" in service
    assert 'media_type="audio/wav"' in service

    requirements = read("mairaiy_voice_service/requirements.txt")
    assert "kokoro-onnx==0.6.1" in requirements
    assert "misaki-fork==0.9.6" in requirements
    assert "soundfile==0.13.1" in requirements


def test_mairaiy_container_is_lightweight_python_service():
    dockerfile = read("Dockerfile.mairaiy-voice")
    assert "FROM python:3.12-slim" in dockerfile
    assert "mairaiy_voice_service/requirements.txt" in dockerfile
    assert "uvicorn" in dockerfile
    assert "torch" not in dockerfile.lower()


def test_mairaiy_service_preloads_model_before_health():
    service = read("mairaiy_voice_service/app.py")
    assert '@app.on_event("startup")' in service
    assert "await _ensure_loaded()" in service


def test_hostinger_smoke_targets_real_native_voice_contract():
    workflow = read(".github/workflows/hostinger-production-smoke.yml")
    assert "/voice/status" in workflow
    assert "/voice/v1/audio/speech" in workflow
    assert "quantic-mairaiy-voice-proxy-v3" in workflow
    assert "node-native" in workflow
    assert "model_ready" in workflow
    assert "kokoro-onnx-node" in workflow
    assert "ff_siwis" in workflow
    assert "RIFF" in workflow
    assert "WAVE" in workflow
    assert "Quantic Studio 2.7.4" not in workflow
    assert "Quantic Glide 1.2.6" not in workflow


def test_node_native_mairaiy_is_french_voice_locked_and_zero_api_cost():
    source = read("src/mairaiy_kokoro_node.js")
    assert "onnx-community/Kokoro-82M-v1.0-ONNX" in source
    assert "1939ad2a8e416c0acfeecc08a694d14ef25f2231" in source
    assert "const VOICE = 'ff_siwis'" in source
    assert "const LANGUAGE = 'fr-fr'" in source
    assert "@piper-plus/g2p/fr" in source\n    assert "FrenchG2P" in source\n    assert "kokoroToken" in source
    assert "StyleTextToSpeech2Model" in source
    assert "dtype: String(process.env.MAIRAIY_KOKORO_DTYPE || 'q8')" in source
    assert "zero_api_cost: true" in source
    assert "wavFromFloat32" in source
    assert "daily-cap" in source
    assert "rate-limit" in source


def test_node_world_eye_ci_runs_real_mairaiy_synthesis():
    workflow = read(".github/workflows/node-world-eye.yml")
    assert "Verify native Mairaiy Kokoro synthesis" in workflow
    assert "npm run test:mairaiy-node" in workflow
    assert "MAIRAIY_KOKORO_DTYPE: q8" in workflow

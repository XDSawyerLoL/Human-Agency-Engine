from cryptography.fernet import Fernet, InvalidToken

from ..config import settings


class TokenCipher:
    def __init__(self, key: str | None = None):
        raw_key = key if key is not None else settings.token_encryption_key
        if not raw_key:
            raise RuntimeError(
                "TOKEN_ENCRYPTION_KEY is required before connecting external accounts"
            )
        try:
            self._fernet = Fernet(raw_key.encode("utf-8"))
        except ValueError as exc:
            raise RuntimeError(
                "TOKEN_ENCRYPTION_KEY must be a valid Fernet key"
            ) from exc

    def encrypt(self, plaintext: str) -> str:
        return self._fernet.encrypt(plaintext.encode("utf-8")).decode("utf-8")

    def decrypt(self, ciphertext: str) -> str:
        try:
            return self._fernet.decrypt(ciphertext.encode("utf-8")).decode("utf-8")
        except InvalidToken as exc:
            raise RuntimeError("Stored connector token could not be decrypted") from exc

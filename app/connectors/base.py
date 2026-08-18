from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Protocol


@dataclass(frozen=True)
class NormalizedSignal:
    external_key: str
    source: str
    type: str
    payload: dict
    observed_at: datetime


class ReadOnlyConnector(Protocol):
    provider: str

    def sync(self, account_id: int) -> dict:
        ...

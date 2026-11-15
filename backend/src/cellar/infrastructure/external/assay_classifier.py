"""HTTP adapter for the ``MethodReader`` port: the assay classifier's ``POST /predict``.

The classifier (``~/workspace/assay-classifier``, ``python -m assay_classifier.demo``) runs on a
GPU host. It answers every question it knows; each copied value comes with its character span in
the text it read (the method, cut to its first 1,500 words), and the quote is that span's line.

Off unless ``ASSAY_CLASSIFIER_URL`` is set: the GPU is a deployment choice, not a default.
"""

from __future__ import annotations

import httpx
from pydantic_settings import BaseSettings, SettingsConfigDict

from cellar.application.screening.suggest_from_method import MethodAnswer, MethodReader
from cellar.domain.shared.errors import ServiceUnavailableError

QUOTE_CHARS = 160


class AssayClassifierSettings(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="ASSAY_CLASSIFIER_", env_file=".env", extra="ignore"
    )

    url: str | None = None
    # A long method takes ~15 s on an Apple GPU; one request at a time, so allow for a queue.
    timeout_seconds: float = 60.0


class HttpMethodReader(MethodReader):
    def __init__(self, client: httpx.AsyncClient, settings: AssayClassifierSettings) -> None:
        if not settings.url:
            raise ValueError("ASSAY_CLASSIFIER_URL is not set")
        self._client = client
        self._url = settings.url.rstrip("/") + "/predict"
        self._timeout = settings.timeout_seconds

    async def read(self, method: str) -> list[MethodAnswer]:
        try:
            r = await self._client.post(self._url, json={"text": method}, timeout=self._timeout)
            r.raise_for_status()
            body = r.json()
        except (httpx.HTTPError, ValueError) as exc:
            raise ServiceUnavailableError("The assay classifier did not answer") from exc
        return answers_from(body)


def answers_from(body: dict) -> list[MethodAnswer]:
    """One answer per located value: a list answer has a span per member."""
    text: str = body["text"]
    return [
        MethodAnswer(row["question"], text[start:end], quote(text, start, end))
        for row in body["rows"]
        for start, end in row.get("spans", [])
    ]


def quote(text: str, start: int, end: int) -> str:
    """The line holding the span, cut around it when the line is long."""
    lo = text.rfind("\n", 0, start) + 1
    hi = text.find("\n", end)
    hi = len(text) if hi < 0 else hi
    if hi - lo > QUOTE_CHARS:
        pad = max((QUOTE_CHARS - (end - start)) // 2, 0)
        cut_lo, cut_hi = max(lo, start - pad), min(hi, end + pad)
        return (
            ("…" if cut_lo > lo else "")
            + text[cut_lo:cut_hi].strip()
            + ("…" if cut_hi < hi else "")
        )
    return text[lo:hi].strip()

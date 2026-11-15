"""Suggestions from the method: pH and Temperature as condition definitions, the stated value as
evidence; off when no classifier is configured; the classifier's answer read into quotes."""

import httpx
import pytest
from returns.result import Failure, Success

from cellar.application.screening.suggest_from_method import (
    ConditionSuggestion,
    Evidence,
    MethodAnswer,
    SuggestFromMethod,
    SuggestFromMethodQuery,
)
from cellar.domain.shared.errors import (
    AuthorizationError,
    ServiceUnavailableError,
    ValidationError,
)
from cellar.infrastructure.external.assay_classifier import (
    AssayClassifierSettings,
    HttpMethodReader,
    answers_from,
    quote,
)
from tests.fakes.fake_auth import FakeAuth

METHOD = (
    "Materials: InhA 50 nM in 30 mM PIPES buffer, pH 6.8.\n"
    "1. Preincubate 10 min at 25 °C.\n"
    "2. Read A340 at 25 °C."
)


class _Reader:
    def __init__(self, answers=None, error=None):
        self.answers, self.error = answers or [], error

    async def read(self, method):
        if self.error:
            raise self.error
        return self.answers


def _q(method=METHOD):
    return SuggestFromMethodQuery(method=method)


async def test_ph_and_temperature_become_definitions_with_their_evidence():
    reader = _Reader(
        [
            MethodAnswer("cond_temperature", "25 °C", "1. Preincubate 10 min at 25 °C."),
            MethodAnswer("cond_temperature", "25 °C", "1. Preincubate 10 min at 25 °C."),
            MethodAnswer("cond_temperature", "25 °C", "2. Read A340 at 25 °C."),
            MethodAnswer("cond_ph", "6.8", "Materials: … pH 6.8."),
            MethodAnswer("cond_incubation_time", "10 min", "1. Preincubate 10 min at 25 °C."),
        ]
    )
    result = await SuggestFromMethod(reader)(_q(), auth=FakeAuth(role="editor"))
    assert result == Success(
        [
            ConditionSuggestion("pH", "numeric", None, (Evidence("6.8", "Materials: … pH 6.8."),)),
            ConditionSuggestion(
                "Temperature",
                "numeric",
                "°C",
                (
                    Evidence("25 °C", "1. Preincubate 10 min at 25 °C."),
                    Evidence("25 °C", "2. Read A340 at 25 °C."),
                ),
            ),
        ]
    )


async def test_nothing_found_is_an_empty_list():
    result = await SuggestFromMethod(_Reader())(_q(), auth=FakeAuth(role="editor"))
    assert result == Success([])


async def test_a_viewer_cannot_ask():
    with pytest.raises(AuthorizationError):
        await SuggestFromMethod(_Reader())(_q(), auth=FakeAuth(role="viewer"))


async def test_off_without_a_classifier():
    uc = SuggestFromMethod(None)
    assert not uc.enabled
    result = await uc(_q(), auth=FakeAuth(role="editor"))
    assert isinstance(result, Failure)
    assert isinstance(result.failure(), ServiceUnavailableError)


async def test_a_blank_method_is_refused():
    result = await SuggestFromMethod(_Reader())(_q("  \n"), auth=FakeAuth(role="editor"))
    assert isinstance(result.failure(), ValidationError)


async def test_an_unreachable_classifier_is_a_failure_not_a_crash():
    reader = _Reader(error=ServiceUnavailableError("down"))
    result = await SuggestFromMethod(reader)(_q(), auth=FakeAuth(role="editor"))
    assert isinstance(result.failure(), ServiceUnavailableError)


# --- the adapter --------------------------------------------------------------------------


def _row(question, *values):
    spans = [[METHOD.index(v), METHOD.index(v) + len(v)] for v in values]
    return {"question": question, "answer": ", ".join(values) or "none", "spans": spans}


BODY = {
    "text": METHOD,
    "rows": [_row("cond_ph", "6.8"), _row("cond_temperature", "25 °C"), _row("species")],
}


def test_each_located_value_is_quoted_by_its_line():
    assert answers_from(BODY) == [
        MethodAnswer("cond_ph", "6.8", "Materials: InhA 50 nM in 30 mM PIPES buffer, pH 6.8."),
        MethodAnswer("cond_temperature", "25 °C", "1. Preincubate 10 min at 25 °C."),
    ]


def test_a_long_line_is_cut_around_the_value():
    text = "x" * 300 + " pH 7.4 " + "y" * 300
    start = text.index("7.4")
    q = quote(text, start, start + 3)
    assert "7.4" in q and q.startswith("…") and q.endswith("…") and len(q) <= 162


async def test_the_adapter_posts_the_method_and_reads_the_answer():
    seen = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["url"], seen["body"] = str(request.url), request.content
        return httpx.Response(200, json=BODY)

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        reader = HttpMethodReader(
            client, AssayClassifierSettings(url="http://gpu:8765/", _env_file=None)
        )
        answers = await reader.read(METHOD)
    assert seen["url"] == "http://gpu:8765/predict"
    assert [a.question for a in answers] == ["cond_ph", "cond_temperature"]


async def test_an_unreachable_classifier_is_unavailable():
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("refused")

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        reader = HttpMethodReader(
            client, AssayClassifierSettings(url="http://gpu:8765", _env_file=None)
        )
        with pytest.raises(ServiceUnavailableError):
            await reader.read(METHOD)


def test_off_by_default(monkeypatch):
    # `make` exports the root .env, which may switch it on for this machine.
    monkeypatch.delenv("ASSAY_CLASSIFIER_URL", raising=False)
    assert AssayClassifierSettings(_env_file=None).url is None

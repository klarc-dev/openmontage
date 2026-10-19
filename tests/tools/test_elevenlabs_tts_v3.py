"""ElevenLabs TTS: v3 constraints fail fast and API rejections stay readable.

Both regressions were hit against the live API: eleven_v3 answers 400 to any
continuity input, and the tool reported only "400 Bad Request" because
raise_for_status() discarded the body that named the offending parameter.
"""

from __future__ import annotations

from typing import Any

import pytest

from tools.audio.elevenlabs_tts import ElevenLabsTTS


class _Response:
    def __init__(self, status: int, body: Any = None, content: bytes = b"ID3audio") -> None:
        self.status_code = status
        self.ok = status < 400
        self._body = body
        self.content = content
        self.headers = {"request-id": "req-test"}
        self.text = str(body)

    def json(self) -> Any:
        if self._body is None:
            raise ValueError("no json")
        return self._body

    def raise_for_status(self) -> None:
        import requests

        if not self.ok:
            raise requests.HTTPError(f"{self.status_code} Client Error", response=self)


@pytest.fixture
def calls(monkeypatch: pytest.MonkeyPatch) -> list[dict[str, Any]]:
    monkeypatch.setenv("ELEVENLABS_API_KEY", "test-key")
    recorded: list[dict[str, Any]] = []
    import requests

    def fake_post(url: str, **kwargs: Any) -> _Response:
        recorded.append(kwargs["json"])
        return _Response(200)

    monkeypatch.setattr(requests, "post", fake_post)
    return recorded


@pytest.mark.parametrize("field,value", [
    ("previous_text", "Avant."),
    ("next_text", "Après."),
    ("previous_request_ids", ["req-1"]),
    ("next_request_ids", ["req-2"]),
])
def test_v3_rejects_continuity_inputs_before_calling_the_api(
    calls: list[dict[str, Any]], tmp_path: Any, field: str, value: Any
) -> None:
    result = ElevenLabsTTS().execute({
        "text": "Bonjour.", "model_id": "eleven_v3", field: value,
        "output_path": str(tmp_path / "out.mp3"),
    })
    assert not result.success
    assert field in result.error and "one request" in result.error
    assert calls == [], "no request should be spent on a call the API will reject"


def test_v2_still_forwards_continuity_inputs(calls: list[dict[str, Any]], tmp_path: Any) -> None:
    result = ElevenLabsTTS().execute({
        "text": "Bonjour.", "model_id": "eleven_multilingual_v2",
        "previous_request_ids": ["req-1"], "next_request_ids": ["req-2"],
        "output_path": str(tmp_path / "out.mp3"),
    })
    assert result.success
    assert calls[0]["previous_request_ids"] == ["req-1"]
    assert calls[0]["next_request_ids"] == ["req-2"]


def test_api_rejection_reason_is_surfaced(monkeypatch: pytest.MonkeyPatch, tmp_path: Any) -> None:
    monkeypatch.setenv("ELEVENLABS_API_KEY", "test-key")
    import requests

    reason = "Quota exceeded for this voice"
    monkeypatch.setattr(
        requests, "post",
        lambda url, **kw: _Response(400, {"detail": {"status": "invalid", "message": reason}}),
    )
    result = ElevenLabsTTS().execute({
        "text": "Bonjour.", "model_id": "eleven_v3",
        "output_path": str(tmp_path / "out.mp3"),
    })
    assert not result.success
    assert "400" in result.error and reason in result.error

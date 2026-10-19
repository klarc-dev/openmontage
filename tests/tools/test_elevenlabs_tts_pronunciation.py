"""Native ElevenLabs pronunciation controls, without paid API calls."""

from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from tools.audio.elevenlabs_tts import ElevenLabsTTS


@pytest.fixture
def post(monkeypatch):
    import requests

    monkeypatch.setenv("ELEVENLABS_API_KEY", "test-key")
    response = SimpleNamespace(
        content=b"ID3audio", headers={"request-id": "test-request"},
        raise_for_status=lambda: None,
    )
    mocked = Mock(return_value=response)
    monkeypatch.setattr(requests, "post", mocked)
    return mocked


@pytest.mark.parametrize("count", [0, 1, 3])
def test_native_pronunciation_controls_are_forwarded(post, tmp_path, count):
    locators = [
        {"pronunciation_dictionary_id": f"dictionary-{i}", "version_id": f"version-{i}"}
        for i in range(count)
    ]
    text = "Bienvenue à Nice."
    result = ElevenLabsTTS().execute({
        "text": text,
        "model_id": "eleven_flash_v2_5",
        "language_code": "fr",
        "pronunciation_dictionary_locators": locators,
        "output_path": str(tmp_path / "out.mp3"),
    })
    assert result.success
    post.assert_called_once()
    payload = post.call_args.kwargs["json"]
    assert payload["text"] == text  # Never rewrite Nice as inline IPA.
    assert payload["language_code"] == "fr"
    assert payload["pronunciation_dictionary_locators"] == locators
    assert "language_code" not in payload["voice_settings"]
    assert (tmp_path / "out.mp3").read_bytes() == b"ID3audio"


def test_v4_rejects_unsupported_voice_settings(post, tmp_path):
    result = ElevenLabsTTS().execute({
        "text": "Une narration plus vive.",
        "model_id": "eleven_v4",
        "stability": 0.3,
        "similarity_boost": 0.72,
        "style": 0.8,
        "speed": 1.1,
        "use_speaker_boost": True,
        "output_path": str(tmp_path / "out.mp3"),
    })
    assert not result.success
    assert 'does not accept voice settings' in (result.error or '')
    post.assert_not_called()


def test_v3_rejects_continuity_before_request(post, tmp_path):
    result = ElevenLabsTTS().execute({
        "text": "A continuous narration.",
        "model_id": "eleven_v3",
        "previous_text": "Preceding context.",
        "output_path": str(tmp_path / "out.mp3"),
    })
    assert not result.success
    assert result.error is not None
    assert "does not accept continuity inputs" in result.error
    post.assert_not_called()


@pytest.mark.parametrize("options", [
    {},
    {"language_code": None, "pronunciation_dictionary_locators": None},
])
def test_optional_pronunciation_controls_are_omitted(post, tmp_path, options):
    result = ElevenLabsTTS().execute({
        "text": "Nice", "output_path": str(tmp_path / "out.mp3"), **options,
    })
    assert result.success
    post.assert_called_once()
    payload = post.call_args.kwargs["json"]
    assert "language_code" not in payload
    assert "pronunciation_dictionary_locators" not in payload


@pytest.mark.parametrize("locators", [
    [{"pronunciation_dictionary_id": "dict", "version_id": "v1"}] * 4,
    {"pronunciation_dictionary_id": "dict", "version_id": "v1"},
    ["dict"],
    [{}],
    [{"pronunciation_dictionary_id": "dict"}],
    [{"version_id": "v1"}],
    [{"pronunciation_dictionary_id": "", "version_id": "v1"}],
    [{"pronunciation_dictionary_id": "dict", "version_id": None}],
    [{"pronunciation_dictionary_id": 1, "version_id": "v1"}],
    [{"pronunciation_dictionary_id": "dict", "version_id": "v1", "extra": True}],
])
def test_invalid_locators_fail_before_request(post, tmp_path, locators):
    output = tmp_path / "out.mp3"
    result = ElevenLabsTTS().execute({
        "text": "Nice", "pronunciation_dictionary_locators": locators,
        "output_path": str(output),
    })
    assert not result.success
    assert "pronunciation_dictionary_locators" in result.error
    post.assert_not_called()
    assert not output.exists()


def test_pronunciation_schema_and_idempotency_contract():
    properties = ElevenLabsTTS.input_schema["properties"]
    assert properties["language_code"]["type"] == "string"
    locators = properties["pronunciation_dictionary_locators"]
    assert locators["type"] == "array"
    assert locators["maxItems"] == 3
    item = locators["items"]
    assert item["type"] == "object"
    assert set(item["required"]) == {"pronunciation_dictionary_id", "version_id"}
    assert item["additionalProperties"] is False
    for field in item["required"]:
        assert item["properties"][field] == {"type": "string", "minLength": 1}
    for field in ("language_code", "pronunciation_dictionary_locators"):
        assert field in ElevenLabsTTS.idempotency_key_fields
        assert field not in ElevenLabsTTS.input_schema["required"]

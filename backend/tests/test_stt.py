"""Paid dictation, the provider (common/stt.py): language hint forms, price math, errors, no audio kept. A fake HTTP layer; no network."""
import io
import json
import urllib.error

import pytest

from common import stt


class _Resp(io.BytesIO):
    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


def opener(payload=None, error=None, sink=None):
    def _open(req, timeout=None):
        if sink is not None:
            sink.append((req, timeout))
        if error:
            raise error
        return _Resp(json.dumps(payload).encode())
    return _open


def provider(**kw):
    return stt.OpenAIProvider(api_key="sk-test", opener=opener(**kw))


def test_one_language_uses_the_plain_language_field_and_two_use_the_array():
    assert stt.language_fields(["es"]) == [("language", "es")]
    assert stt.language_fields(["en", "es"]) == [("languages[]", "en"), ("languages[]", "es")]
    assert stt.language_fields([]) == []


def test_the_request_carries_model_hint_and_file_and_the_key_only_in_the_header():
    sink = []
    p = stt.OpenAIProvider(api_key="sk-test", opener=opener({"text": " Hola ", "languages": [{"code": "es"}], "usage": {"type": "duration", "seconds": 5}}, sink=sink))
    out = p.transcribe(b"AUDIO", "audio/webm;codecs=opus", ["es"], "A request for a video")
    req, timeout = sink[0]
    body = req.data.decode("latin-1")
    assert 'name="model"\r\n\r\ngpt-transcribe' in body and 'name="language"\r\n\r\nes' in body and "languages" not in body and 'name="prompt"' in body
    assert 'filename="audio.webm"' in body and "Content-Type: audio/webm\r\n" in body and "AUDIO" in body
    assert req.get_header("Authorization") == "Bearer sk-test" and "sk-test" not in body and timeout == 25.0
    assert out["text"] == "Hola" and out["language"] == "es" and out["seconds"] == 5 and out["model"] == "gpt-transcribe" and out["provider"] == "openai"


def test_price_math_is_per_second_at_the_list_rate():
    assert stt.cost_usd(60) == 0.0045 and stt.cost_usd(180) == 0.0135 and stt.cost_usd(300) == 0.0225
    out = provider(payload={"text": "x", "usage": {"seconds": 90}}).transcribe(b"a", "audio/mp4", [])
    assert out["cost_usd"] == 0.00675


def test_seconds_fall_back_to_the_claim_then_to_the_size_and_never_below_one():
    p = provider(payload={"text": "x"})
    assert p.transcribe(b"a" * 100, "audio/webm", [], claimed_seconds=12.5)["seconds"] == 12.5
    assert p.transcribe(b"a" * 30000, "audio/webm", [])["seconds"] == 10
    assert p.transcribe(b"a", "audio/webm", [])["seconds"] == 1


def test_languages_are_cleaned():
    assert stt.clean_languages(["es-MX", "EN", "en", "xx1", 5, None, "fr", "de", "it"]) == ["es", "en", "fr", "de"]
    assert stt.clean_languages("es") == [] and stt.clean_languages(None) == []


@pytest.mark.parametrize("status,code", [(400, "bad_audio"), (415, "bad_audio"), (429, "provider_busy"), (500, "provider_unavailable"), (503, "provider_unavailable")])
def test_provider_http_errors_map_to_codes(status, code):
    err = urllib.error.HTTPError("u", status, "x", {}, io.BytesIO(b'{"error":{"message":"secret words"}}'))
    with pytest.raises(stt.SttError) as e:
        provider(error=err).transcribe(b"a", "audio/webm", [])
    assert e.value.code == code and "secret words" not in str(e.value)


def test_timeout_and_network_errors_are_unavailable():
    for err in (TimeoutError(), urllib.error.URLError("down"), OSError()):
        with pytest.raises(stt.SttError) as e:
            provider(error=err).transcribe(b"a", "audio/webm", [])
        assert e.value.code == "provider_unavailable"


def test_the_default_model_is_the_one_without_a_shutdown_date_and_a_second_slot_is_reserved():
    assert stt.DEFAULT_MODEL == "gpt-transcribe" and set(stt.RATE_PER_MINUTE_USD) == {"gpt-transcribe"} and "openai" in stt.PROVIDERS
    with pytest.raises(stt.SttError):
        stt.provider("elevenlabs")   # reserved, not built

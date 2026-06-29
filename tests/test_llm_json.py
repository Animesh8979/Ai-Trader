import pytest

from godmode.llm.provider import LLMError, extract_json


def test_plain_json():
    assert extract_json('{"action": "buy", "size": 1}') == {"action": "buy", "size": 1}


def test_fenced_json():
    assert extract_json('```json\n{"action": "hold"}\n```') == {"action": "hold"}


def test_embedded_json():
    assert extract_json('Reasoning... Final: {"action": "sell"} done.') == {"action": "sell"}


def test_bad_json_raises():
    with pytest.raises(LLMError):
        extract_json("there is no json here")


def test_empty_raises():
    with pytest.raises(LLMError):
        extract_json("   ")

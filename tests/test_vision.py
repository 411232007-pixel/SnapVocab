import json

import pytest

from snapvocab.vision import ClaudeVision, VisionError

from .conftest import make_card


def _stream(structured, is_error=False) -> str:
    events = [{"type": "system"}, {"type": "result", "is_error": is_error, "structured_output": structured}]
    return "\n".join(json.dumps(e) for e in events)


def test_identification_parsed_and_sanitised():
    v = ClaudeVision()
    out = _stream({"candidates": [{"zh_name": " 馬克杯\n", "confidence": "high"},
                                  {"zh_name": "x", "confidence": "bogus"},
                                  {"zh_name": "", "confidence": "low"}],
                   "single_clear_target": True})
    ident = v._parse_identification(out)
    assert [c.zh_name for c in ident.candidates] == ["馬克杯"]
    assert ident.single_clear_target


def test_error_result_becomes_user_safe_message():
    with pytest.raises(VisionError) as exc:
        ClaudeVision()._parse_identification(_stream(None, is_error=True))
    assert "暫時無法處理" in str(exc.value)


def test_garbage_output_rejected():
    with pytest.raises(VisionError):
        ClaudeVision()._parse_identification("not json")
    with pytest.raises(VisionError):
        ClaudeVision()._parse_identification(_stream("oops"))


async def test_generate_retries_once_then_fails(monkeypatch):
    v = ClaudeVision()
    calls = []

    async def fake_run(args, stdin):
        calls.append(1)
        return json.dumps({"type": "result", "is_error": False, "structured_output": {"zh_name": "x"}})

    monkeypatch.setattr(v, "_run", fake_run)
    with pytest.raises(VisionError):
        await v.generate("雨傘")
    assert len(calls) == 2


async def test_generate_accepts_valid_card(monkeypatch):
    v = ClaudeVision()

    async def fake_run(args, stdin):
        assert "--tools" in args and args[args.index("--tools") + 1] == ""  # no tools enabled
        return json.dumps({"type": "result", "is_error": False,
                           "structured_output": make_card().as_dict()})

    monkeypatch.setattr(v, "_run", fake_run)
    assert (await v.generate("雨傘")).en_word == "umbrella"

"""Comprehensive Worst-Case Scenario Resilience Tests.

Tests system behavior under severe error conditions, offline failures,
corrupted configurations, backend crashes, OOM context limits, and malformed inputs.
"""

import os
import json
import pytest
from unittest.mock import MagicMock, patch

from config import config_manager
from plugins.services.service_llm import OpenAILLM, LLMRouter, is_context_limit_error, LLMProviderError, build_services
from plugins.services.service_whisper import FasterWhisperService, _looks_like_hallucination
from plugins.tools.tool_transcribe_audio import TranscribeAudioTool
from state_machine.conversation import ConversationState, Participant
from state_machine.errors import ActionError, ERROR_INVALID_ACTION


# =====================================================================
# 1. LOCAL LLM WORST-CASE TESTS
# =====================================================================

def test_unreachable_local_llm_endpoint():
    """Verify OpenAILLM handles connection refusal gracefully without unhandled exceptions."""
    llm = OpenAILLM("local-model", api_key=None, base_url="http://127.0.0.1:59999/v1")
    llm.load()
    res = llm.invoke([{"role": "user", "content": "Hello"}])
    assert res.error != ""
    assert res.content.startswith("Error:")


def test_context_window_overflow_classification():
    """Verify context limit errors are correctly identified and raised as LLMProviderError."""
    err_msg = "BadRequestError: Error code: 400 - {'error': {'message': 'Maximum context length is 8192 tokens, but prompt contains 9200 tokens'}}"
    assert is_context_limit_error(Exception(err_msg)) is True

    fake_err = Exception("Connection reset by peer")
    assert is_context_limit_error(fake_err) is False


def test_llm_router_handles_all_unloaded_services():
    """Verify LLMRouter surfaces clean error response when all LLM services fail."""
    config = {
        "llm_profiles": {
            "broken-local": {
                "llm_endpoint": "http://127.0.0.1:59999/v1",
                "llm_service_class": "OpenAILLM",
                "llm_context_size": 8192,
            }
        },
        "default_llm_profile": "broken-local",
    }
    services = build_services(config)
    router = services["llm"]
    # LLM service is not loaded
    res = router.invoke([{"role": "user", "content": "test"}])
    assert res.error != ""
    assert res.error_code == "not_loaded"


# =====================================================================
# 2. AUDIO & MEDIA WORST-CASE TESTS
# =====================================================================

def test_whisper_hallucination_filter():
    """Verify hallucination detection filters repetitive YouTube noise phrases."""
    assert _looks_like_hallucination("Thank you. Thank you. Thank you. Thank you. Thank you. Thank you. Thank you. Thank you.") is True
    assert _looks_like_hallucination("Thanks for watching.") is True
    assert _looks_like_hallucination("This is a genuine user voice query about local AI.") is False


def test_transcribe_tool_handles_corrupted_file(tmp_path):
    """Verify TranscribeAudioTool handles zero-byte / corrupted audio gracefully."""
    corrupted_file = tmp_path / "corrupted.wav"
    corrupted_file.write_bytes(b"")

    tool = TranscribeAudioTool()
    mock_whisper = MagicMock()
    mock_whisper.transcribe.side_effect = Exception("Invalid WAV header")

    class DummyContext:
        services = {"whisper": mock_whisper}

    res = tool.run({"file_path": str(corrupted_file)}, DummyContext())
    assert res.error != ""
    assert "Transcription failed" in res.error


# =====================================================================
# 3. CONFIGURATION WORST-CASE TESTS
# =====================================================================

def test_config_loader_recovers_from_corrupted_json(tmp_path):
    """Verify config manager recovers gracefully when config.json is corrupted."""
    bad_config = tmp_path / "config.json"
    bad_config.write_text("{ malformed_json: true, ")

    loaded = config_manager.load(str(bad_config))
    assert isinstance(loaded, dict)
    assert "enabled_frontends" in loaded


def test_frontend_normalization_handles_mixed_types():
    """Verify _normalize_frontends survives invalid types and empty strings."""
    assert config_manager._normalize_frontends(None) == ["repl", "telegram"]
    assert config_manager._normalize_frontends(12345) == ["repl", "telegram"]
    assert config_manager._normalize_frontends(["repl", "", None, "CUSTOM_WEB"]) == ["repl", "custom_web"]


# =====================================================================
# 4. STATE MACHINE WORST-CASE TESTS
# =====================================================================

from state_machine.action import SendText


def test_conversation_state_machine_illegal_action_rejection():
    """Verify state machine strictly rejects illegal actions during wrong phase."""
    conv = ConversationState([
        Participant("user", "user"),
        Participant("agent", "agent"),
    ])
    # At initial state, turn priority is user. Attempting agent action returns failed ActionResult
    result = SendText(conv, "agent", {"text": "hello"}).enact()
    assert result.ok is False
    assert result.error is not None

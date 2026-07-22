"""Tests for Local AI service and audio transcription tool."""

import pytest
from plugins.services.service_llm import OpenAILLM, build_services
from plugins.tools.tool_transcribe_audio import TranscribeAudioTool


def test_openai_llm_local_api_key_default():
    """Verify that OpenAILLM defaults api_key to no-key-required for local endpoints."""
    llm = OpenAILLM("local-model", api_key=None, base_url="http://127.0.0.1:8081/v1")
    assert llm.model_name == "local-model"
    assert llm.base_url == "http://127.0.0.1:8081/v1"


def test_default_llm_profiles_populated():
    """Verify default 6GB VRAM profiles are populated when config has empty profiles."""
    config = {}
    services = build_services(config)
    assert "llm_profiles" in config
    assert "llama-server" in config["llm_profiles"]
    assert config["llm_profiles"]["llama-server"]["llm_context_size"] == 8192
    assert "llm" in services


def test_transcribe_audio_tool_missing_file():
    """Verify TranscribeAudioTool returns error when file is missing."""
    tool = TranscribeAudioTool()
    class DummyContext:
        services = {}
    res = tool.run({"file_path": "non_existent_audio.wav"}, DummyContext())
    assert res.error != ""
    assert "not found" in res.error.lower()

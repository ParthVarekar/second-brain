"""Tool plugin for transcribing audio files using local STT."""

import os
from pathlib import Path
from plugins.BaseTool import BaseTool, ToolResult


class TranscribeAudioTool(BaseTool):
    """LLM-callable tool to transcribe local audio files via local Whisper service."""

    name = "transcribe_audio"
    description = "Transcribe a local audio file (WAV, MP3, M4A, FLAC, OGG) to text using local Speech-To-Text."
    requires_services = ["whisper"]

    parameters = {
        "type": "object",
        "properties": {
            "file_path": {
                "type": "string",
                "description": "Absolute path to the audio file to transcribe.",
            },
        },
        "required": ["file_path"],
    }

    def run(self, args: dict, context) -> ToolResult:
        """Execute audio transcription."""
        file_path = args.get("file_path", "").strip()
        if not file_path or not os.path.exists(file_path):
            return ToolResult(
                error=f"Audio file not found: '{file_path}'",
            )

        whisper_svc = context.services.get("whisper")
        if not whisper_svc:
            return ToolResult(
                error="Whisper STT service is not available",
            )

        try:
            transcript = whisper_svc.transcribe(file_path)
            if not transcript:
                return ToolResult(
                    data={"file_path": file_path, "transcript": ""},
                    llm_summary=f"Audio file '{Path(file_path).name}' processed, but no speech was detected.",
                )

            return ToolResult(
                data={"file_path": file_path, "transcript": transcript},
                llm_summary=f"Transcript for '{Path(file_path).name}':\n\n{transcript}",
            )
        except Exception as e:
            return ToolResult(
                error=f"Transcription failed: {e}",
            )

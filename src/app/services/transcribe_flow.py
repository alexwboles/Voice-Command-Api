from fastapi import UploadFile
from groq import APIError, Groq

from src.app.core.config import get_settings
from src.app.schemas.voice import (
    InstructionPayload,
    TaskCreate,
    TaskReplace,
    TaskUpdate,
    TranscribeFlowResponse,
)
from src.app.services.instruction_service import TASKS_COLLECTION_ENDPOINT, TASK_ITEM_ENDPOINT, route_instruction
from src.app.services.task_store import create_task, delete_task, list_tasks, replace_task, update_task


def build_flow_from_transcription(transcription: str) -> TranscribeFlowResponse:
    instruction = route_instruction(transcription)
    result = execute_instruction(instruction)
    return TranscribeFlowResponse(
        transcription=transcription.strip(),
        instruction=instruction,
        result=result,
    )


async def build_flow_from_audio(upload: UploadFile, language: str | None = None) -> TranscribeFlowResponse:
    transcription = await transcribe_audio(upload, language)
    return build_flow_from_transcription(transcription)


def execute_instruction(instruction: InstructionPayload):
    if instruction.endpoint == TASKS_COLLECTION_ENDPOINT and instruction.method == "GET":
        return list_tasks()

    if instruction.endpoint == TASKS_COLLECTION_ENDPOINT and instruction.method == "POST":
        return create_task(TaskCreate(**instruction.params))

    if instruction.endpoint == TASK_ITEM_ENDPOINT and instruction.method == "PUT":
        params = dict(instruction.params)
        task_id = int(params.pop("task_id"))
        return replace_task(task_id, TaskReplace(**params))

    if instruction.endpoint == TASK_ITEM_ENDPOINT and instruction.method == "PATCH":
        params = dict(instruction.params)
        task_id = int(params.pop("task_id"))
        return update_task(task_id, TaskUpdate(**params))

    if instruction.endpoint == TASK_ITEM_ENDPOINT and instruction.method == "DELETE":
        return delete_task(int(instruction.params["task_id"]))

    raise FlowExecutionError("Instruction could not be executed because the route is unsupported.")


async def transcribe_audio(upload: UploadFile, language: str | None = None) -> str:
    settings = get_settings()
    client = Groq(api_key=settings.groq_api_key, timeout=settings.request_timeout_seconds)
    audio_bytes = await upload.read()

    if not audio_bytes:
        raise AudioTranscriptionError("The uploaded audio file is empty.")

    request_args = {
        "file": (upload.filename or "command.webm", audio_bytes, upload.content_type or "application/octet-stream"),
        "model": settings.groq_transcription_model,
        "temperature": 0,
        "response_format": "verbose_json",
    }
    if language:
        request_args["language"] = language

    try:
        transcription = client.audio.transcriptions.create(**request_args)
    except APIError as exc:
        raise AudioTranscriptionError("Groq request failed while transcribing the audio.") from exc

    text = getattr(transcription, "text", "")
    if not isinstance(text, str) or not text.strip():
        raise AudioTranscriptionError("Groq returned an empty transcription.")
    return text.strip()


class AudioTranscriptionError(Exception):
    pass


class FlowExecutionError(Exception):
    pass
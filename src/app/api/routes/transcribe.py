from fastapi import APIRouter, HTTPException, Request, status
from starlette.datastructures import UploadFile

from src.app.schemas.voice import InstructionRequest
from src.app.schemas.voice import TranscribeFlowResponse
from src.app.services.instruction_service import InstructionRoutingError
from src.app.services.task_store import TaskNotFoundError
from src.app.services.transcribe_flow import (
    AudioTranscriptionError,
    FlowExecutionError,
    build_flow_from_audio,
    build_flow_from_transcription,
)

router = APIRouter(tags=["transcribe"])


@router.get("/")
async def healthcheck() -> dict[str, str]:
    return {"status": "ok"}


@router.post("/transcribe", response_model=TranscribeFlowResponse)
async def transcribe_and_run_flow(request: Request) -> TranscribeFlowResponse:
    content_type = request.headers.get("content-type", "")

    try:
        if "application/json" in content_type:
            payload = InstructionRequest.model_validate(await request.json())
            return build_flow_from_transcription(payload.transcription)

        if "multipart/form-data" in content_type:
            form = await request.form()
            upload = form.get("file")
            language = form.get("language")

            if not isinstance(upload, UploadFile):
                raise HTTPException(
                    status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                    detail="The transcribe endpoint expects a file field in multipart form data.",
                )

            normalized_language = language.strip() if isinstance(language, str) and language.strip() else None
            return await build_flow_from_audio(upload, normalized_language)

        raise HTTPException(
            status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
            detail="Send JSON with a transcription or multipart/form-data with a file.",
        )
    except InstructionRoutingError as exc:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=str(exc)) from exc
    except AudioTranscriptionError as exc:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=str(exc)) from exc
    except FlowExecutionError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    except TaskNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc

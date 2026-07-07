from fastapi import APIRouter, HTTPException, status

from src.app.schemas.voice import InstructionPayload, InstructionRequest
from src.app.services.instruction_service import InstructionRoutingError, route_instruction as route_text_instruction

router = APIRouter(tags=["instruction"])


@router.post("/instruction", response_model=InstructionPayload)
def route_instruction(
    payload: InstructionRequest,
) -> InstructionPayload:
    try:
        return route_text_instruction(payload.transcription)
    except InstructionRoutingError as exc:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=str(exc)) from exc

import json
import re

from groq import APIError, Groq

from src.app.core.config import get_settings
from src.app.schemas.voice import InstructionPayload

ALLOWED_METHODS = {"GET", "POST", "PUT", "PATCH", "DELETE"}
TASKS_COLLECTION_ENDPOINT = "/tasks"
TASK_ITEM_ENDPOINT = "/tasks/{task_id}"
TASK_ITEM_ENDPOINT_PATTERN = re.compile(r"^/tasks/(?P<task_id>\d+)$")

SYSTEM_PROMPT = """
You convert a spoken task-management instruction into routing JSON for a FastAPI backend.

Return one JSON object and nothing else.

Rules:
- Allowed endpoints: /tasks or /tasks/{task_id}
- Allowed methods: GET, POST, PUT, PATCH, DELETE
- Always include params as an object
- For GET /tasks, return params as {}
- For POST /tasks, return params with title and optional done
- For PUT /tasks/{task_id}, return params with task_id, title, and done
- For PATCH /tasks/{task_id}, return params with task_id and only the fields that should change
- For DELETE /tasks/{task_id}, return params with task_id
- task_id must be an integer
- done must be a boolean
- title must be a non-empty string when present
- If the user refers to listing tasks, use GET /tasks
- If the user refers to deleting, completing, updating, or replacing a task, extract the target task_id when spoken
- Never include explanations, markdown, or extra keys
""".strip()


def route_instruction(transcription: str) -> InstructionPayload:
    settings = get_settings()
    client = Groq(api_key=settings.groq_api_key, timeout=settings.request_timeout_seconds)

    try:
        completion = client.chat.completions.create(
            model=settings.groq_model,
            temperature=0,
            response_format={"type": "json_object"},
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": transcription.strip()},
            ],
        )
    except APIError as exc:
        raise InstructionRoutingError("Groq request failed while routing the instruction.") from exc

    content = completion.choices[0].message.content or ""

    try:
        payload = json.loads(content)
    except json.JSONDecodeError as exc:
        raise InstructionRoutingError("Groq returned invalid JSON for the instruction route.") from exc

    return _normalize_instruction_payload(payload)


def _normalize_instruction_payload(payload: object) -> InstructionPayload:
    if not isinstance(payload, dict):
        raise InstructionRoutingError("Instruction payload must be a JSON object.")

    raw_endpoint = str(payload.get("endpoint", "")).strip()
    method = str(payload.get("method", "")).strip().upper()
    raw_params = payload.get("params", {})
    endpoint, endpoint_task_id = _normalize_endpoint(raw_endpoint)

    if method not in ALLOWED_METHODS:
        raise InstructionRoutingError(f"Unsupported method returned by Groq: {method or 'missing'}.")
    if endpoint not in {TASKS_COLLECTION_ENDPOINT, TASK_ITEM_ENDPOINT}:
        raise InstructionRoutingError(f"Unsupported endpoint returned by Groq: {raw_endpoint or 'missing'}.")
    if not isinstance(raw_params, dict):
        raise InstructionRoutingError("Instruction params must be an object.")

    params = dict(raw_params)
    if endpoint_task_id is not None and "task_id" not in params:
        params["task_id"] = endpoint_task_id

    if endpoint == TASKS_COLLECTION_ENDPOINT and method == "GET":
        params = {}
    elif endpoint == TASKS_COLLECTION_ENDPOINT and method == "POST":
        params = _normalize_task_create_params(params)
    elif endpoint == TASK_ITEM_ENDPOINT and method == "PUT":
        params = _normalize_task_replace_params(params)
    elif endpoint == TASK_ITEM_ENDPOINT and method == "PATCH":
        params = _normalize_task_update_params(params)
    elif endpoint == TASK_ITEM_ENDPOINT and method == "DELETE":
        params = {"task_id": _normalize_task_id(params.get("task_id"))}
    else:
        raise InstructionRoutingError("Groq returned an endpoint/method combination that is not supported.")

    return InstructionPayload(endpoint=endpoint, method=method, params=params)


def _normalize_endpoint(endpoint: str) -> tuple[str, int | None]:
    if endpoint == TASKS_COLLECTION_ENDPOINT:
        return endpoint, None
    if endpoint == TASK_ITEM_ENDPOINT:
        return endpoint, None

    match = TASK_ITEM_ENDPOINT_PATTERN.fullmatch(endpoint)
    if match:
        return TASK_ITEM_ENDPOINT, int(match.group("task_id"))

    return endpoint, None


def _normalize_task_create_params(params: dict[str, object]) -> dict[str, object]:
    title = _normalize_title(params.get("title"))
    done = _normalize_done(params.get("done", False))
    return {"title": title, "done": done}


def _normalize_task_replace_params(params: dict[str, object]) -> dict[str, object]:
    return {
        "task_id": _normalize_task_id(params.get("task_id")),
        "title": _normalize_title(params.get("title")),
        "done": _normalize_done(params.get("done")),
    }


def _normalize_task_update_params(params: dict[str, object]) -> dict[str, object]:
    normalized: dict[str, object] = {"task_id": _normalize_task_id(params.get("task_id"))}

    if "title" in params and params.get("title") is not None:
        normalized["title"] = _normalize_title(params.get("title"))
    if "done" in params and params.get("done") is not None:
        normalized["done"] = _normalize_done(params.get("done"))
    if len(normalized) == 1:
        raise InstructionRoutingError("PATCH instructions must include at least one field to update.")
    return normalized


def _normalize_task_id(value: object) -> int:
    if isinstance(value, bool):
        raise InstructionRoutingError("task_id must be an integer.")
    try:
        task_id = int(value)
    except (TypeError, ValueError) as exc:
        raise InstructionRoutingError("task_id must be an integer.") from exc
    if task_id < 1:
        raise InstructionRoutingError("task_id must be greater than zero.")
    return task_id


def _normalize_title(value: object) -> str:
    if not isinstance(value, str) or not value.strip():
        raise InstructionRoutingError("title must be a non-empty string.")
    return value.strip()


def _normalize_done(value: object) -> bool:
    if isinstance(value, bool):
        return value
    raise InstructionRoutingError("done must be a boolean.")


class InstructionRoutingError(Exception):
    pass
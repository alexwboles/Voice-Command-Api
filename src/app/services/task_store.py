from src.app.schemas.voice import Task, TaskCreate, TaskReplace, TaskUpdate


tasks: list[Task] = []
_next_task_id = 1


def list_tasks() -> list[Task]:
    return list(tasks)


def create_task(payload: TaskCreate) -> Task:
    global _next_task_id

    task = Task(id=_next_task_id, title=payload.title.strip(), done=payload.done)
    tasks.append(task)
    _next_task_id += 1
    return task


def replace_task(task_id: int, payload: TaskReplace) -> Task:
    index = _find_task_index(task_id)
    task = Task(id=task_id, title=payload.title.strip(), done=payload.done)
    tasks[index] = task
    return task


def update_task(task_id: int, payload: TaskUpdate) -> Task:
    index = _find_task_index(task_id)
    current = tasks[index]
    updated_task = current.model_copy(
        update={
            "title": payload.title.strip() if payload.title is not None else current.title,
            "done": payload.done if payload.done is not None else current.done,
        }
    )
    tasks[index] = updated_task
    return updated_task


def delete_task(task_id: int) -> dict[str, str]:
    index = _find_task_index(task_id)
    deleted = tasks.pop(index)
    return {"message": f"Task {deleted.id} deleted successfully."}


def get_task(task_id: int) -> Task:
    return tasks[_find_task_index(task_id)]


def reset_tasks() -> None:
    global _next_task_id
    tasks.clear()
    _next_task_id = 1


def _find_task_index(task_id: int) -> int:
    for index, task in enumerate(tasks):
        if task.id == task_id:
            return index
    raise TaskNotFoundError(task_id)


class TaskNotFoundError(Exception):
    def __init__(self, task_id: int) -> None:
        super().__init__(f"Task {task_id} was not found.")
        self.task_id = task_id
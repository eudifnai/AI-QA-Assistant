import asyncio
import logging
from uuid import uuid4

from fastapi import APIRouter, WebSocket
from starlette.websockets import WebSocketDisconnect, WebSocketState

from backend.app.application.task_events import TaskEventUseCases
from backend.app.core.errors import AppError
from backend.app.schemas.task_events import TaskSnapshotResponse, TaskStreamEventResponse

TASK_EVENT_PROTOCOL = "ai-qa-task-events"
logger = logging.getLogger(__name__)


def _offered_protocols(websocket: WebSocket) -> tuple[str, ...]:
    return tuple(
        item.strip()
        for item in websocket.headers.get("sec-websocket-protocol", "").split(",")
        if item.strip()
    )


def create_task_event_router(
    service: TaskEventUseCases,
    *,
    poll_interval_seconds: float = 0.25,
) -> APIRouter:
    router = APIRouter(tags=["task-events"])

    @router.websocket("/api/workspaces/{workspace_id}/task-events")
    async def task_events(websocket: WebSocket, workspace_id: str) -> None:
        if TASK_EVENT_PROTOCOL not in _offered_protocols(websocket):
            await websocket.close(code=1002, reason="任务事件协议无效。")
            return
        try:
            initial = await asyncio.to_thread(service.list_snapshots, workspace_id)
        except AppError:
            await websocket.close(code=1008, reason="无法订阅该工作空间的任务事件。")
            return
        except Exception as exception:
            logger.error(
                "Task event subscription failed",
                extra={"workspace_id": workspace_id, "error_type": type(exception).__name__},
            )
            await websocket.close(code=1011, reason="任务事件流暂时不可用。")
            return
        await websocket.accept(subprotocol=TASK_EVENT_PROTOCOL)
        stream_id = str(uuid4())
        sequence = 1
        previous = {item.key: item.fingerprint for item in initial}
        await websocket.send_json(
            TaskStreamEventResponse(
                stream_id=stream_id,
                sequence=sequence,
                kind="stream_ready",
                task=None,
            ).model_dump(mode="json")
        )
        try:
            while True:
                try:
                    message = await asyncio.wait_for(
                        websocket.receive(), timeout=poll_interval_seconds
                    )
                    if message["type"] == "websocket.disconnect":
                        return
                    await websocket.close(code=1003, reason="任务事件流不接受客户端消息。")
                    return
                except TimeoutError:
                    pass
                current_items = await asyncio.to_thread(service.list_snapshots, workspace_id)
                current = {item.key: item.fingerprint for item in current_items}
                for item in current_items:
                    if previous.get(item.key) == item.fingerprint:
                        continue
                    sequence += 1
                    await websocket.send_json(
                        TaskStreamEventResponse(
                            stream_id=stream_id,
                            sequence=sequence,
                            kind="task_updated",
                            task=TaskSnapshotResponse.from_domain(item),
                        ).model_dump(mode="json")
                    )
                previous = current
        except WebSocketDisconnect:
            return
        except Exception as exception:
            logger.error(
                "Task event stream failed",
                extra={"workspace_id": workspace_id, "error_type": type(exception).__name__},
            )
            if websocket.client_state == WebSocketState.CONNECTED:
                await websocket.close(code=1011, reason="任务事件流暂时不可用。")

    return router

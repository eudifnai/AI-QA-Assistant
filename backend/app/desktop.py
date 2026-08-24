import json
import multiprocessing
import os
import secrets
import socket
import sys
import time
from pathlib import Path

import uvicorn

from backend.app.core.config import get_settings
from backend.app.core.logging import configure_logging
from backend.app.core.network import API_LOOPBACK_HOST
from backend.app.infrastructure.database_migrations import upgrade_database

STARTUP_MESSAGE_TYPE = "backend_ready"
PARENT_HEARTBEAT_ENVIRONMENT_VARIABLE = "AI_QA_PARENT_HEARTBEAT_PATH"
PARENT_HEARTBEAT_TIMEOUT_SECONDS = 5.0


def generate_session_token() -> str:
    return secrets.token_urlsafe(32)


def create_startup_message(*, port: int, token: str) -> str:
    return json.dumps(
        {"type": STARTUP_MESSAGE_TYPE, "port": port, "token": token},
        ensure_ascii=True,
        separators=(",", ":"),
    )


def parent_heartbeat_is_current(
    heartbeat_path: Path,
    *,
    current_time: float | None = None,
) -> bool:
    try:
        modified_at = heartbeat_path.stat().st_mtime
    except OSError:
        return False
    now = time.time() if current_time is None else current_time
    return now - modified_at <= PARENT_HEARTBEAT_TIMEOUT_SECONDS


class DesktopServer(uvicorn.Server):
    def __init__(
        self,
        config: uvicorn.Config,
        session_token: str,
        parent_heartbeat_path: Path,
    ) -> None:
        super().__init__(config)
        self._session_token = session_token
        self._parent_heartbeat_path = parent_heartbeat_path

    async def on_tick(self, counter: int) -> bool:
        if await super().on_tick(counter):
            return True
        if not parent_heartbeat_is_current(self._parent_heartbeat_path):
            self.should_exit = True
        return self.should_exit

    async def startup(self, sockets: list[socket.socket] | None = None) -> None:
        await super().startup(sockets=sockets)
        if self.should_exit:
            return
        listeners = [
            listener
            for server in self.servers
            for listener in (server.sockets or ())
            if listener.family == socket.AF_INET
        ]
        if len(listeners) != 1:
            raise RuntimeError("本地后端回环监听器初始化失败。")
        host, port = listeners[0].getsockname()
        if host != API_LOOPBACK_HOST or not 1024 <= port <= 65535:
            raise RuntimeError("本地后端回环监听器校验失败。")
        os.environ["AI_QA_API_PORT"] = str(port)
        print(create_startup_message(port=port, token=self._session_token), flush=True)


def main() -> None:
    token = generate_session_token()
    os.environ["AI_QA_SESSION_TOKEN"] = token
    get_settings.cache_clear()

    from backend.app.main import create_app

    settings = get_settings()
    parent_heartbeat_value = os.environ.get(PARENT_HEARTBEAT_ENVIRONMENT_VARIABLE)
    if not parent_heartbeat_value:
        raise RuntimeError("Electron 父进程心跳路径未配置。")
    configure_logging()
    upgrade_database(settings.database_url)
    server = DesktopServer(
        uvicorn.Config(
            create_app(settings=settings),
            host=API_LOOPBACK_HOST,
            port=0,
            reload=False,
            log_config=None,
        ),
        token,
        Path(parent_heartbeat_value),
    )
    server.run()


if __name__ == "__main__":
    multiprocessing.freeze_support()
    if len(sys.argv) > 1 and sys.argv[1] == "--grpc-tools-protoc":
        from grpc_tools.protoc import main as protoc_main  # type: ignore[import-untyped]

        raise SystemExit(protoc_main([sys.argv[0], *sys.argv[2:]]))
    main()

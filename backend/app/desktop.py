import argparse
import ctypes
import json
import os
import secrets
import socket
import threading
import time

import uvicorn

from backend.app.core.config import get_settings
from backend.app.core.logging import configure_logging

STARTUP_MESSAGE_TYPE = "backend_ready"
PARENT_CHECK_INTERVAL_SECONDS = 1.0


def generate_session_token() -> str:
    return secrets.token_urlsafe(32)


def open_loopback_socket() -> socket.socket:
    listener = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    try:
        listener.bind(("127.0.0.1", 0))
        listener.listen(2048)
    except BaseException:
        listener.close()
        raise
    return listener


def create_startup_message(*, port: int, token: str) -> str:
    return json.dumps(
        {"type": STARTUP_MESSAGE_TYPE, "port": port, "token": token},
        ensure_ascii=True,
        separators=(",", ":"),
    )


def parent_process_is_alive(parent_pid: int) -> bool:
    if os.name != "nt":
        try:
            os.kill(parent_pid, 0)
        except OSError:
            return False
        return True

    synchronize = 0x00100000
    wait_timeout = 0x00000102
    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    open_process = kernel32.OpenProcess
    open_process.argtypes = [ctypes.c_uint32, ctypes.c_int, ctypes.c_uint32]
    open_process.restype = ctypes.c_void_p
    wait_for_single_object = kernel32.WaitForSingleObject
    wait_for_single_object.argtypes = [ctypes.c_void_p, ctypes.c_uint32]
    wait_for_single_object.restype = ctypes.c_uint32
    close_handle = kernel32.CloseHandle
    close_handle.argtypes = [ctypes.c_void_p]
    close_handle.restype = ctypes.c_int

    handle = open_process(synchronize, 0, parent_pid)
    if handle is None:
        return False
    try:
        return int(wait_for_single_object(handle, 0)) == wait_timeout
    finally:
        close_handle(handle)


def monitor_parent_process(parent_pid: int, server: uvicorn.Server) -> None:
    while not server.should_exit:
        if not parent_process_is_alive(parent_pid):
            server.should_exit = True
            return
        time.sleep(PARENT_CHECK_INTERVAL_SECONDS)


def parse_parent_pid() -> int:
    parser = argparse.ArgumentParser(add_help=False)
    parser.add_argument("--parent-pid", type=int, required=True)
    arguments = parser.parse_args()
    if arguments.parent_pid <= 0:
        parser.error("--parent-pid must be positive")
    return int(arguments.parent_pid)


def main() -> None:
    parent_pid = parse_parent_pid()
    listener = open_loopback_socket()
    token = generate_session_token()
    _, port = listener.getsockname()
    os.environ["AI_QA_API_PORT"] = str(port)
    os.environ["AI_QA_SESSION_TOKEN"] = token
    get_settings.cache_clear()

    try:
        from backend.app.main import create_app

        settings = get_settings()
        configure_logging()
        server = uvicorn.Server(
            uvicorn.Config(
                create_app(settings=settings),
                host=settings.api_host,
                port=settings.api_port,
                reload=False,
                log_config=None,
            )
        )
        threading.Thread(
            target=monitor_parent_process,
            args=(parent_pid, server),
            daemon=True,
            name="desktop-parent-monitor",
        ).start()
        print(create_startup_message(port=port, token=token), flush=True)
        server.run(sockets=[listener])
    finally:
        listener.close()


if __name__ == "__main__":
    main()

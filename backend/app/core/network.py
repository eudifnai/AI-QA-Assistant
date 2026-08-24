from typing import Final

API_LOOPBACK_HOST: Final = "127.0.0.1"


def validate_api_bind_host(host: str) -> str:
    if host != API_LOOPBACK_HOST:
        raise ValueError("本地 API 只允许绑定 127.0.0.1。")
    return host

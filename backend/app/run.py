import uvicorn

from backend.app.core.config import get_settings
from backend.app.core.logging import configure_logging


def main() -> None:
    settings = get_settings()
    configure_logging()
    uvicorn.run(
        "backend.app.main:app",
        host=settings.api_host,
        port=settings.api_port,
        reload=False,
        log_config=None,
    )


if __name__ == "__main__":
    main()

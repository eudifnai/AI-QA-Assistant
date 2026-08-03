from pathlib import Path

from sqlalchemy.engine import Engine, make_url
from sqlmodel import create_engine


def ensure_sqlite_parent(database_url: str) -> None:
    url = make_url(database_url)
    if url.drivername != "sqlite" or not url.database or url.database == ":memory:":
        return

    database_path = Path(url.database)
    database_path.parent.mkdir(parents=True, exist_ok=True)


def create_database_engine(database_url: str) -> Engine:
    ensure_sqlite_parent(database_url)
    connect_args = {"check_same_thread": False} if database_url.startswith("sqlite") else {}
    return create_engine(database_url, connect_args=connect_args)

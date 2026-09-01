from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime
from pathlib import Path
from threading import Barrier, Lock

from sqlalchemy import event

from backend.app.application.settings import SettingsService
from backend.app.infrastructure.database import create_database_engine
from backend.app.infrastructure.database_migrations import upgrade_database
from backend.app.infrastructure.settings import SqlModelSettingsRepository

NOW = datetime(2026, 8, 31, 1, 0, tzinfo=UTC)


def test_concurrent_first_read_initializes_one_settings_record(tmp_path: Path) -> None:
    database_url = f"sqlite:///{(tmp_path / 'settings-race.db').as_posix()}"
    upgrade_database(database_url)
    engine = create_database_engine(database_url)
    repository = SqlModelSettingsRepository(engine)
    service = SettingsService(repository, clock=lambda: NOW)
    first_read_barrier = Barrier(2)
    first_insert_barrier = Barrier(2)
    counter_lock = Lock()
    settings_select_count = 0
    settings_insert_count = 0

    def synchronize_first_read_and_create(
        _connection: object,
        _cursor: object,
        statement: str,
        _parameters: object,
        _context: object,
        _executemany: object,
    ) -> None:
        nonlocal settings_select_count
        normalized_statement = statement.lstrip().upper()
        if (
            not normalized_statement.startswith("SELECT")
            or "APP_SETTINGS" not in normalized_statement
        ):
            return
        with counter_lock:
            settings_select_count += 1
            should_wait = settings_select_count <= 2
        if should_wait:
            first_read_barrier.wait(timeout=5)

    def synchronize_first_insert(
        _connection: object,
        _cursor: object,
        statement: str,
        _parameters: object,
        _context: object,
        _executemany: object,
    ) -> None:
        nonlocal settings_insert_count
        normalized_statement = statement.lstrip().upper()
        if (
            not normalized_statement.startswith("INSERT")
            or "APP_SETTINGS" not in normalized_statement
        ):
            return
        with counter_lock:
            settings_insert_count += 1
            should_wait = settings_insert_count <= 2
        if should_wait:
            first_insert_barrier.wait(timeout=5)

    event.listen(engine, "after_cursor_execute", synchronize_first_read_and_create)
    event.listen(engine, "before_cursor_execute", synchronize_first_insert)
    try:
        with ThreadPoolExecutor(max_workers=2) as executor:
            futures = [executor.submit(service.get) for _ in range(2)]
            settings = [future.result(timeout=10) for future in futures]
    finally:
        event.remove(engine, "after_cursor_execute", synchronize_first_read_and_create)
        event.remove(engine, "before_cursor_execute", synchronize_first_insert)
        engine.dispose()

    assert settings == [settings[0], settings[0]]

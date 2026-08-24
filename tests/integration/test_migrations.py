import sqlite3
from pathlib import Path

from alembic import command
from alembic.config import Config


def migration_config(database_path: Path) -> Config:
    config = Config("alembic.ini")
    config.set_main_option("sqlalchemy.url", f"sqlite:///{database_path.as_posix()}")
    return config


def current_revision(database_path: Path) -> str | None:
    with sqlite3.connect(database_path) as connection:
        row = connection.execute("SELECT version_num FROM alembic_version").fetchone()
    return None if row is None else str(row[0])


def test_initial_migration_can_upgrade_downgrade_and_upgrade_again(tmp_path: Path) -> None:
    database_path = tmp_path / "migration-test.db"
    config = migration_config(database_path)

    command.upgrade(config, "head")
    first_revision = current_revision(database_path)
    assert first_revision is not None

    command.downgrade(config, "base")
    assert current_revision(database_path) is None

    command.upgrade(config, "head")
    assert current_revision(database_path) == first_revision


def test_workspace_migration_creates_expected_constraints(tmp_path: Path) -> None:
    database_path = tmp_path / "workspace-migration.db"
    command.upgrade(migration_config(database_path), "head")

    with sqlite3.connect(database_path) as connection:
        columns = {
            str(row[1]) for row in connection.execute("PRAGMA table_info(workspaces)").fetchall()
        }
        indexes = {
            str(row[1]) for row in connection.execute("PRAGMA index_list(workspaces)").fetchall()
        }

    assert columns == {
        "id",
        "name",
        "name_key",
        "path",
        "path_key",
        "created_at",
        "last_opened_at",
    }
    assert {"ix_workspaces_name_key", "ix_workspaces_path_key"} <= indexes


def test_settings_migration_creates_singleton_table_without_secret_columns(tmp_path: Path) -> None:
    database_path = tmp_path / "settings-migration.db"
    command.upgrade(migration_config(database_path), "head")

    with sqlite3.connect(database_path) as connection:
        columns = {
            str(row[1]) for row in connection.execute("PRAGMA table_info(app_settings)").fetchall()
        }

    assert columns == {
        "id",
        "theme",
        "model_mode",
        "model_provider",
        "model_name",
        "base_url",
        "cloud_data_consent",
        "updated_at",
    }
    assert not {"api_key", "token", "password", "credential"} & columns


def test_document_migration_creates_version_and_job_constraints(tmp_path: Path) -> None:
    database_path = tmp_path / "documents-migration.db"
    command.upgrade(migration_config(database_path), "head")

    with sqlite3.connect(database_path) as connection:
        tables = {
            str(row[0])
            for row in connection.execute(
                "SELECT name FROM sqlite_master WHERE type = 'table'"
            ).fetchall()
        }
        version_indexes = {
            str(row[1])
            for row in connection.execute("PRAGMA index_list(document_versions)").fetchall()
        }

    assert {"documents", "document_versions", "document_jobs"} <= tables
    assert "uq_document_versions_workspace_hash" in version_indexes


def test_document_chunk_migration_creates_reference_constraints(tmp_path: Path) -> None:
    database_path = tmp_path / "document-chunks-migration.db"
    command.upgrade(migration_config(database_path), "head")

    with sqlite3.connect(database_path) as connection:
        columns = {
            str(row[1])
            for row in connection.execute("PRAGMA table_info(document_chunks)").fetchall()
        }
        indexes = {
            str(row[1])
            for row in connection.execute("PRAGMA index_list(document_chunks)").fetchall()
        }

    assert columns == {
        "id",
        "version_id",
        "ordinal",
        "source_type",
        "source_start",
        "source_end",
        "start_offset",
        "end_offset",
        "text",
    }
    assert "uq_document_chunks_version_ordinal" in indexes


def test_document_chunk_migration_backfills_passed_versions(tmp_path: Path) -> None:
    database_path = tmp_path / "document-chunks-backfill.db"
    config = migration_config(database_path)
    command.upgrade(config, "20260810_0004")
    timestamp = "2026-08-11 00:00:00"
    with sqlite3.connect(database_path) as connection:
        connection.execute(
            """
            INSERT INTO workspaces (
                id, name, name_key, path, path_key, created_at, last_opened_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                "workspace-1",
                "支付",
                "支付",
                "C:/qa/pay",
                "c:/qa/pay",
                timestamp,
                timestamp,
            ),
        )
        connection.execute(
            """
            INSERT INTO documents (
                id, workspace_id, name, relative_path, path_key, created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                "document-1",
                "workspace-1",
                "requirements.md",
                "requirements.md",
                "requirements.md",
                timestamp,
                timestamp,
            ),
        )
        connection.execute(
            """
            INSERT INTO document_versions (
                id, document_id, workspace_id, version_number, sha256, size_bytes,
                status, parsed_text, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                "version-1",
                "document-1",
                "workspace-1",
                1,
                "a" * 64,
                12,
                "passed",
                "旧版解析文本",
                timestamp,
            ),
        )
        connection.commit()

    command.upgrade(config, "head")

    with sqlite3.connect(database_path) as connection:
        row = connection.execute(
            """
            SELECT id, version_id, ordinal, source_type, start_offset, end_offset, text
            FROM document_chunks
            """
        ).fetchone()

    assert row == ("version-1", "version-1", 1, "document", 0, 6, "旧版解析文本")


def test_analysis_migration_creates_run_issue_score_and_citation_tables(tmp_path: Path) -> None:
    database_path = tmp_path / "analysis-migration.db"
    command.upgrade(migration_config(database_path), "head")

    with sqlite3.connect(database_path) as connection:
        tables = {
            str(row[0])
            for row in connection.execute(
                "SELECT name FROM sqlite_master WHERE type = 'table'"
            ).fetchall()
        }
        run_indexes = {
            str(row[1]) for row in connection.execute("PRAGMA index_list(analysis_runs)").fetchall()
        }
        citation_indexes = {
            str(row[1])
            for row in connection.execute("PRAGMA index_list(analysis_citations)").fetchall()
        }
        run_columns = {
            str(row[1]) for row in connection.execute("PRAGMA table_info(analysis_runs)").fetchall()
        }

    assert {
        "analysis_runs",
        "analysis_scores",
        "analysis_issues",
        "analysis_citations",
    } <= tables
    assert "ix_analysis_runs_document_created" in run_indexes
    assert "uq_analysis_citations_issue_ordinal" in citation_indexes
    assert {
        "input_chunk_count",
        "input_character_count",
        "cloud_data_confirmed_at",
    } <= run_columns


def test_analysis_audit_migration_backfills_existing_input_scope(tmp_path: Path) -> None:
    database_path = tmp_path / "analysis-audit-backfill.db"
    config = migration_config(database_path)
    command.upgrade(config, "20260812_0006")
    timestamp = "2026-08-12 00:00:00"
    with sqlite3.connect(database_path) as connection:
        connection.execute(
            """
            INSERT INTO workspaces (
                id, name, name_key, path, path_key, created_at, last_opened_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            ("workspace-1", "支付", "支付", "C:/qa/pay", "c:/qa/pay", timestamp, timestamp),
        )
        connection.execute(
            """
            INSERT INTO documents (
                id, workspace_id, name, relative_path, path_key, created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                "document-1",
                "workspace-1",
                "requirements.md",
                "requirements.md",
                "requirements.md",
                timestamp,
                timestamp,
            ),
        )
        connection.execute(
            """
            INSERT INTO document_versions (
                id, document_id, workspace_id, version_number, sha256, size_bytes,
                status, parsed_text, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                "version-1",
                "document-1",
                "workspace-1",
                1,
                "a" * 64,
                10,
                "passed",
                "需求文本",
                timestamp,
            ),
        )
        connection.executemany(
            """
            INSERT INTO document_chunks (
                id, version_id, ordinal, source_type, source_start, source_end,
                start_offset, end_offset, text
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            [
                ("chunk-1", "version-1", 1, "lines", 1, 1, 0, 4, "需求文本"),
                ("chunk-2", "version-1", 2, "lines", 2, 2, 4, 6, "补充"),
            ],
        )
        connection.execute(
            """
            INSERT INTO analysis_runs (
                id, workspace_id, document_id, version_id, provider, model_name,
                base_url, status, progress, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                "run-1",
                "workspace-1",
                "document-1",
                "version-1",
                "ollama",
                "qwen3:8b",
                "http://127.0.0.1:11434",
                "passed",
                100,
                timestamp,
            ),
        )
        connection.commit()

    command.upgrade(config, "head")

    with sqlite3.connect(database_path) as connection:
        row = connection.execute(
            """
            SELECT input_chunk_count, input_character_count, cloud_data_confirmed_at
            FROM analysis_runs WHERE id = 'run-1'
            """
        ).fetchone()

    assert row == (2, 6, None)


def test_test_design_migration_creates_traceability_constraints(tmp_path: Path) -> None:
    database_path = tmp_path / "test-design-migration.db"
    command.upgrade(migration_config(database_path), "head")

    with sqlite3.connect(database_path) as connection:
        tables = {
            str(row[0])
            for row in connection.execute(
                "SELECT name FROM sqlite_master WHERE type = 'table'"
            ).fetchall()
        }
        review_indexes = {
            str(row[1]): bool(row[2])
            for row in connection.execute("PRAGMA index_list(analysis_issue_reviews)").fetchall()
        }
        point_indexes = {
            str(row[1]): bool(row[2])
            for row in connection.execute("PRAGMA index_list(test_points)").fetchall()
        }
        review_foreign_keys = {
            (str(row[3]), str(row[2]), str(row[4]), str(row[6]))
            for row in connection.execute(
                "PRAGMA foreign_key_list(analysis_issue_reviews)"
            ).fetchall()
        }
        point_foreign_keys = {
            (str(row[3]), str(row[2]), str(row[4]), str(row[6]))
            for row in connection.execute("PRAGMA foreign_key_list(test_points)").fetchall()
        }

    assert {"analysis_issue_reviews", "test_points"} <= tables
    assert review_indexes["uq_analysis_issue_reviews_issue"] is True
    assert point_indexes["uq_test_points_source_issue"] is True
    assert ("issue_id", "analysis_issues", "id", "CASCADE") in review_foreign_keys
    assert ("run_id", "analysis_runs", "id", "CASCADE") in review_foreign_keys
    assert ("source_issue_id", "analysis_issues", "id", "CASCADE") in point_foreign_keys
    assert ("run_id", "analysis_runs", "id", "CASCADE") in point_foreign_keys


def test_test_case_migration_creates_source_and_step_constraints(tmp_path: Path) -> None:
    database_path = tmp_path / "test-case-migration.db"
    command.upgrade(migration_config(database_path), "head")

    with sqlite3.connect(database_path) as connection:
        tables = {
            str(row[0])
            for row in connection.execute(
                "SELECT name FROM sqlite_master WHERE type = 'table'"
            ).fetchall()
        }
        case_indexes = {
            str(row[1]): bool(row[2])
            for row in connection.execute("PRAGMA index_list(test_cases)").fetchall()
        }
        step_indexes = {
            str(row[1]): bool(row[2])
            for row in connection.execute("PRAGMA index_list(test_case_steps)").fetchall()
        }
        case_foreign_keys = {
            (str(row[3]), str(row[2]), str(row[4]), str(row[6]))
            for row in connection.execute("PRAGMA foreign_key_list(test_cases)").fetchall()
        }
        step_foreign_keys = {
            (str(row[3]), str(row[2]), str(row[4]), str(row[6]))
            for row in connection.execute("PRAGMA foreign_key_list(test_case_steps)").fetchall()
        }

    assert {"test_cases", "test_case_steps"} <= tables
    assert case_indexes["uq_test_cases_source_point"] is True
    assert step_indexes["uq_test_case_steps_case_ordinal"] is True
    assert ("source_test_point_id", "test_points", "id", "CASCADE") in case_foreign_keys
    assert ("run_id", "analysis_runs", "id", "CASCADE") in case_foreign_keys
    assert ("test_case_id", "test_cases", "id", "CASCADE") in step_foreign_keys


def test_http_execution_migration_separates_secret_values_from_sqlite(tmp_path: Path) -> None:
    database_path = tmp_path / "http-execution-migration.db"
    command.upgrade(migration_config(database_path), "head")

    with sqlite3.connect(database_path) as connection:
        tables = {
            str(row[0])
            for row in connection.execute(
                "SELECT name FROM sqlite_master WHERE type = 'table'"
            ).fetchall()
        }
        environment_columns = {
            str(row[1])
            for row in connection.execute("PRAGMA table_info(http_environments)").fetchall()
        }
        execution_columns = {
            str(row[1])
            for row in connection.execute("PRAGMA table_info(http_executions)").fetchall()
        }
        environment_indexes = {
            str(row[1]): bool(row[2])
            for row in connection.execute("PRAGMA index_list(http_environments)").fetchall()
        }
        execution_foreign_keys = {
            (str(row[3]), str(row[2]), str(row[4]), str(row[6]))
            for row in connection.execute("PRAGMA foreign_key_list(http_executions)").fetchall()
        }

    assert {"http_environments", "http_executions"} <= tables
    assert environment_indexes["uq_http_environments_workspace_name"] is True
    assert ("environment_id", "http_environments", "id", "SET NULL") in execution_foreign_keys
    assert {"variables_json", "secret_names_json"} <= environment_columns
    assert {"headers_template_json", "response_headers_json"} <= execution_columns
    assert not {
        "secret",
        "secret_value",
        "api_key",
        "password",
        "token",
        "authorization",
    } & (environment_columns | execution_columns)


def test_http_assertion_migration_adds_retry_results_and_event_constraints(
    tmp_path: Path,
) -> None:
    database_path = tmp_path / "http-assertion-migration.db"
    command.upgrade(migration_config(database_path), "head")

    with sqlite3.connect(database_path) as connection:
        execution_columns = {
            str(row[1])
            for row in connection.execute("PRAGMA table_info(http_executions)").fetchall()
        }
        event_indexes = {
            str(row[1]): bool(row[2])
            for row in connection.execute("PRAGMA index_list(http_execution_events)").fetchall()
        }
        event_foreign_keys = {
            (str(row[3]), str(row[2]), str(row[4]), str(row[6]))
            for row in connection.execute(
                "PRAGMA foreign_key_list(http_execution_events)"
            ).fetchall()
        }

    assert {"max_attempts", "assertions_json", "assertion_results_json"} <= execution_columns
    assert event_indexes["uq_http_execution_events_run_ordinal"] is True
    assert ("run_id", "http_executions", "id", "CASCADE") in event_foreign_keys


def test_websocket_execution_migration_adds_frozen_runs_and_ordered_events(
    tmp_path: Path,
) -> None:
    database_path = tmp_path / "websocket-execution-migration.db"
    command.upgrade(migration_config(database_path), "head")

    with sqlite3.connect(database_path) as connection:
        tables = {
            str(row[0])
            for row in connection.execute(
                "SELECT name FROM sqlite_master WHERE type = 'table'"
            ).fetchall()
        }
        run_columns = {
            str(row[1])
            for row in connection.execute("PRAGMA table_info(websocket_executions)").fetchall()
        }
        event_indexes = {
            str(row[1]): bool(row[2])
            for row in connection.execute(
                "PRAGMA index_list(websocket_execution_events)"
            ).fetchall()
        }
        run_foreign_keys = {
            (str(row[3]), str(row[2]), str(row[4]), str(row[6]))
            for row in connection.execute(
                "PRAGMA foreign_key_list(websocket_executions)"
            ).fetchall()
        }

    assert {"websocket_executions", "websocket_execution_events"} <= tables
    assert {"headers_template_json", "variables_json", "secret_names_json"} <= run_columns
    assert not {"secret", "secret_value", "password", "token", "authorization"} & run_columns
    assert event_indexes["uq_websocket_execution_events_run_ordinal"] is True
    assert ("environment_id", "http_environments", "id", "SET NULL") in run_foreign_keys


def test_proto_asset_migration_adds_versioned_descriptors(tmp_path: Path) -> None:
    database_path = tmp_path / "proto-asset-migration.db"
    command.upgrade(migration_config(database_path), "head")

    with sqlite3.connect(database_path) as connection:
        columns = {
            str(row[1]) for row in connection.execute("PRAGMA table_info(proto_assets)").fetchall()
        }
        indexes = {
            str(row[1]): bool(row[2])
            for row in connection.execute("PRAGMA index_list(proto_assets)").fetchall()
        }
        foreign_keys = {
            (str(row[3]), str(row[2]), str(row[4]), str(row[6]))
            for row in connection.execute("PRAGMA foreign_key_list(proto_assets)").fetchall()
        }

    assert {"relative_path", "path_key", "sha256", "descriptor_set"} <= columns
    assert indexes["uq_proto_assets_workspace_path"] is True
    assert indexes["uq_proto_assets_workspace_hash"] is True
    assert ("workspace_id", "workspaces", "id", "CASCADE") in foreign_keys


def test_protobuf_execution_migration_freezes_descriptor_without_secret_values(
    tmp_path: Path,
) -> None:
    database_path = tmp_path / "protobuf-execution-migration.db"
    command.upgrade(migration_config(database_path), "head")

    with sqlite3.connect(database_path) as connection:
        tables = {
            str(row[0])
            for row in connection.execute(
                "SELECT name FROM sqlite_master WHERE type = 'table'"
            ).fetchall()
        }
        columns = {
            str(row[1])
            for row in connection.execute("PRAGMA table_info(protobuf_executions)").fetchall()
        }
        event_indexes = {
            str(row[1]): bool(row[2])
            for row in connection.execute("PRAGMA index_list(protobuf_execution_events)").fetchall()
        }
        foreign_keys = {
            (str(row[3]), str(row[2]), str(row[4]), str(row[6]))
            for row in connection.execute("PRAGMA foreign_key_list(protobuf_executions)").fetchall()
        }

    assert {"protobuf_executions", "protobuf_execution_events"} <= tables
    assert {
        "asset_sha256",
        "descriptor_set",
        "request_payload_json",
        "assertions_json",
        "assertion_results_json",
    } <= columns
    assert not {"secret", "secret_value", "password", "token", "authorization"} & columns
    assert event_indexes["uq_protobuf_execution_events_run_ordinal"] is True
    assert ("environment_id", "http_environments", "id", "SET NULL") in foreign_keys
    assert ("asset_id", "proto_assets", "id", "SET NULL") in foreign_keys


def test_websocket_sequence_migration_adds_heartbeat_reconnect_and_assertion_snapshots(
    tmp_path: Path,
) -> None:
    database_path = tmp_path / "websocket-sequence-migration.db"
    command.upgrade(migration_config(database_path), "head")

    with sqlite3.connect(database_path) as connection:
        columns = {
            str(row[1])
            for row in connection.execute("PRAGMA table_info(websocket_executions)").fetchall()
        }

    assert {
        "additional_messages_json",
        "receive_count",
        "ping_interval_seconds",
        "max_reconnect_attempts",
        "responses_json",
        "assertions_json",
        "assertion_results_json",
        "attempt_count",
    } <= columns

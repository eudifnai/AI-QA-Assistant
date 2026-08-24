from datetime import UTC, datetime

from sqlalchemy import Column, DateTime, String
from sqlalchemy.engine import Engine
from sqlalchemy.exc import IntegrityError
from sqlmodel import Field, Session, SQLModel, col, select

from backend.app.domain.workspace import Workspace, WorkspaceConflictError


class WorkspaceRecord(SQLModel, table=True):
    __tablename__ = "workspaces"

    id: str = Field(sa_column=Column(String(36), primary_key=True))
    name: str = Field(sa_column=Column(String(80), nullable=False))
    name_key: str = Field(sa_column=Column(String(80), nullable=False, unique=True, index=True))
    path: str = Field(sa_column=Column(String(1024), nullable=False))
    path_key: str = Field(sa_column=Column(String(1024), nullable=False, unique=True, index=True))
    created_at: datetime = Field(sa_column=Column(DateTime(timezone=True), nullable=False))
    last_opened_at: datetime = Field(sa_column=Column(DateTime(timezone=True), nullable=False))


def _as_utc(value: datetime) -> datetime:
    return value.replace(tzinfo=UTC) if value.tzinfo is None else value.astimezone(UTC)


def _to_domain(record: WorkspaceRecord) -> Workspace:
    return Workspace(
        id=record.id,
        name=record.name,
        path=record.path,
        created_at=_as_utc(record.created_at),
        last_opened_at=_as_utc(record.last_opened_at),
    )


class SqlModelWorkspaceRepository:
    def __init__(self, engine: Engine) -> None:
        self._engine = engine

    def list(self) -> list[Workspace]:
        with Session(self._engine) as session:
            records = session.exec(
                select(WorkspaceRecord).order_by(col(WorkspaceRecord.last_opened_at).desc())
            ).all()
            return [_to_domain(record) for record in records]

    def get(self, workspace_id: str) -> Workspace | None:
        with Session(self._engine) as session:
            record = session.get(WorkspaceRecord, workspace_id)
            return None if record is None else _to_domain(record)

    def find_by_name_key(self, name_key: str) -> Workspace | None:
        with Session(self._engine) as session:
            record = session.exec(
                select(WorkspaceRecord).where(WorkspaceRecord.name_key == name_key)
            ).first()
            return None if record is None else _to_domain(record)

    def find_by_path_key(self, path_key: str) -> Workspace | None:
        with Session(self._engine) as session:
            record = session.exec(
                select(WorkspaceRecord).where(WorkspaceRecord.path_key == path_key)
            ).first()
            return None if record is None else _to_domain(record)

    def add(self, workspace: Workspace) -> Workspace:
        record = WorkspaceRecord(
            id=workspace.id,
            name=workspace.name,
            name_key=workspace.name.casefold(),
            path=workspace.path,
            path_key=workspace.path.casefold(),
            created_at=workspace.created_at,
            last_opened_at=workspace.last_opened_at,
        )
        with Session(self._engine) as session:
            session.add(record)
            try:
                session.commit()
            except IntegrityError as exception:
                session.rollback()
                conflict_field = "name" if "name_key" in str(exception.orig) else "path"
                raise WorkspaceConflictError(conflict_field) from exception
            session.refresh(record)
            return _to_domain(record)

    def update_last_opened(self, workspace_id: str, opened_at: datetime) -> Workspace:
        with Session(self._engine) as session:
            record = session.get(WorkspaceRecord, workspace_id)
            if record is None:
                raise LookupError(workspace_id)
            record.last_opened_at = opened_at
            session.add(record)
            session.commit()
            session.refresh(record)
            return _to_domain(record)

    def update_name(self, workspace_id: str, name: str) -> Workspace:
        with Session(self._engine) as session:
            record = session.get(WorkspaceRecord, workspace_id)
            if record is None:
                raise LookupError(workspace_id)
            record.name = name
            record.name_key = name.casefold()
            session.add(record)
            try:
                session.commit()
            except IntegrityError as exception:
                session.rollback()
                raise WorkspaceConflictError("name") from exception
            session.refresh(record)
            return _to_domain(record)

    def delete(self, workspace_id: str) -> Workspace:
        with Session(self._engine) as session:
            record = session.get(WorkspaceRecord, workspace_id)
            if record is None:
                raise LookupError(workspace_id)
            workspace = _to_domain(record)
            session.delete(record)
            session.commit()
            return workspace

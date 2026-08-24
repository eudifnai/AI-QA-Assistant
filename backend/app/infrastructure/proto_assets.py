from datetime import UTC, datetime

from sqlalchemy import Column, DateTime, ForeignKey, Index, Integer, LargeBinary, String
from sqlalchemy.engine import Engine
from sqlalchemy.exc import IntegrityError
from sqlmodel import Field, Session, SQLModel, col, select

from backend.app.domain.proto_asset import ProtoAsset, ProtoAssetConflictError
from backend.app.infrastructure.protobuf_codec import summarize_descriptor_set


class ProtoAssetRecord(SQLModel, table=True):
    __tablename__ = "proto_assets"
    __table_args__ = (
        Index("uq_proto_assets_workspace_path", "workspace_id", "path_key", unique=True),
        Index("uq_proto_assets_workspace_hash", "workspace_id", "sha256", unique=True),
    )

    id: str = Field(sa_column=Column(String(36), primary_key=True))
    workspace_id: str = Field(
        sa_column=Column(
            String(36), ForeignKey("workspaces.id", ondelete="CASCADE"), nullable=False
        )
    )
    name: str = Field(sa_column=Column(String(255), nullable=False))
    relative_path: str = Field(sa_column=Column(String(2048), nullable=False))
    path_key: str = Field(sa_column=Column(String(2048), nullable=False))
    sha256: str = Field(sa_column=Column(String(64), nullable=False))
    size_bytes: int = Field(sa_column=Column(Integer, nullable=False))
    descriptor_set: bytes = Field(sa_column=Column(LargeBinary, nullable=False))
    created_at: datetime = Field(sa_column=Column(DateTime(timezone=True), nullable=False))
    updated_at: datetime = Field(sa_column=Column(DateTime(timezone=True), nullable=False))


def _utc(value: datetime) -> datetime:
    return value.replace(tzinfo=UTC) if value.tzinfo is None else value.astimezone(UTC)


def _to_domain(record: ProtoAssetRecord) -> ProtoAsset:
    summary = summarize_descriptor_set(record.descriptor_set, record.relative_path)
    return ProtoAsset(
        record.id,
        record.workspace_id,
        record.name,
        record.relative_path,
        record.sha256,
        record.size_bytes,
        record.descriptor_set,
        summary.packages,
        summary.messages,
        summary.enums,
        summary.services,
        _utc(record.created_at),
        _utc(record.updated_at),
    )


class SqlModelProtoAssetRepository:
    def __init__(self, engine: Engine) -> None:
        self._engine = engine

    def list(self, workspace_id: str) -> list[ProtoAsset]:
        with Session(self._engine) as session:
            records = session.exec(
                select(ProtoAssetRecord)
                .where(ProtoAssetRecord.workspace_id == workspace_id)
                .order_by(col(ProtoAssetRecord.updated_at).desc())
            ).all()
            return [_to_domain(record) for record in records]

    def get(self, workspace_id: str, asset_id: str) -> ProtoAsset | None:
        with Session(self._engine) as session:
            record = session.get(ProtoAssetRecord, asset_id)
            if record is None or record.workspace_id != workspace_id:
                return None
            return _to_domain(record)

    def find_by_hash(self, workspace_id: str, sha256: str) -> ProtoAsset | None:
        with Session(self._engine) as session:
            record = session.exec(
                select(ProtoAssetRecord).where(
                    ProtoAssetRecord.workspace_id == workspace_id,
                    ProtoAssetRecord.sha256 == sha256,
                )
            ).first()
            return None if record is None else _to_domain(record)

    def find_by_path(self, workspace_id: str, path_key: str) -> ProtoAsset | None:
        with Session(self._engine) as session:
            record = session.exec(
                select(ProtoAssetRecord).where(
                    ProtoAssetRecord.workspace_id == workspace_id,
                    ProtoAssetRecord.path_key == path_key,
                )
            ).first()
            return None if record is None else _to_domain(record)

    def save(self, asset: ProtoAsset) -> ProtoAsset:
        with Session(self._engine) as session:
            record = session.get(ProtoAssetRecord, asset.id)
            if record is None:
                record = ProtoAssetRecord(
                    id=asset.id,
                    workspace_id=asset.workspace_id,
                    name=asset.name,
                    relative_path=asset.relative_path,
                    path_key=asset.relative_path.casefold(),
                    sha256=asset.sha256,
                    size_bytes=asset.size_bytes,
                    descriptor_set=asset.descriptor_set,
                    created_at=asset.created_at,
                    updated_at=asset.updated_at,
                )
            else:
                record.name = asset.name
                record.relative_path = asset.relative_path
                record.path_key = asset.relative_path.casefold()
                record.sha256 = asset.sha256
                record.size_bytes = asset.size_bytes
                record.descriptor_set = asset.descriptor_set
                record.updated_at = asset.updated_at
            session.add(record)
            try:
                session.commit()
            except IntegrityError as exception:
                session.rollback()
                raise ProtoAssetConflictError from exception
            session.refresh(record)
            return _to_domain(record)

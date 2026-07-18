"""Run database model: one batch conversion run."""

from datetime import datetime, timezone

from sqlalchemy import BigInteger, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class Run(Base):
    """A batch conversion run over a set of Immich assets."""

    __tablename__ = "runs"

    id: Mapped[int] = mapped_column(primary_key=True)

    # queued, running, completed, failed, cancelled
    status: Mapped[str] = mapped_column(default="queued")

    created_at: Mapped[datetime] = mapped_column(
        default=lambda: datetime.now(timezone.utc)
    )
    started_at: Mapped[datetime | None] = mapped_column(default=None)
    completed_at: Mapped[datetime | None] = mapped_column(default=None)

    # JSON snapshot of the filters + encoding settings actually used.
    config_snapshot: Mapped[str] = mapped_column(Text, default="{}")
    dry_run: Mapped[bool] = mapped_column(default=False)

    total_assets: Mapped[int] = mapped_column(default=0)
    processed_count: Mapped[int] = mapped_column(default=0)
    success_count: Mapped[int] = mapped_column(default=0)
    skipped_count: Mapped[int] = mapped_column(default=0)
    failed_count: Mapped[int] = mapped_column(default=0)

    input_bytes: Mapped[int] = mapped_column(BigInteger, default=0)
    output_bytes: Mapped[int] = mapped_column(BigInteger, default=0)

    error_message: Mapped[str | None] = mapped_column(Text, default=None)

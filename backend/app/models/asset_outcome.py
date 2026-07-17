"""AssetOutcome database model: per-asset result within a run."""

from datetime import datetime, timezone

from sqlalchemy import BigInteger, ForeignKey, Index, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base

# A status we consider "done" -- resumable filter-based runs skip these.
# Everything else (failed_*, error, unknown) is retryable.
FINAL_STATUSES = frozenset({"success", "partial_success", "skipped"})


class AssetOutcome(Base):
    """Result of processing one asset during one run."""

    __tablename__ = "asset_outcomes"

    id: Mapped[int] = mapped_column(primary_key=True)
    run_id: Mapped[int] = mapped_column(ForeignKey("runs.id", ondelete="CASCADE"))

    asset_id: Mapped[str] = mapped_column(index=True)
    filename: Mapped[str] = mapped_column(default="")
    status: Mapped[str] = mapped_column(default="unknown")
    error: Mapped[str | None] = mapped_column(Text, default=None)
    new_asset_id: Mapped[str | None] = mapped_column(default=None)
    target_format: Mapped[str | None] = mapped_column(default=None)
    input_bytes: Mapped[int] = mapped_column(BigInteger, default=0)
    output_bytes: Mapped[int] = mapped_column(BigInteger, default=0)

    updated_at: Mapped[datetime] = mapped_column(
        default=lambda: datetime.now(timezone.utc)
    )

    __table_args__ = (
        Index("idx_asset_outcomes_run_id", "run_id"),
        Index("idx_asset_outcomes_asset_id_updated_at", "asset_id", "updated_at"),
    )

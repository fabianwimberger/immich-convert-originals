"""Shared custom SQLAlchemy column types."""

from datetime import datetime, timezone

from sqlalchemy import DateTime
from sqlalchemy.types import TypeDecorator


class TZDateTime(TypeDecorator):
    """An always-aware UTC DateTime for backends without timestamptz.

    SQLite ignores DateTime(timezone=True) and drops tzinfo on read, so a
    timestamp written as UTC came back naive and serialized without an
    offset. Store naive UTC, return aware UTC.
    """

    impl = DateTime
    cache_ok = True

    def process_bind_param(self, value: datetime | None, dialect) -> datetime | None:
        if value is None:
            return None
        if value.tzinfo is None:
            raise TypeError(
                f"{value!r} is naive; TZDateTime columns require an aware datetime"
            )
        return value.astimezone(timezone.utc).replace(tzinfo=None)

    def process_result_value(self, value: datetime | None, dialect) -> datetime | None:
        if value is None:
            return None
        return value.replace(tzinfo=timezone.utc)

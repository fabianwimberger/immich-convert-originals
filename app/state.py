"""SQLite-backed persistent state for resumable runs."""

import csv
import os
import sqlite3
from datetime import datetime, timezone

# A status we consider "done" — resumable runs skip these by default.
# Everything else (failed_*, error, unknown) is retryable.
FINAL_STATUSES = frozenset(
    {
        "success",
        "partial_success",
        "skipped",
    }
)


def _utcnow_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


class StateDB:
    """Per-asset outcome store.

    Records only live runs (dry runs should not call record()).
    """

    def __init__(self, path: str) -> None:
        self.path = path
        parent = os.path.dirname(path)
        if parent:
            os.makedirs(parent, exist_ok=True)
        self._conn = sqlite3.connect(path, check_same_thread=False)
        self._conn.execute("PRAGMA journal_mode=WAL")
        self._init_schema()

    def _init_schema(self) -> None:
        self._conn.execute(
            """
            CREATE TABLE IF NOT EXISTS assets (
                asset_id TEXT PRIMARY KEY,
                status TEXT NOT NULL,
                error TEXT,
                filename TEXT,
                input_bytes INTEGER DEFAULT 0,
                output_bytes INTEGER DEFAULT 0,
                updated_at TEXT NOT NULL
            )
            """
        )
        self._conn.commit()

    def record(
        self,
        asset_id: str,
        status: str,
        filename: str,
        error: str | None = None,
        input_bytes: int = 0,
        output_bytes: int = 0,
    ) -> None:
        with self._conn:
            self._conn.execute(
                """
                INSERT INTO assets(asset_id, status, error, filename,
                                   input_bytes, output_bytes, updated_at)
                VALUES(?,?,?,?,?,?,?)
                ON CONFLICT(asset_id) DO UPDATE SET
                    status=excluded.status,
                    error=excluded.error,
                    filename=excluded.filename,
                    input_bytes=excluded.input_bytes,
                    output_bytes=excluded.output_bytes,
                    updated_at=excluded.updated_at
                """,
                (
                    asset_id,
                    status,
                    error,
                    filename,
                    input_bytes,
                    output_bytes,
                    _utcnow_iso(),
                ),
            )

    def get_status(self, asset_id: str) -> str | None:
        cur = self._conn.execute(
            "SELECT status FROM assets WHERE asset_id = ?", (asset_id,)
        )
        row = cur.fetchone()
        return row[0] if row else None

    def completed_ids(self) -> set[str]:
        """Asset ids with a terminal success-like status."""
        placeholders = ",".join("?" * len(FINAL_STATUSES))
        cur = self._conn.execute(
            f"SELECT asset_id FROM assets WHERE status IN ({placeholders})",
            tuple(FINAL_STATUSES),
        )
        return {r[0] for r in cur.fetchall()}

    def failed_ids(self) -> set[str]:
        """Asset ids whose last recorded status is a failure."""
        placeholders = ",".join("?" * len(FINAL_STATUSES))
        cur = self._conn.execute(
            f"SELECT asset_id FROM assets WHERE status NOT IN ({placeholders})",
            tuple(FINAL_STATUSES),
        )
        return {r[0] for r in cur.fetchall()}

    def export_failures_csv(self, path: str) -> int:
        placeholders = ",".join("?" * len(FINAL_STATUSES))
        cur = self._conn.execute(
            f"""
            SELECT asset_id, filename, status, error, updated_at
            FROM assets
            WHERE status NOT IN ({placeholders})
            ORDER BY updated_at DESC
            """,
            tuple(FINAL_STATUSES),
        )
        rows = cur.fetchall()
        with open(path, "w", newline="") as f:
            writer = csv.writer(f)
            writer.writerow(["asset_id", "filename", "status", "error", "updated_at"])
            writer.writerows(rows)
        return len(rows)

    def reset(self) -> None:
        with self._conn:
            self._conn.execute("DELETE FROM assets")

    def close(self) -> None:
        self._conn.close()

    def __enter__(self) -> "StateDB":
        return self

    def __exit__(self, exc_type, exc, tb) -> None:  # type: ignore[no-untyped-def]
        self.close()

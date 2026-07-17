"""Shared FastAPI dependencies."""

from fastapi import Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.routes.settings import get_settings_row
from app.services.immich_client import ImmichClient


async def get_immich_client(db: AsyncSession = Depends(get_db)) -> ImmichClient:
    """Build an ImmichClient from the saved Settings row.

    Raises 424 (Failed Dependency) if the connection hasn't been
    configured yet, so routes that need Immich get a clear error instead
    of an opaque connection failure.
    """
    row = await get_settings_row(db)
    if not row.immich_api_base or not row.immich_api_key:
        raise HTTPException(
            status_code=424,
            detail="Immich connection not configured -- set it on the Settings page",
        )

    api_base = row.immich_api_base
    if not api_base.endswith("/"):
        api_base += "/"

    # A lower retry count than the default (3, tuned for long batch runs)
    # keeps interactive browse/thumbnail requests from hanging for ~20s
    # on a broken connection.
    return ImmichClient(api_base=api_base, api_key=row.immich_api_key, retry_max=1)

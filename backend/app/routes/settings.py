"""Settings API: connection and default encoding values."""

import asyncio

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models.schemas import (
    SettingsResponse,
    SettingsUpdate,
    TestConnectionRequest,
    TestConnectionResponse,
)
from app.models.settings import SETTINGS_ROW_ID, Settings
from app.services.immich_client import ImmichClient

router = APIRouter()


async def get_settings_row(db: AsyncSession) -> Settings:
    result = await db.execute(select(Settings).where(Settings.id == SETTINGS_ROW_ID))
    row = result.scalar_one_or_none()
    if row is None:
        raise RuntimeError("Settings row missing -- init_settings() did not run")
    return row


@router.get("", response_model=SettingsResponse)
async def read_settings(db: AsyncSession = Depends(get_db)):
    row = await get_settings_row(db)
    return SettingsResponse.from_settings(row)


@router.put("", response_model=SettingsResponse)
async def update_settings(data: SettingsUpdate, db: AsyncSession = Depends(get_db)):
    row = await get_settings_row(db)
    updates = data.model_dump(exclude_unset=True)
    for key, value in updates.items():
        setattr(row, key, value)
    await db.commit()
    await db.refresh(row)
    return SettingsResponse.from_settings(row)


@router.post("/test-connection", response_model=TestConnectionResponse)
async def test_connection(
    data: TestConnectionRequest, db: AsyncSession = Depends(get_db)
):
    row = await get_settings_row(db)
    api_base = data.immich_api_base or row.immich_api_base
    api_key = data.immich_api_key or row.immich_api_key

    if not api_base or not api_key:
        return TestConnectionResponse(ok=False, error="API base and key are required")

    if not api_base.endswith("/"):
        api_base += "/"

    client = ImmichClient(api_base=api_base, api_key=api_key, retry_max=0)
    ok, error = await asyncio.to_thread(client.test_connection)
    if not ok:
        return TestConnectionResponse(ok=False, error=error)

    info = await asyncio.to_thread(client.server_info)
    version = None
    if info:
        version = f"{info.get('major')}.{info.get('minor')}.{info.get('patch')}"
    return TestConnectionResponse(ok=True, server_version=version)

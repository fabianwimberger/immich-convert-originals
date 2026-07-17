"""Pydantic schemas for API requests and responses."""

from pydantic import BaseModel, ConfigDict, Field

from app.models.settings import Settings as SettingsRow


class SettingsResponse(BaseModel):
    """Settings as returned to the client. The API key is masked."""

    model_config = ConfigDict(from_attributes=True)

    immich_api_base: str
    immich_api_key_set: bool
    asset_types: str
    include_archived: bool
    include_deleted: bool
    image_distance: float
    image_distance_retry: float
    video_crf: int
    video_preset: int
    video_max_dimension: int
    video_audio_bitrate: str
    video_crf_retry: int
    enable_retry: bool
    accept_retry_output: bool
    allow_larger: bool
    concurrency: int

    @classmethod
    def from_settings(cls, settings: SettingsRow) -> "SettingsResponse":
        return cls(
            immich_api_base=settings.immich_api_base,
            immich_api_key_set=bool(settings.immich_api_key),
            asset_types=settings.asset_types,
            include_archived=settings.include_archived,
            include_deleted=settings.include_deleted,
            image_distance=settings.image_distance,
            image_distance_retry=settings.image_distance_retry,
            video_crf=settings.video_crf,
            video_preset=settings.video_preset,
            video_max_dimension=settings.video_max_dimension,
            video_audio_bitrate=settings.video_audio_bitrate,
            video_crf_retry=settings.video_crf_retry,
            enable_retry=settings.enable_retry,
            accept_retry_output=settings.accept_retry_output,
            allow_larger=settings.allow_larger,
            concurrency=settings.concurrency,
        )


class SettingsUpdate(BaseModel):
    """Partial update for settings. Omitted fields are left unchanged.

    immich_api_key: pass null/omit to leave the stored key unchanged, or an
    empty string to clear it. This lets the UI round-trip the masked
    settings response without ever needing to redisplay the real key.
    """

    immich_api_base: str | None = None
    immich_api_key: str | None = None
    asset_types: str | None = None
    include_archived: bool | None = None
    include_deleted: bool | None = None
    image_distance: float | None = Field(default=None, ge=0, le=25)
    image_distance_retry: float | None = Field(default=None, ge=0, le=25)
    video_crf: int | None = Field(default=None, ge=0, le=63)
    video_preset: int | None = Field(default=None, ge=0, le=13)
    video_max_dimension: int | None = Field(default=None, ge=0)
    video_audio_bitrate: str | None = None
    video_crf_retry: int | None = Field(default=None, ge=0, le=63)
    enable_retry: bool | None = None
    accept_retry_output: bool | None = None
    allow_larger: bool | None = None
    concurrency: int | None = Field(default=None, ge=1, le=32)


class TestConnectionRequest(BaseModel):
    """Optional override so the connection can be tested before saving."""

    immich_api_base: str | None = None
    immich_api_key: str | None = None


class TestConnectionResponse(BaseModel):
    ok: bool
    error: str | None = None
    server_version: str | None = None


class AssetItem(BaseModel):
    id: str
    original_file_name: str
    original_path: str
    original_mime_type: str | None
    type: str
    file_created_at: str
    file_modified_at: str
    already_jxl: bool


class AssetListResponse(BaseModel):
    items: list[AssetItem]
    page: int
    size: int
    has_more: bool


class AlbumItem(BaseModel):
    id: str
    album_name: str
    asset_count: int


class AlbumListResponse(BaseModel):
    items: list[AlbumItem]

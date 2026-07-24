"""Settings database model: a single row of app-wide defaults."""

from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base

SETTINGS_ROW_ID = 1


class Settings(Base):
    """Immich connection and default encoding settings.

    A singleton row (id always SETTINGS_ROW_ID). Seeded from environment
    variables on first boot (see app.config.seed_settings_from_env); after
    that, the Settings page in the UI is the only way to change it.
    """

    __tablename__ = "settings"

    id: Mapped[int] = mapped_column(primary_key=True, default=SETTINGS_ROW_ID)

    immich_api_base: Mapped[str] = mapped_column(default="")
    immich_api_key: Mapped[str] = mapped_column(default="")

    asset_types: Mapped[str] = mapped_column(default="IMAGE,VIDEO")
    include_archived: Mapped[bool] = mapped_column(default=False)
    include_deleted: Mapped[bool] = mapped_column(default=False)

    # Which image formats a run will touch at all; anything else is skipped
    # before download. Comma-separated subset of jpg,png,webp,heic,avif,tiff,gif,bmp.
    convert_image_formats: Mapped[str] = mapped_column(
        default="jpg,png,webp,heic,avif,tiff,gif,bmp"
    )

    image_distance: Mapped[float] = mapped_column(default=1.0)
    image_distance_retry: Mapped[float] = mapped_column(default=2.0)

    video_crf: Mapped[int] = mapped_column(default=36)
    video_preset: Mapped[int] = mapped_column(default=4)
    video_max_dimension: Mapped[int] = mapped_column(default=0)
    video_audio_bitrate: Mapped[str] = mapped_column(default="64k")
    video_crf_retry: Mapped[int] = mapped_column(default=40)

    enable_retry: Mapped[bool] = mapped_column(default=True)
    accept_retry_output: Mapped[bool] = mapped_column(default=False)
    allow_larger: Mapped[bool] = mapped_column(default=False)

    concurrency: Mapped[int] = mapped_column(default=2)

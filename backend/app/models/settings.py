"""Settings database model: a single row of app-wide defaults."""

from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base

SETTINGS_ROW_ID = 1


class Settings(Base):
    """Immich connection and default encoding settings.

    A singleton row (id always SETTINGS_ROW_ID), seeded with these column
    defaults on first boot; after that, the Settings page in the UI is the
    only way to change it.
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

    # Target image container. HEIC/AVIF use image_quality_* (0-100,
    # ImageMagick -quality) instead of distance -- not the same scale.
    image_target_format: Mapped[str] = mapped_column(default="jxl")
    image_distance: Mapped[float] = mapped_column(default=1.0)
    image_distance_retry: Mapped[float] = mapped_column(default=2.0)
    image_quality_heic: Mapped[int] = mapped_column(default=80)
    image_quality_heic_retry: Mapped[int] = mapped_column(default=60)
    image_quality_avif: Mapped[int] = mapped_column(default=75)
    image_quality_avif_retry: Mapped[int] = mapped_column(default=55)

    video_crf: Mapped[int] = mapped_column(default=36)
    video_preset: Mapped[int] = mapped_column(default=4)
    video_max_dimension: Mapped[int] = mapped_column(default=0)
    video_audio_bitrate: Mapped[str] = mapped_column(default="64k")
    video_crf_retry: Mapped[int] = mapped_column(default=40)

    enable_retry: Mapped[bool] = mapped_column(default=True)
    accept_retry_output: Mapped[bool] = mapped_column(default=False)
    allow_larger: Mapped[bool] = mapped_column(default=False)

    concurrency: Mapped[int] = mapped_column(default=2)

    # "local" writes the converted file to local_output_dir instead of
    # uploading to Immich -- the original is never touched (no upload, no
    # delete) either way.
    output_mode: Mapped[str] = mapped_column(default="upload")
    local_output_dir: Mapped[str] = mapped_column(default="/app/output")
    local_keep_originals: Mapped[bool] = mapped_column(default=False)

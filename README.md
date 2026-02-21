# Immich Library Converter

[![CI](https://github.com/fabianwimberger/immich-convert-originals/actions/workflows/ci.yml/badge.svg)](https://github.com/fabianwimberger/immich-convert-originals/actions)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)

Batch-transcode your Immich library to modern efficient formats:
- **Images** → JPEG XL (JXL)
- **Videos** → AV1 (MP4 container)

This tool downloads your original assets, transcodes them to space-efficient formats, uploads the new versions, copies all metadata (EXIF, location, tags, albums, etc.), and removes the originals.

## Why This Project?

Modern image and video formats offer significant space savings without perceptible quality loss. JPEG XL typically reduces image sizes by 20-40% compared to JPEG, while AV1 can reduce video sizes by 30-50% compared to H.264. For large photo libraries, this can mean saving hundreds of gigabytes.

**Goals:**
- Reduce storage costs for Immich libraries
- Maintain full metadata and quality
- Provide a safe, reversible conversion process

## Features

- **Image conversion** — JPEG, PNG, WebP, HEIC → JPEG XL
- **Video conversion** — MP4, MOV, MKV → AV1 (MP4)
- **Metadata preservation** — EXIF, GPS, tags, albums, faces
- **Smart retry logic** — automatically retries with higher compression if output is larger
- **Dry-run mode** — preview changes before executing
- **Date filtering** — process only assets within a date range
- **Concurrency control** — configurable parallel workers

## Quick Start

```bash
# Clone the repository
git clone https://github.com/fabianwimberger/immich-convert-originals.git
cd immich-convert-originals

# Copy and edit configuration
cp .env.example .env
# Edit .env with your Immich URL and API key

# Start with dry run to preview
DRY_RUN=true docker compose up

# When ready, run for real
docker compose up
```

## How It Works

```
Search assets → Download → Transcode → Upload new → Copy metadata → Delete original
```

Each step is verified:
1. **Download** original to temp directory
2. **Transcode** based on asset type
3. **Validate** output format and integrity
4. **Upload** new asset to Immich
5. **Copy metadata** (EXIF, GPS, tags, albums, faces, etc.)
6. **Verify** new asset is accessible
7. **Delete** original (goes to trash, recoverable for 30 days)

If any step fails, the new asset is cleaned up and the original is preserved.

## Configuration

### Required Settings

| Variable | Description | Example |
|----------|-------------|---------|
| `IMMICH_API_BASE` | Your Immich API URL | `https://photos.example.com/api` |
| `IMMICH_API_KEY` | API key from Immich | `abc123...` |

**Always start with `DRY_RUN=true` (the default) to test your settings.**

### Image Encoding (JPEG XL)

| Variable | Description | Default |
|----------|-------------|---------|
| `IMAGE_DISTANCE` | JXL distance (0=lossless, 1=visually lossless) | `1.0` |
| `IMAGE_DISTANCE_RETRY` | Distance for retry if output is larger | `2.0` |

### Video Encoding (AV1)

| Variable | Description | Default |
|----------|-------------|---------|
| `VIDEO_CRF` | Quality (0-63, lower=better) | `36` |
| `VIDEO_PRESET` | Speed/quality tradeoff (0-13, lower=slower) | `4` |
| `VIDEO_MAX_DIMENSION` | Max shorter side in pixels (0=original) | `0` |

## Security & Safety

**⚠️ USE AT YOUR OWN RISK.** This tool modifies your Immich library:
- Permanently deletes original assets after successful conversion
- Replaced assets go to Immich's **trash** (recoverable for 30 days by default)

**Before using:**
1. **Backup your Immich library**
2. **Test on a small subset first** — use date filters or `MAX_ASSETS`
3. **Check your Immich trash settings** at `Administration > Settings > Trash`

## Getting Your Immich API Key

1. Open your Immich web interface
2. Click your **profile picture** (top right) → **Account Settings**
3. Go to **API Keys** section
4. Click **New API Key**
5. Give it a name (e.g., "Library Converter")
6. Copy the key immediately (it won't be shown again)

**Required Permissions:**
- `Asset` — Read, Upload, Delete
- `Album` — Read
- `Library` — Read (if using external libraries)

## License

MIT License — see [LICENSE](LICENSE) file.

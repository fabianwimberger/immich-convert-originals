# Immich Library Converter

Batch-transcode your Immich library to modern efficient formats:
- **Images** → JPEG XL (JXL)
- **Videos** → AV1 (MP4 container)

This tool downloads your original assets, transcodes them to space-efficient formats, uploads the new versions, copies all metadata (EXIF, location, tags, albums, etc.), and removes the originals.

---

## Disclaimer & Risks

**USE AT YOUR OWN RISK.** This tool modifies your Immich library by:
- Permanently deleting original assets after successful conversion
- Replacing them with transcoded versions

**Before using this tool:**
1. **Backup your Immich library** - Have a complete backup of your original files
2. **Test on a small subset first** - Use date filters or `MAX_ASSETS` to test with a few assets
3. **Understand your Immich trash settings** - Deleted assets go to Immich trash first

---

## About Trash & Recovery

**Good news:** When this tool deletes originals, they go to Immich's **trash**, not permanent deletion.

- Trash items can be restored from the Immich web UI
- Default trash auto-empty is typically 30 days (configurable in Immich)
- **Check your Immich trash settings** at `Administration > Settings > Trash`
- The converted JXL/AV1 files remain in your library immediately

**Recommendation:** After converting, verify a few converted assets before emptying trash.

---

## Getting Your Immich API Key

1. Open your Immich web interface
2. Click your **profile picture** (top right) → **Account Settings**
3. Go to **API Keys** section
4. Click **New API Key**
5. Give it a name (e.g., "Library Converter")
6. Copy the key immediately (it won't be shown again)

**Required API Key Permissions:**
- `Asset` - Read, Upload, Delete
- `Album` - Read
- `Library` - Read (if using external libraries)

---

## Quick Start

```bash
# 1. Clone or download this repository
cd immich-library-convert

# 2. Copy and edit configuration
cp .env.example .env
# Edit .env with your Immich URL and API key

# 3. Start with dry run to preview
DRY_RUN=true docker compose up

# 4. When ready, run for real
docker compose up
```

---

## Configuration

Only 2 settings are **required**: `IMMICH_API_BASE` and `IMMICH_API_KEY`. Everything else uses sensible defaults (dry-run mode is on by default).

### Required Settings

| Variable | Description | Example |
|----------|-------------|---------|
| `IMMICH_API_BASE` | Your Immich API URL | `https://photos.example.com/api` |
| `IMMICH_API_KEY` | API key from Immich | `abc123...` |

**Always start with `DRY_RUN=true` (the default) to test your settings.**

### Optional Settings

| Variable | Description | Default |
|----------|-------------|---------|
| `DRY_RUN` | Preview mode - no changes made | `true` |
| `ASSET_TYPES` | `IMAGE`, `VIDEO`, or `IMAGE,VIDEO` | `IMAGE,VIDEO` |
| `CONCURRENCY` | Parallel workers | `1` |
| `MAX_ASSETS` | Limit number of assets to process (0 = unlimited) | `0` |
| `INCLUDE_ARCHIVED` | Include archived assets | `false` |
| `INCLUDE_DELETED` | Include trash assets | `false` |

### Date Filtering

| Variable | Description | Example |
|----------|-------------|---------|
| `FILTER_DATE_AFTER` | Only assets after date (YYYY-MM-DD) | `2020-01-01` |
| `FILTER_DATE_BEFORE` | Only assets before date (YYYY-MM-DD) | `2023-12-31` |

Leave empty to process all dates.

### Image Encoding (JPEG XL)

| Variable | Description | Default |
|----------|-------------|---------|
| `IMAGE_DISTANCE` | JXL distance (0=lossless, 1=visually lossless, higher=smaller) | `1.0` |
| `IMAGE_DISTANCE_RETRY` | Distance for retry if output is larger (higher=more compression) | `2.0` |

**How images are encoded:**
- **JPEG files**: `cjxl` lossless repack (always lossless, distance setting ignored)
- **PNG/WebP/HEIC/AVIF/TIFF/BMP/GIF/etc**: ImageMagick with `IMAGE_DISTANCE`
- If `cjxl` fails (progressive JPEG, CMYK), falls back to ImageMagick

### Video Encoding (AV1)

| Variable | Description | Default |
|----------|-------------|---------|
| `VIDEO_CRF` | Quality (0-63, lower=better, larger file) | `36` |
| `VIDEO_PRESET` | Speed/quality tradeoff (0-13, lower=slower/better) | `4` |
| `VIDEO_MAX_DIMENSION` | Max shorter side in pixels (0=original size) | `0` |
| `VIDEO_AUDIO_BITRATE` | Audio bitrate | `64k` |
| `VIDEO_CRF_RETRY` | CRF for retry if output is larger | `40` |

**Note:** `VIDEO_MAX_DIMENSION` limits the shorter side (width for portrait, height for landscape). A 1080 setting keeps 1080x1920 portrait videos at full resolution.

### Retry Behavior

When output is larger than input:

| Variable | Description | Default |
|----------|-------------|---------|
| `ENABLE_RETRY` | Retry with more compression if output is larger | `true` |
| `ACCEPT_RETRY_OUTPUT` | Accept retry result even if still larger | `false` |

**Retry flow:**
1. First attempt with `IMAGE_DISTANCE` / `VIDEO_CRF`
2. If output >= input and `ENABLE_RETRY=true`: Retry with retry settings
3. If still larger and `ACCEPT_RETRY_OUTPUT=false`: Skip file
4. If still larger and `ACCEPT_RETRY_OUTPUT=true`: Accept the file

### Safety Settings

| Variable | Description | Default |
|----------|-------------|---------|
| `ALLOW_LARGER` | Keep output even if larger than input | `false` |

---

## Supported Input Formats

**Images:** JPEG, PNG, WebP, AVIF, HEIC/HEIF, TIFF, BMP, GIF, and more

**Videos:** MP4, MOV, MKV, WebM, AVI, and any format ffmpeg supports

Already-converted assets (JXL images, AV1 videos) are automatically skipped.

---

## How It Works

```
Search assets -> Download -> Transcode -> Upload new -> Copy metadata -> Delete original
```

Each step is verified:
1. **Download** original to temp directory
2. **Transcode** based on asset type
3. **Validate** output format and integrity
4. **Upload** new asset to Immich
5. **Copy metadata** (EXIF, GPS, tags, albums, faces, etc.)
6. **Verify** new asset is accessible
7. **Delete** original (goes to trash)

If any step fails, the new asset is cleaned up and the original is preserved.

---

## Troubleshooting

### Configuration error: X is required
You must set `IMMICH_API_BASE` and `IMMICH_API_KEY` in your `.env` file.

### Assets not being processed
- Check `ASSET_TYPES` includes your asset type
- Check date filters aren't too restrictive
- Try `DRY_RUN=true` to see what's being selected

### Output files larger than input
- Enable retry: `ENABLE_RETRY=true`
- More compression: `IMAGE_DISTANCE=2.0` or `VIDEO_CRF=40`
- Accept larger: `ALLOW_LARGER=true`

### Connection failures
- Verify `IMMICH_API_BASE` ends with `/api`
- Check API key has required permissions
- Ensure Immich is accessible from the container

---

## License

MIT License - See [LICENSE](LICENSE) file.

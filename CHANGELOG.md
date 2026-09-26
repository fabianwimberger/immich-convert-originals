# Changelog

All notable changes to this project are documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [v2.5.0] - 2026-09-26

Sorts album dropdowns alphabetically and fixes timestamp display and partner-shared asset handling.

### Features

- Sort album dropdowns A-Z

### Fixes

- Store run and asset timestamps as timezone-aware UTC, so the run history shows the correct local time and the failure CSV exports ISO 8601 (thanks to @arjankapteijn)
- Skip assets owned by another account (partner shares and others' shared albums) in upload mode instead of failing with `no asset.copy.access`

### Documentation & Links

- [README](https://github.com/fabianwimberger/immich-convert-originals#readme)
- [Container image](https://github.com/fabianwimberger/immich-convert-originals/pkgs/container/immich-convert-originals)

## [v2.4.2] - 2026-09-19

Reports the package version in the OpenAPI schema and tidies the lint tooling.

### Fixes

- Report the package version in the OpenAPI schema instead of the framework default

### CI

- Install lint tools from `requirements-dev.txt` and pin the ruff rule set
- Update the pinned lint tools to their latest versions

### Documentation

- Add a troubleshooting section to the README

### Documentation & Links

- [README](https://github.com/fabianwimberger/immich-convert-originals#readme)
- [Container image](https://github.com/fabianwimberger/immich-convert-originals/pkgs/container/immich-convert-originals)

## [v2.4.1] - 2026-09-11

Fixes a large-upload timeout bug and an AV1 transcode failure on certain SDR sources.

### Fixes

- Fix large video uploads failing after ~10s regardless of file size, caused by reusing the short connect-timeout for the whole upload body instead of only the connection phase (thanks to @arjankapteijn)
- Fix AV1 transcode failing on SDR videos mistagged with gbr/rgb color metadata by older phone/WhatsApp encoders (thanks to @arjankapteijn)

### Documentation & Links

- [README](https://github.com/fabianwimberger/immich-convert-originals#readme)

## [v2.4.0] - 2026-09-04

HDR sources now keep their color, and TIFF conversion is fixed.

### Features

- Encode HDR10/HLG video with 10-bit BT.2020 instead of flattening to SDR — HDR is detected via `color_transfer` and carried through to the AV1 output; SDR sources are unaffected

### Fixes

- Add the missing TIFF ImageMagick dependency to the Docker image, fixing TIFF conversion (thanks to @salvah22)

### Dependencies

- Bump fastapi, uvicorn, sqlalchemy, websockets, ruff, mypy, setuptools, and responses to their latest patch/minor versions

### Documentation & Links

- [README](https://github.com/fabianwimberger/immich-convert-originals#readme)

## [v2.3.0] - 2026-08-15

Encoder effort now applies wherever a JPEG XL target does, not just the JPEG lossless repack.

### Features

- Apply JPEG XL encoder effort to every target format, not only the JPEG->JXL cjxl repack — PNG, HEIC, and other sources going through ImageMagick's encoder now respect it too
- Raise the effort range from 1-9 to 1-10 to match libjxl 0.11.x

### Documentation & Links

- [README](https://github.com/fabianwimberger/immich-convert-originals#readme)

## [v2.2.0] - 2026-08-14

Adds control over JPEG XL repack compression effort, plus a URL-configuration fix and routine dependency maintenance.

### Features

- Configurable `cjxl --effort` (1-9, default 7) for the JPEG->JXL lossless repack, settable on the Settings page and as a per-run override -- existing installs upgrade automatically and default to 7

### Fixes

- Settings page and README now call out that the Immich API base URL needs the `/api` suffix, and a failed test-connection hints at it when a 404 looks like a missing suffix
- README now notes the Docker image is multi-arch (`linux/amd64`, `linux/arm64`) and pulls the right one automatically

### Dependencies

- Bumped fastapi, uvicorn, websockets, and ruff

### Documentation & Links

- [README](https://github.com/fabianwimberger/immich-convert-originals#readme)
- [Container image](https://github.com/fabianwimberger/immich-convert-originals/pkgs/container/immich-convert-originals)

## [v2.1.0] - 2026-07-24

Adds control over which formats get converted and how they leave your library, plus routine dependency maintenance.

### Features

- Choose HEIC or AVIF as the output format instead of JPEG XL, each with its own quality setting
- Exclude specific input formats from a run entirely (e.g. leave HEIC untouched, only convert JPEG)
- Local-only output mode: write converted files to disk under `<year>/<month>` instead of uploading, with an option to keep the original alongside -- nothing in Immich is touched
- Settings page redesigned with a description, default, and example under every field, regrouped by concern

### Fixes

- Settings no longer seed from `.env` files -- the database is now the single source of truth, with an automatic upgrade path for existing installs
- Corrected third-party license documentation: FFmpeg is GPL-2.0-or-later as built by Alpine (not LGPL-only, since libavcodec links x264/x265), and added the previously-undocumented libheif/libde265/x265/x264/libaom/dav1d/rav1e/SVT-AV1 entries

### Dependencies

- Bumped fastapi, mypy, ruff, types-requests, and websockets
- Bumped actions/setup-python to v7
- Pinned CI's ruff/mypy versions to stop lint from breaking on upstream rule changes

### Documentation & Links

- [README](https://github.com/fabianwimberger/immich-convert-originals#readme)
- [Container image](https://github.com/fabianwimberger/immich-convert-originals/pkgs/container/immich-convert-originals)

## [v2.0.2] - 2026-07-18

Follow-up fixes from further real-world testing of run stability and live progress reporting.

### Fixes

- Cancelling a run now actually ends with status "cancelled" instead of silently reporting "completed"
- Progress counters can no longer be broadcast out of order, and the aggregate counter update is throttled instead of sent once per asset, keeping the live view responsive on very large runs
- exiftool metadata-copy failures keep their real error message instead of a generic one, and the JXL container rewrap exiftool needs to hold EXIF/XMP data is now accepted instead of rejected
- Skipped and failed-transcode outcomes no longer show a false "100% saved" when no output was actually produced
- Video max dimension and audio bitrate settings fields now spell out the expected units/format
- `.env.example`'s Immich connection fields are blank instead of a placeholder that gets silently treated as "configured" after a database reset

### Documentation & Links

- [README](https://github.com/fabianwimberger/immich-convert-originals#readme)
- [Container image](https://github.com/fabianwimberger/immich-convert-originals/pkgs/container/immich-convert-originals)

## [v2.0.1] - 2026-07-18

Fixes the app freezing during runs with many fast skips, along with the underlying database and crash-recovery issues that caused it.

### Fixes

- Live run log no longer rebuilds its entire table on every progress message — this froze the browser tab once fast, high-volume skips piled up
- SQLite writes are now batched into one transaction per asset and use WAL mode instead of the default rollback journal, removing the lock contention that serialized writers and blocked reads during a run
- A failure in one asset's pipeline is now recorded and skipped over instead of aborting the whole run and deleting other in-flight assets' working files
- A run interrupted by a crash or restart is now marked failed on startup instead of staying stuck "running" forever, which previously blocked retrying it

### Documentation & Links

- [README](https://github.com/fabianwimberger/immich-convert-originals#readme)
- [Container image](https://github.com/fabianwimberger/immich-convert-originals/pkgs/container/immich-convert-originals)

## [v2.0.0] - 2026-07-18

Replaces the command-line tool with a self-hosted web GUI for browsing and converting your Immich library.

### Features

- Browse assets by album or date range with thumbnails, then start a conversion run from the browser
- Live per-asset progress log during a run — filename, format, size before/after, and savings as each asset resolves
- Run history with retry-failed and CSV export of failures
- Dry runs preview real converted sizes (download + transcode, no upload) instead of a no-op
- Settings page for the Immich connection, transcode parameters, and default asset-type/archived/deleted filters

### Fixes

- Asset browsing sorts newest-first instead of oldest-first
- Browse page recovers automatically after connecting Immich, no manual reload needed
- New-run defaults now respect the saved asset-type/archived/deleted settings instead of always selecting images and videos

### Documentation & Links

- [README](https://github.com/fabianwimberger/immich-convert-originals#readme)
- [Container image](https://github.com/fabianwimberger/immich-convert-originals/pkgs/container/immich-convert-originals)

## [v1.2.0] - 2026-07-17

Restores compatibility with Immich v3, which broke this tool by removing several fields and endpoints this project depended on.

### Fixes

- Remove `deviceAssetId`/`deviceId`, both dropped from the v3 asset schema and upload payload — this was causing a `KeyError` on every asset for anyone running Immich v3
- Replace `withArchived` with the new `visibility` enum in `search/metadata`, restoring `INCLUDE_ARCHIVED` filtering
- Replace `isArchived`/`isTrashed` with `visibility` in `copy_asset_data`'s bulk update; clamp out-of-range ratings (0, -1) to null
- Use `PUT /assets/copy` for album and stack association copying instead of a manual per-album loop
- Rebuild `get_album_assets` on `POST /search/metadata` with `albumIds`, since `GET /albums/{id}` no longer returns an `assets` array — fixes a silent data-loss bug where `FILTER_ALBUM_ID` returned zero assets on v3 instead of erroring

### Compatibility

- Verified against a live Immich v3.0.3 instance end to end (full convert/upload/copy/delete pipeline and upload-failure rollback)
- Verified backward-compatible with Immich v2.7.5 by diffing both OpenAPI specs — no version branching needed
- CI now pins integration tests to Immich v3.0.3

### Documentation & Links

- [README](https://github.com/fabianwimberger/immich-convert-originals#readme)
- [Container image](https://github.com/fabianwimberger/immich-convert-originals/pkgs/container/immich-convert-originals)

## [v1.1.1] - 2026-05-09

Immich Library Converter now documents metadata preservation behavior more accurately.

### Fixes

- Clarify that replacement assets preserve EXIF/GPS data, favorite/archive/rating state, and album membership
- Align package version metadata with the release version
- Remove warning symbols from README safety text

### Documentation & Links

- [README](https://github.com/fabianwimberger/immich-convert-originals#readme)

## [v1.1.0] - 2026-05-09

CI compatibility and robustness fixes for album date filtering and download integrity verification.

### Fixes
- Album date filter now parses ISO strings to datetime before comparing — eliminates reliance on lexicographic string ordering
- Base64-decode Immich checksum before hex comparison — fixes download checksum verification that always failed
- copy_asset_data now reports album-add failures instead of silently swallowing them
- copy_asset_data only sends metadata fields explicitly present in the source asset response
- download_original fetches and verifies asset checksum from Immich before returning success
- transcode no longer runs exiftool for JPEG→JXL via cjxl (lossless repack already preserves EXIF)
- Removed dead _parse_date from config.py and dead assignment in interactive.py last_month preset
- Dockerfile ENTRYPOINT changed from python main.py to python -m app

### Documentation & Links
- https://github.com/fabianwimberger/immich-convert-originals

## [v1.0.1] - 2026-04-25

Robustness fix for malformed EXIF metadata and routine dependency updates.

### Fixes

- Handle malformed EXIF gracefully instead of aborting the run

### CI

- Bump actions/cache from 4 to 5

### Dependencies

- Bump tqdm from 4.67.1 to 4.67.3
- Bump responses from 0.25.0 to 0.26.0
- Update mypy requirement to >=1.20.1
- Update setuptools requirement to >=82.0.1
- Update types-requests requirement

### Chores

- Added community health files


### Documentation & Links

- [README](https://github.com/fabianwimberger/immich-convert-originals#readme)
- [Container image](https://github.com/fabianwimberger/immich-convert-originals/pkgs/container/immich-convert-originals)

## [v1.0.0] - 2026-04-19

**The first official release of a batch-transcoder that shrinks an Immich library to JPEG XL and AV1 in place — preserving EXIF, GPS, albums, and faces.**

Walks every asset in your Immich library, transcodes images to JPEG XL and videos to AV1, uploads the new version, copies all metadata, and removes the original. Typically reclaims 20–40% on photos and 30–50% on videos with no visible quality loss.

---

### Features

- **Image conversion** — JPEG, PNG, WebP, HEIC → JPEG XL (lossless JPEG repack via cjxl)
- **Video conversion** — MP4, MOV, MKV → AV1 in MP4 (SVT-AV1, Opus audio)
- **Metadata preservation** — EXIF, GPS, tags, albums, faces
- **Smart retry** — re-encodes with more compression if output is larger than input
- **Resumable runs** — SQLite state DB; interrupted runs skip already-converted assets, SIGINT handled gracefully
- **Dry-run mode** — preview every change before executing
- **Interactive wizard** — `--interactive` guided setup
- **Filters** — by date range, album, or asset type
- **Concurrency control** — configurable parallel workers

---

### Encoding Defaults

| Kind  | Tool     | Parameters                            |
|-------|----------|---------------------------------------|
| Image | cjxl     | distance=1.0 (visually lossless)      |
| Video | SVT-AV1  | CRF 36, preset 4, 1080p max dimension |
| Audio | Opus     | 64 kbps                               |

---

### Quick Start

```bash
mkdir immich-converter && cd immich-converter
curl -O https://raw.githubusercontent.com/fabianwimberger/immich-convert-originals/main/.env.example
mv .env.example .env
# edit .env with your Immich URL + API key, then:
mkdir -p work
docker run --rm --env-file .env -v ./work:/work \
  ghcr.io/fabianwimberger/immich-convert-originals:1.0.0
```

Defaults to dry run. Once happy, set `DRY_RUN=false` in `.env` and re-run. See the [README](https://github.com/fabianwimberger/immich-convert-originals#readme) for Docker Compose and local Python options.

**⚠️ Use at your own risk.** This tool deletes originals after conversion (recoverable via Immich trash for 30 days). Always back up first and test on a small batch with `MAX_ASSETS`.

---

### Documentation & Links

- Docs: https://github.com/fabianwimberger/immich-convert-originals#readme
- Docker image: https://github.com/fabianwimberger/immich-convert-originals/pkgs/container/immich-convert-originals

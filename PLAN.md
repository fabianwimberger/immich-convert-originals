# Improvement Plan: Usability, Tests, Interactive Mode

Goal: raise confidence and approachability of the tool by (1) exposing a real CLI with an interactive mode, (2) expanding unit-test coverage to the currently-untested modules, and (3) adding integration tests against a disposable real Immich instance seeded with a representative fixture set.

This document is structured as independently mergeable phases. Each phase lists concrete files to add/change and a definition of done, so it can be executed phase-by-phase.

---

## Phase 0 — Baseline / Guardrails (small, do first)

Before adding features, tighten the scaffolding so later phases don't regress.

- **Add `pyproject.toml`** to hold `ruff`, `mypy`, `pytest`, `coverage` config in one place (currently implicit in CI flags).
- **Add coverage threshold** to CI: `pytest --cov=app --cov-fail-under=26` to lock in today's floor (measured: 26%). Phase 3 raises it to 85.
- **Backward-compat guarantee**: no existing env var is renamed or removed in any phase. `.env` files from today keep working forever.

Deferred to later phases (listed here so nothing gets lost):
- Integration test marker → Phase 4 (adding it now with no integration tests makes `pytest -m integration` exit 5).
- `Timeouts` dataclass for injectable subprocess timeouts → Phase 3 (where tests need it).

Definition of done: `pytest --cov=app --cov-fail-under=26` green, `pyproject.toml` owns tool config, CI behavior unchanged.

---

## Phase 1 — CLI with argparse (usability foundation)

Today everything is env-only. This hurts ad-hoc use, discoverability, and interactive mode. Introduce a proper CLI while keeping env vars as fallback (Docker workflow unaffected).

Files:
- New: `app/cli.py` — builds `argparse.ArgumentParser`, one flag per `Config` field (`--dry-run/--no-dry-run`, `--concurrency`, `--max-assets`, `--asset-types`, `--image-distance`, `--video-crf`, `--filter-album-id`, `--filter-date-after/before`, `--workdir`, `--log-level`, `--log-format {text,json}`, `--interactive`, `--yes`).
- Change: `app/config.py` — add `Config.from_args_and_env(args)` merging precedence **CLI > env > default**. Keep `from_env` as thin wrapper so Docker keeps working.
- Change: `app/main.py` — entrypoint parses args first, then loads config.
- Add: `app/__main__.py` so `python -m app` works.
- Docs: update `README.md` Quick Start with `python -m app --help` section.

Usability extras in the same phase:
- **`--stats-json path`** writes a machine-readable summary (counts, bytes, failures). Useful for CI and scripting.
- **Global progress line** via `tqdm` (add as a hard dep in `requirements.txt` — trivial size, not worth the fallback code path). Replaces the "Progress: N/total" log every 50 items with a live progress bar.
- **Structured log option** (`--log-format json`) for servers that ingest logs.

### `tests/test_cli.py` (Phase 1 owns this)
- Argparse rejects invalid values before touching env.
- CLI overrides env; env overrides defaults.
- `--dry-run` / `--no-dry-run` precedence.
- `--help` exits 0 and mentions every Config field.

Definition of done: `python -m app --help` shows every config option; running with no args in a pure-env environment still behaves identically to today; Docker image still runs unchanged.

---

## Phase 2 — Interactive mode

When invoked with `--interactive` (or with no config at all on a TTY), walk the user through a guided run. Target audience: first-time users who want to try it on a subset before committing.

Recommended tool: **`questionary`** (MIT, small, works in plain TTY, supports checkbox/select/confirm). Alternative: roll hand-written `input()` prompts to avoid the dep.

Flow:
1. **Connect**: prompt for `IMMICH_API_BASE` + `IMMICH_API_KEY` (pre-filled from env if present). Call `client.test_connection()` and show server version (add a small helper `client.server_info()` hitting `/server/version`).
2. **Scope**: select asset types (checkbox), then one of:
   - Entire library
   - Specific album (fetches album list via a new `client.list_albums()` and shows name + asset count)
   - Date range (prompt for dates, offer common presets: last month, last year, 2010-2020, etc.)
3. **Limit**: ask "preview on first N assets?" (default 25). Sets `--max-assets`.
4. **Encoding**: accept defaults or tweak (CRF, distance).
5. **Preview**: run a **dry-run pass** automatically, show a summary table (count by type, projected input bytes). Do **not** estimate savings — we don't know them without transcoding. Be explicit: "Preview shows what will be processed, not estimated savings."
6. **Confirm**: "Proceed with real run on N assets? [y/N]". On `y`, disable dry-run and execute.
7. **Post-run summary**: show totals, list of failures with reasons, offer to re-run on failures only (future enhancement — just exit gracefully for now).

Files:
- New: `app/interactive.py` — contains the flow as a pure function returning a final `Config`. Keep IO wrapped so it's testable (inject a `Prompt` protocol).
- Change: `app/immich_api.py` — add `list_albums()` and `server_info()`.
- Change: `app/main.py` — if `--interactive`, hand off to `interactive.run()` before executing.

Definition of done: `python -m app --interactive` walks end-to-end on a real dev Immich, allows cancelling at each step, and produces the same logs as a non-interactive run when the user confirms.

---

## Phase 3 — Unit test coverage expansion

Current tests cover `config` and `transcode.detect_format/validate_output` only. `immich_api` (0%), `main` (0%), and the subprocess paths of `transcode` (38%) are untested. Measured starting coverage: **26%**. Target: **≥85% line coverage on `app/`** via unit tests alone (no network, no subprocesses).

Precondition refactor: introduce `transcode.Timeouts` dataclass (replacing the `IMAGE_TIMEOUT`/`VIDEO_TIMEOUT`/`PROBE_TIMEOUT`/`METADATA_TIMEOUT` module-level constants) so tests can pass short timeouts without monkey-patching internals. Keep the old constants as module-level defaults so no caller has to change.

Add test files:

### `tests/test_immich_api.py`
Mock `requests` with `responses` or `respx` (pick `responses` — simpler, sync). Cover:
- `search_assets` pagination body shape, date filters included only when set, returns `Asset` dataclasses.
- `download_original` streams bytes, returns size; returns error tuple on 404/500.
- `_request_with_retry`: retries on 429/500 with backoff (monkeypatch `time.sleep`), raises on 401/403, no retry on 404.
- `upload_asset`: happy path returns id, retries on 500, error message extraction from JSON vs text.
- `copy_asset_data`, `delete_assets`, `get_album_assets`: happy + error paths.
- `Asset.from_dict`: missing optional fields, unexpected types.

### `tests/test_transcode_subprocess.py`
Mock `subprocess.run` to exercise branching without actually shelling out:
- `transcode()` JPEG path calls `cjxl`; on `FileNotFoundError` falls back to magick; on non-zero exit also falls back.
- `transcode()` non-JPEG goes straight to magick.
- `transcode()` refuses JXL input with "Already JXL".
- `transcode_video()` skips AV1 inputs, builds correct `ffmpeg` args with/without `max_dimension`, correctly wires retry CRF.
- `detect_video_codec` timeout and missing-binary paths.
- `copy_metadata` CalledProcessError returns False but doesn't crash.

### `tests/test_main_orchestration.py`
Table-driven tests over `process_asset` with a fake `ImmichClient` (in-memory) and the real `transcode` functions replaced via `monkeypatch.setattr` with lightweight stubs. Each row asserts final `result_info["status"]`:
- Image already JXL by MIME → `skipped`, no download.
- Image dry run → `dry_run_skip`.
- Video dry run with AV1 codec → `skipped`.
- Download fails → `failed_download`.
- Transcode failure → `failed_transcode`.
- Output larger + `allow_larger=True` → still succeeds.
- Output larger + `enable_retry=True` + retry smaller → `success`.
- Output larger + retry still larger + `accept_retry_output=False` → `skipped`.
- Upload fails → `failed_upload`, no copy attempted.
- Copy fails → new asset is deleted, status `failed_copy`.
- Verify fails → new asset deleted, status `failed_verification`.
- Delete original fails → `partial_success`.
- Full happy path → `success` with correct savings_pct.

(CLI tests live in Phase 1, not here.)

Definition of done: `pytest --cov=app --cov-fail-under=85` green locally and in CI.

---

## Phase 4 — Integration tests with a real Immich instance

This is the load-bearing improvement. Unit tests can't catch upload-format mismatches, auth header quirks, or API drift across Immich versions. We need a disposable Immich.

### 4a. The fixture instance

Files:
- New: `tests/integration/docker-compose.test.yml` — copy Immich's official compose but:
  - Pin an exact Immich version via `IMMICH_TEST_TAG` (defaults set in the file; overridable in CI).
  - Use ephemeral `tmpfs` volumes for the upload library and postgres so nothing persists.
  - Bind the API to `127.0.0.1:<random-free-port>` (pytest picks the port).
  - Disable the ML container (not needed, saves minutes of startup).
- New: `tests/integration/conftest.py` — session-scoped fixtures:
  - `immich_stack`: `docker compose up -d`, poll `/api/server/ping` until healthy (120s timeout — first-run DB migrations are slow), tear down on exit via `docker compose down -v`.
  - `admin_client`: bootstraps the admin user via `/api/auth/admin-sign-up`, logs in, creates a fresh API key, returns an `ImmichClient`.
  - `seeded_library`: runs the seeder (below) once per session.
- New: `tests/integration/toxiproxy-compose.yml` (optional sidecar) — used by the fault-injection test in 4c to put a proxy in front of the Immich API so individual requests can be made to fail deterministically. Preferred over mocking the client.

### 4b. Seeder

New: `tests/integration/seeder.py` — given an `ImmichClient`, uploads a curated fixture set:

- **Images** (kept in-repo under `tests/integration/fixtures/` as small, known-good samples, ≤50KB each):
  - `sample.jpg` — standard baseline JPEG with EXIF (GPS + date).
  - `progressive.jpg` — progressive JPEG (exercises cjxl fallback to magick).
  - `sample.png` — PNG with alpha.
  - `sample.webp` — lossy WebP.
  - `sample.heic` — generated at session start via `magick convert sample.jpg sample.heic` to avoid shipping a binary from a phone and licensing ambiguity.
  - `already.jxl` — should be skipped by MIME check.
  - `tiny.png` — expected to transcode larger (exercises retry path).
- **Videos** (generated at session start via `ffmpeg` into `tmp_path_factory` so we don't ship binaries):
  - `h264.mp4` — 2 seconds, 320x240, H.264, with audio.
  - `h264_portrait.mp4` — portrait orientation (exercises scaling path).
  - `hevc.mov` — HEVC in MOV container.
  - `av1.mp4` — already AV1 (should be skipped).
- **Albums**:
  - "Vacation 2023" — contains 3 images + 1 video.
  - "Screenshots" — contains 1 image.
- **Metadata**:
  - One image marked favorite.
  - One image archived.
  - Date range spanning 2015–2024 so date filters can be tested.

The seeder should be idempotent per session (checks if already seeded via a marker tag in description).

### 4c. Test cases (`tests/integration/test_end_to_end.py`)

Each test runs the full `main()` against the live stack with a scoped config. All are marked `@pytest.mark.integration` and skipped when Docker is unavailable.

1. **Dry run lists everything, changes nothing** — assert asset count in Immich before == after, log line mentions correct format targets.
2. **Happy path: convert one JPEG** — `MAX_ASSETS=1 ASSET_TYPES=IMAGE`, assert: new JXL asset exists, original is in trash, EXIF/GPS preserved (compare via `exiftool` on the downloaded new original), album membership preserved, favorite flag preserved.
3. **Happy path: convert one video** — similar, assert new MP4/AV1 exists, duration within ±0.1s of original, audio stream present.
4. **Already-target skip**: run on `already.jxl` and `av1.mp4`; assert status=skipped, no new asset uploaded, no delete performed.
5. **Album filter**: `FILTER_ALBUM_ID` of "Vacation 2023" → only those assets touched; other album untouched.
6. **Date filter**: convert only 2020–2021 → newer/older assets untouched.
7. **Retry path**: point at `tiny.png` with aggressive distance; assert retry fires and either succeeds or gracefully skips.
8. **Upload failure handling (real fault injection)**: route the client through the toxiproxy sidecar, configure it to return 503 on the next `POST /assets`, run the converter. Assert: original asset still exists, no new asset was created, no delete was issued, status is `failed_upload`. This validates the rollback path against a real server, not a mock.
9. **Concurrency**: `CONCURRENCY=4` on 10 assets → all succeed; for each converted asset, download the new original and assert its SHA-256 is *different* from the pre-conversion SHA-256 of the original (confirms distinct content was uploaded, not accidentally duplicated across workers).
10. **Idempotency**: run twice; second run reports all assets as `skipped` (everything is already JXL/AV1), zero uploads, zero deletes.

### 4d. CI wiring

- New GH Actions job `integration` in `ci.yml`:
  - Runs only on `pull_request` + `push to main`.
  - Uses `docker compose up` in the runner (Ubuntu runners have Docker); GH Actions `services:` can't express a multi-container stack.
  - **Image cache from day one**: use `actions/cache` keyed on the pinned `IMMICH_TEST_TAG`, storing a `docker save` tarball of the Immich server + postgres + redis images. Cold cache pull ≈ 2–3 min; warm cache load ≈ 20 s. Essential given Immich server is ~1–2 GB.
  - Timeout 20 min.
  - Invocation: `pytest -m integration -v`.
- Add the `integration` pytest marker to `pyproject.toml` here (deferred from Phase 0).
- Keep the fast `test` job unmarked (unit only) so normal pushes stay under 2 min.
- Weekly `schedule:` job runs the same suite against Immich `release` tag to surface API drift without blocking PRs.

Definition of done: `make integration` and the GH job both pass on a clean clone.

---

## Phase 5 — Usability polish (post-interactive)

Pick up after Phase 4 — these are nice-to-have but cheap once the CLI and integration rig exist.

- **Resumable runs (single source of truth)**: persist per-asset outcomes in a SQLite file at `$WORKDIR/state.db`. On next run, skip `status=success` assets immediately. `--reset-state` flag to wipe. Handles the "ran for 3 days, crashed on hour 71" case.
- **Failure report**: `--export-failures failures.csv` flag derives a CSV (asset id, original filename, stage, error) from the SQLite state on demand. Not written automatically — state.db is the truth, CSV is a view.
- **Per-stage timing in log line**: `x.jpg: dl=120ms tx=3.1s up=450ms (total 4.0s)` — makes it obvious where bottlenecks are.
- **`--only-failed`** flag: re-runs only assets whose last `state.db` status was a failure.
- **Estimated time remaining** in the progress bar based on median seconds-per-asset over the last 20.
- **Graceful SIGINT**: on Ctrl-C, finish in-flight assets, then exit with summary rather than hard-killing workers mid-upload.

Definition of done: each bullet is its own small PR; none of them change default behavior.

---

## Execution order & sizing

| Phase | Size | Blocks |
|---|---|---|
| 0 Baseline | XS (~1h) | everything after |
| 1 CLI | M (~4h) | Phase 2 |
| 2 Interactive | M (~4h) | — |
| 3 Unit tests | L (~1 day) | — |
| 4 Integration | L (~2 days) | — |
| 5 Polish | pick & mix | — |

Phases 1 and 3 can go in parallel; phase 2 depends on phase 1; phase 4 is independent of 1–3 but benefits from 1 (CLI makes test invocation cleaner).

**Recommended first PR: Phase 0 alone.** It's ~1 hour, lands `pyproject.toml` and the 26% coverage floor, and unblocks everything. Then Phase 3 (biggest confidence win per hour) or Phase 1 (biggest user-facing win), whichever you feel like.

---

## Open questions for the user

1. **Interactive TUI depth**: `questionary` (colorful, single-line prompts) vs `textual` (full screen app)? Recommendation: `questionary` — lower dep surface, works over SSH, and matches the "quick wizard" use case.
2. **Ship fixture binaries in git**: OK to add ~500KB of sample images under `tests/integration/fixtures/`? Recommendation (the plan assumes this): ship the tiny JPEG/PNG/WebP/already.jxl (~5 files, ≤300KB total), generate HEIC and all videos at session start via `magick` / `ffmpeg`.

"""Tests for main.main() orchestration entrypoint."""

from unittest.mock import MagicMock

from app.main import _fmt_timings, _should_skip_by_mime_type, main


class FakeAsset:
    def __init__(self, **kwargs):
        self.id = kwargs.get("id", "a1")
        self.type = kwargs.get("type", "IMAGE")
        self.original_file_name = kwargs.get("original_file_name", "x.jpg")
        self.original_mime_type = kwargs.get("original_mime_type", "image/jpeg")
        self.file_created_at = kwargs.get("file_created_at", "2023-01-01T00:00:00Z")
        self.file_modified_at = kwargs.get("file_modified_at", "2023-01-01T00:00:00Z")


class FakeClient:
    def __init__(self, **kwargs):
        self.assets = kwargs.get("assets", [])
        self.ok = kwargs.get("ok", True)
        self.error = kwargs.get("error", None)
        self._page_called = False

    def test_connection(self):
        return self.ok, self.error

    def search_assets(self, **kwargs):
        if self._page_called:
            return []
        self._page_called = True
        return self.assets

    def get_album_assets(self, album_id):
        return self.assets


def _patch_deps(
    monkeypatch, tmp_path, assets=None, connection_ok=True, config_kwargs=None
):
    config_kwargs = config_kwargs or {}
    workdir = str(tmp_path)

    fake_config = MagicMock()
    fake_config.immich_api_base = "https://example.com/api/"
    fake_config.immich_api_key = "key"
    fake_config.dry_run = config_kwargs.get("dry_run", True)
    fake_config.concurrency = 1
    fake_config.max_assets = config_kwargs.get("max_assets", 0)
    fake_config.asset_types = config_kwargs.get("asset_types", ("IMAGE", "VIDEO"))
    fake_config.include_archived = False
    fake_config.include_deleted = False
    fake_config.filter_date_after = None
    fake_config.filter_date_before = None
    fake_config.filter_album_id = config_kwargs.get("filter_album_id")
    fake_config.image_distance = 1.0
    fake_config.image_distance_retry = 2.0
    fake_config.video_crf = 36
    fake_config.video_preset = "4"
    fake_config.video_max_dimension = 0
    fake_config.video_audio_bitrate = "64k"
    fake_config.video_crf_retry = 40
    fake_config.enable_retry = True
    fake_config.accept_retry_output = False
    fake_config.allow_larger = False
    fake_config.workdir = workdir
    fake_config.input_dir.return_value = f"{workdir}/in"
    fake_config.output_dir.return_value = f"{workdir}/out"
    fake_config.use_state = config_kwargs.get("use_state", False)
    fake_config.reset_state = config_kwargs.get("reset_state", False)
    fake_config.only_failed = config_kwargs.get("only_failed", False)
    fake_config.export_failures = config_kwargs.get("export_failures", None)
    fake_config.state_db_path.return_value = f"{workdir}/state.db"

    fake_client = FakeClient(assets=assets or [], ok=connection_ok)

    monkeypatch.setattr(
        "app.main.parse_args",
        lambda argv=None: MagicMock(
            log_level=None,
            log_format=None,
            interactive=False,
            yes=False,
            stats_json=None,
        ),
    )
    monkeypatch.setattr("app.main.Config.from_args_and_env", lambda args: fake_config)
    monkeypatch.setattr("app.main.setup_logging", lambda **kwargs: None)
    monkeypatch.setattr("app.main.ImmichClient", lambda **kwargs: fake_client)
    monkeypatch.setattr(
        "app.main.process_asset",
        lambda asset, client, cfg: {
            "status": "dry_run_skip",
            "input_bytes": 0,
            "output_bytes": 0,
            "savings_pct": 0.0,
        },
    )
    monkeypatch.setattr("app.main.tqdm", None)

    return fake_config, fake_client


class TestMainEntrypoint:
    def test_config_error_returns_1(self, monkeypatch):
        monkeypatch.setattr(
            "app.main.parse_args",
            lambda argv=None: MagicMock(
                log_level=None,
                log_format=None,
                interactive=False,
                yes=False,
                stats_json=None,
            ),
        )
        monkeypatch.setattr(
            "app.main.Config.from_args_and_env",
            lambda args: (_ for _ in ()).throw(ValueError("bad config")),
        )
        monkeypatch.setattr("app.main.setup_logging", lambda **kwargs: None)
        assert main([]) == 1

    def test_interactive_mode_aborted_returns_0(self, monkeypatch):
        monkeypatch.setattr(
            "app.main.parse_args",
            lambda argv=None: MagicMock(
                log_level=None,
                log_format=None,
                interactive=True,
                yes=False,
                stats_json=None,
            ),
        )
        monkeypatch.setattr("app.main.setup_logging", lambda **kwargs: None)
        monkeypatch.setattr("app.main.run_interactive", lambda **kwargs: None)
        assert main([]) == 0

    def test_interactive_mode_preview_then_real(self, monkeypatch, tmp_path):
        from app.config import Config

        workdir = str(tmp_path)

        fake_config = Config(
            immich_api_base="https://example.com/api/",
            immich_api_key="key",
            dry_run=True,
            concurrency=1,
            max_assets=0,
            asset_types=("IMAGE",),
            workdir=workdir,
        )

        fake_client = FakeClient(assets=[FakeAsset()], ok=True)

        monkeypatch.setattr(
            "app.main.parse_args",
            lambda argv=None: MagicMock(
                log_level=None,
                log_format=None,
                interactive=True,
                yes=True,
                stats_json=None,
            ),
        )
        monkeypatch.setattr("app.main.setup_logging", lambda **kwargs: None)
        monkeypatch.setattr("app.main.run_interactive", lambda **kwargs: fake_config)
        monkeypatch.setattr("app.main.ImmichClient", lambda **kwargs: fake_client)
        monkeypatch.setattr(
            "app.main.process_asset",
            lambda asset, client, cfg: {
                "status": "dry_run_skip",
                "input_bytes": 0,
                "output_bytes": 0,
                "savings_pct": 0.0,
            },
        )
        monkeypatch.setattr("app.main.tqdm", None)
        assert main([]) == 0

    def test_connection_failure_returns_1(self, monkeypatch, tmp_path):
        _patch_deps(monkeypatch, tmp_path, connection_ok=False)
        assert main([]) == 1

    def test_no_assets_found_returns_0(self, monkeypatch, tmp_path):
        _patch_deps(monkeypatch, tmp_path, assets=[])
        assert main([]) == 0

    def test_assets_found_returns_0(self, monkeypatch, tmp_path):
        _patch_deps(monkeypatch, tmp_path, assets=[FakeAsset()])
        assert main([]) == 0

    def test_max_assets_limits_results(self, monkeypatch, tmp_path):
        assets = [FakeAsset(id=f"a{i}") for i in range(5)]
        processed = []

        def track_process(asset, client, cfg):
            processed.append(asset.id)
            return {
                "status": "dry_run_skip",
                "input_bytes": 0,
                "output_bytes": 0,
                "savings_pct": 0.0,
            }

        _patch_deps(
            monkeypatch, tmp_path, assets=assets, config_kwargs={"max_assets": 2}
        )
        monkeypatch.setattr("app.main.process_asset", track_process)
        assert main([]) == 0
        assert len(processed) == 2

    def test_worker_exception_caught(self, monkeypatch, tmp_path):
        assets = [FakeAsset(id="a1")]

        def failing_process(asset, client, cfg):
            raise RuntimeError("boom")

        _patch_deps(monkeypatch, tmp_path, assets=assets)
        monkeypatch.setattr("app.main.process_asset", failing_process)
        assert main([]) == 0

    def test_stats_json_written(self, monkeypatch, tmp_path):
        stats_path = str(tmp_path / "stats.json")
        _patch_deps(monkeypatch, tmp_path, assets=[FakeAsset()])
        monkeypatch.setattr(
            "app.main.parse_args",
            lambda argv=None: MagicMock(
                log_level=None,
                log_format=None,
                interactive=False,
                yes=False,
                stats_json=stats_path,
            ),
        )
        assert main([]) == 0
        with open(stats_path) as f:
            import json

            data = json.load(f)
        assert data["total_assets"] == 1
        assert "status_counts" in data

    def test_progress_without_tqdm(self, monkeypatch, tmp_path):
        _patch_deps(monkeypatch, tmp_path, assets=[FakeAsset(id="a1")])
        monkeypatch.setattr("app.main.tqdm", None)
        assert main([]) == 0

    def test_progress_with_tqdm(self, monkeypatch, tmp_path):
        fake_bar = MagicMock()

        def fake_tqdm(**kwargs):
            return fake_bar

        _patch_deps(monkeypatch, tmp_path, assets=[FakeAsset(id="a1")])
        monkeypatch.setattr("app.main.tqdm", fake_tqdm)
        assert main([]) == 0
        assert fake_bar.update.called
        assert fake_bar.close.called

    def test_album_filter_path(self, monkeypatch, tmp_path):
        assets = [FakeAsset(id="a1")]
        _patch_deps(
            monkeypatch,
            tmp_path,
            assets=assets,
            config_kwargs={"filter_album_id": "album-1"},
        )
        assert main([]) == 0

    def test_state_records_outcomes(self, monkeypatch, tmp_path):
        from app.state import StateDB

        assets = [FakeAsset(id="a1"), FakeAsset(id="a2")]

        def stub_process(asset, client, cfg):
            return {
                "status": "success" if asset.id == "a1" else "failed_upload",
                "input_bytes": 100,
                "output_bytes": 50,
                "savings_pct": 50.0,
                "error": "boom" if asset.id == "a2" else None,
            }

        _patch_deps(
            monkeypatch,
            tmp_path,
            assets=assets,
            config_kwargs={"dry_run": False, "use_state": True},
        )
        monkeypatch.setattr("app.main.process_asset", stub_process)
        assert main([]) == 0

        db = StateDB(f"{tmp_path}/state.db")
        try:
            assert db.get_status("a1") == "success"
            assert db.get_status("a2") == "failed_upload"
        finally:
            db.close()

    def test_resume_skips_completed(self, monkeypatch, tmp_path):
        from app.state import StateDB

        with StateDB(f"{tmp_path}/state.db") as db:
            db.record("a1", "success", "x.jpg")

        processed = []

        def track(asset, client, cfg):
            processed.append(asset.id)
            return {
                "status": "success",
                "input_bytes": 0,
                "output_bytes": 0,
                "savings_pct": 0.0,
            }

        _patch_deps(
            monkeypatch,
            tmp_path,
            assets=[FakeAsset(id="a1"), FakeAsset(id="a2")],
            config_kwargs={"dry_run": False, "use_state": True},
        )
        monkeypatch.setattr("app.main.process_asset", track)
        assert main([]) == 0
        assert processed == ["a2"]

    def test_only_failed_filters(self, monkeypatch, tmp_path):
        from app.state import StateDB

        with StateDB(f"{tmp_path}/state.db") as db:
            db.record("a1", "success", "x.jpg")
            db.record("a2", "failed_upload", "y.jpg", error="boom")

        processed = []

        def track(asset, client, cfg):
            processed.append(asset.id)
            return {
                "status": "success",
                "input_bytes": 0,
                "output_bytes": 0,
                "savings_pct": 0.0,
            }

        _patch_deps(
            monkeypatch,
            tmp_path,
            assets=[FakeAsset(id="a1"), FakeAsset(id="a2")],
            config_kwargs={
                "dry_run": False,
                "use_state": True,
                "only_failed": True,
            },
        )
        monkeypatch.setattr("app.main.process_asset", track)
        assert main([]) == 0
        assert processed == ["a2"]

    def test_reset_state_wipes(self, monkeypatch, tmp_path):
        from app.state import StateDB

        with StateDB(f"{tmp_path}/state.db") as db:
            db.record("a1", "success", "x.jpg")

        processed = []

        def track(asset, client, cfg):
            processed.append(asset.id)
            return {
                "status": "success",
                "input_bytes": 0,
                "output_bytes": 0,
                "savings_pct": 0.0,
            }

        _patch_deps(
            monkeypatch,
            tmp_path,
            assets=[FakeAsset(id="a1")],
            config_kwargs={
                "dry_run": False,
                "use_state": True,
                "reset_state": True,
            },
        )
        monkeypatch.setattr("app.main.process_asset", track)
        assert main([]) == 0
        assert processed == ["a1"]

    def test_export_failures_written(self, monkeypatch, tmp_path):
        from app.state import StateDB

        csv_path = str(tmp_path / "failures.csv")
        with StateDB(f"{tmp_path}/state.db") as db:
            db.record("a1", "failed_upload", "y.jpg", error="boom")

        _patch_deps(
            monkeypatch,
            tmp_path,
            assets=[],
            config_kwargs={
                "dry_run": False,
                "use_state": True,
                "export_failures": csv_path,
            },
        )
        assert main([]) == 0
        content = open(csv_path).read()
        assert "a1" in content and "boom" in content

    def test_search_exception_logs_error(self, monkeypatch, tmp_path, caplog):
        class ExplodingClient:
            def test_connection(self):
                return True, None

            def search_assets(self, **kwargs):
                raise RuntimeError("network down")

            def get_album_assets(self, album_id):
                return []

        _patch_deps(
            monkeypatch,
            tmp_path,
            assets=[],
            config_kwargs={"asset_types": ("VIDEO",)},
        )
        monkeypatch.setattr("app.main.ImmichClient", lambda **kwargs: ExplodingClient())
        assert main([]) == 0
        assert "network down" in caplog.text


class TestFmtTimings:
    def test_sub_second_uses_ms(self):
        out = _fmt_timings({"dl": 0.12})
        assert "dl=120ms" in out
        assert "(total 0.1s)" in out

    def test_over_second_uses_seconds(self):
        out = _fmt_timings({"tx": 3.1})
        assert "tx=3.1s" in out
        assert "(total 3.1s)" in out

    def test_mixed_stages(self):
        out = _fmt_timings({"dl": 0.2, "tx": 2.5})
        assert "dl=200ms" in out
        assert "tx=2.5s" in out


class TestShouldSkipByMimeType:
    def test_video_asset_never_skipped_by_mime(self):
        asset = FakeAsset(type="VIDEO", original_mime_type="video/mp4")
        assert _should_skip_by_mime_type(asset) is False

    def test_image_jxl_mime_skipped(self):
        asset = FakeAsset(
            type="IMAGE",
            original_mime_type="image/jxl",
            original_file_name="x.jxl",
        )
        assert _should_skip_by_mime_type(asset) is True

    def test_image_jxl_extension_fallback(self):
        asset = FakeAsset(
            type="IMAGE",
            original_mime_type=None,
            original_file_name="photo.jxl",
        )
        assert _should_skip_by_mime_type(asset) is True

    def test_image_jpeg_not_skipped(self):
        asset = FakeAsset(
            type="IMAGE",
            original_mime_type="image/jpeg",
            original_file_name="photo.jpg",
        )
        assert _should_skip_by_mime_type(asset) is False

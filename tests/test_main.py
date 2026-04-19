"""Tests for main.main() orchestration entrypoint."""

from unittest.mock import MagicMock

from app.main import main


class FakeAsset:
    def __init__(self, **kwargs):
        self.id = kwargs.get("id", "a1")
        self.type = kwargs.get("type", "IMAGE")
        self.original_file_name = kwargs.get("original_file_name", "x.jpg")
        self.original_mime_type = kwargs.get("original_mime_type", "image/jpeg")
        self.device_id = kwargs.get("device_id", "phone1")
        self.device_asset_id = kwargs.get("device_asset_id", "da1")
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

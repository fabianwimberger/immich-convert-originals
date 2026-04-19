"""Tests for CLI argument parsing and config merging."""

import json
import logging
import sys
import pytest

from app.cli import JsonFormatter, build_parser, parse_args, setup_logging
from app.config import Config


class TestBuildParser:
    """Tests for the argparse parser construction."""

    def test_help_exits_zero(self):
        parser = build_parser()
        with pytest.raises(SystemExit) as exc:
            parser.parse_args(["--help"])
        assert exc.value.code == 0

    def test_help_mentions_all_config_fields(self, capsys):
        parser = build_parser()
        parser.print_help()
        out = capsys.readouterr().out
        fields = [
            "--immich-api-base",
            "--immich-api-key",
            "--dry-run",
            "--concurrency",
            "--max-assets",
            "--asset-types",
            "--include-archived",
            "--include-deleted",
            "--filter-date-after",
            "--filter-date-before",
            "--filter-album-id",
            "--image-distance",
            "--image-distance-retry",
            "--video-crf",
            "--video-preset",
            "--video-max-dimension",
            "--video-audio-bitrate",
            "--video-crf-retry",
            "--enable-retry",
            "--accept-retry-output",
            "--allow-larger",
            "--workdir",
            "--log-level",
            "--log-format",
            "--interactive",
            "--yes",
            "--stats-json",
        ]
        for field in fields:
            assert field in out, f"{field} missing from help"

    def test_rejects_negative_max_assets(self):
        parser = build_parser()
        with pytest.raises(SystemExit):
            parser.parse_args(["--max-assets", "-1"])

    def test_rejects_negative_image_distance(self):
        parser = build_parser()
        with pytest.raises(SystemExit):
            parser.parse_args(["--image-distance", "-0.5"])

    def test_rejects_non_integer_video_crf(self):
        parser = build_parser()
        with pytest.raises(SystemExit):
            parser.parse_args(["--video-crf", "abc"])

    def test_api_base_alias(self):
        parser = build_parser()
        args = parser.parse_args(["--api-base", "https://example.com/api"])
        assert args.immich_api_base == "https://example.com/api"

    def test_api_key_alias(self):
        parser = build_parser()
        args = parser.parse_args(["--api-key", "secret"])
        assert args.immich_api_key == "secret"


class TestParseArgs:
    """Tests for parse_args wrapper."""

    def test_parses_empty_list(self):
        args = parse_args([])
        assert args.immich_api_base is None
        assert args.dry_run is None

    def test_parses_dry_run_true(self):
        args = parse_args(["--dry-run"])
        assert args.dry_run is True

    def test_parses_no_dry_run(self):
        args = parse_args(["--no-dry-run"])
        assert args.dry_run is False

    def test_parses_concurrency(self):
        args = parse_args(["--concurrency", "4"])
        assert args.concurrency == 4

    def test_parses_asset_types(self):
        args = parse_args(["--asset-types", "IMAGE"])
        assert args.asset_types == "IMAGE"

    def test_parses_log_level(self):
        args = parse_args(["--log-level", "debug"])
        assert args.log_level == "debug"

    def test_parses_log_format(self):
        args = parse_args(["--log-format", "json"])
        assert args.log_format == "json"

    def test_parses_interactive(self):
        args = parse_args(["--interactive"])
        assert args.interactive is True

    def test_parses_stats_json(self):
        args = parse_args(["--stats-json", "/tmp/stats.json"])
        assert args.stats_json == "/tmp/stats.json"


class TestConfigMerge:
    """Tests for CLI > env > default precedence."""

    def test_cli_overrides_env(self, monkeypatch):
        monkeypatch.setenv("IMMICH_API_BASE", "https://env.example.com/api")
        monkeypatch.setenv("IMMICH_API_KEY", "env_key")
        monkeypatch.setenv("CONCURRENCY", "2")
        args = parse_args(["--concurrency", "8"])
        config = Config.from_args_and_env(args)
        assert config.concurrency == 8
        assert config.immich_api_base == "https://env.example.com/api/"

    def test_env_overrides_default(self, monkeypatch):
        monkeypatch.setenv("IMMICH_API_BASE", "https://example.com/api")
        monkeypatch.setenv("IMMICH_API_KEY", "key")
        monkeypatch.setenv("IMAGE_DISTANCE", "2.5")
        args = parse_args([])
        config = Config.from_args_and_env(args)
        assert config.image_distance == 2.5

    def test_defaults_when_nothing_set(self, monkeypatch):
        monkeypatch.delenv("IMMICH_API_BASE", raising=False)
        monkeypatch.delenv("IMMICH_API_KEY", raising=False)
        monkeypatch.delenv("DRY_RUN", raising=False)
        args = parse_args([])
        with pytest.raises(ValueError, match="IMMICH_API_BASE is required"):
            Config.from_args_and_env(args)

    def test_dry_run_cli_overrides_env(self, monkeypatch):
        monkeypatch.setenv("IMMICH_API_BASE", "https://example.com/api")
        monkeypatch.setenv("IMMICH_API_KEY", "key")
        monkeypatch.setenv("DRY_RUN", "false")
        args = parse_args(["--dry-run"])
        config = Config.from_args_and_env(args)
        assert config.dry_run is True

    def test_no_dry_run_cli_overrides_env(self, monkeypatch):
        monkeypatch.setenv("IMMICH_API_BASE", "https://example.com/api")
        monkeypatch.setenv("IMMICH_API_KEY", "key")
        monkeypatch.setenv("DRY_RUN", "true")
        args = parse_args(["--no-dry-run"])
        config = Config.from_args_and_env(args)
        assert config.dry_run is False

    def test_boolean_optional_fields(self, monkeypatch):
        monkeypatch.setenv("IMMICH_API_BASE", "https://example.com/api")
        monkeypatch.setenv("IMMICH_API_KEY", "key")
        args = parse_args(
            [
                "--include-archived",
                "--include-deleted",
                "--no-enable-retry",
                "--accept-retry-output",
                "--allow-larger",
            ]
        )
        config = Config.from_args_and_env(args)
        assert config.include_archived is True
        assert config.include_deleted is True
        assert config.enable_retry is False
        assert config.accept_retry_output is True
        assert config.allow_larger is True

    def test_video_preset_int_parsed_to_string(self, monkeypatch):
        monkeypatch.setenv("IMMICH_API_BASE", "https://example.com/api")
        monkeypatch.setenv("IMMICH_API_KEY", "key")
        args = parse_args(["--video-preset", "6"])
        config = Config.from_args_and_env(args)
        assert config.video_preset == "6"

    def test_filter_date_after_and_before(self, monkeypatch):
        monkeypatch.setenv("IMMICH_API_BASE", "https://example.com/api")
        monkeypatch.setenv("IMMICH_API_KEY", "key")
        args = parse_args(
            [
                "--filter-date-after",
                "2023-01-01",
                "--filter-date-before",
                "2023-12-31",
            ]
        )
        config = Config.from_args_and_env(args)
        assert config.filter_date_after == "2023-01-01T00:00:00.000Z"
        assert config.filter_date_before == "2023-12-31T23:59:59.999Z"

    def test_filter_album_id(self, monkeypatch):
        monkeypatch.setenv("IMMICH_API_BASE", "https://example.com/api")
        monkeypatch.setenv("IMMICH_API_KEY", "key")
        args = parse_args(["--filter-album-id", "album-123"])
        config = Config.from_args_and_env(args)
        assert config.filter_album_id == "album-123"

    def test_workdir(self, monkeypatch):
        monkeypatch.setenv("IMMICH_API_BASE", "https://example.com/api")
        monkeypatch.setenv("IMMICH_API_KEY", "key")
        args = parse_args(["--workdir", "/tmp/work"])
        config = Config.from_args_and_env(args)
        assert config.workdir == "/tmp/work"

    def test_invalid_asset_types_from_cli(self, monkeypatch):
        monkeypatch.setenv("IMMICH_API_BASE", "https://example.com/api")
        monkeypatch.setenv("IMMICH_API_KEY", "key")
        args = parse_args(["--asset-types", "AUDIO"])
        with pytest.raises(ValueError, match="Invalid ASSET_TYPES"):
            Config.from_args_and_env(args)


class TestLogging:
    """Tests for logging setup and JSON formatter."""

    def test_setup_logging_text_format(self):
        setup_logging(level="info", fmt="text")
        root = logging.getLogger()
        assert root.level == logging.INFO
        handler = root.handlers[0]
        assert isinstance(handler.formatter, logging.Formatter)

    def test_setup_logging_json_format(self):
        setup_logging(level="debug", fmt="json")
        root = logging.getLogger()
        assert root.level == logging.DEBUG
        handler = root.handlers[0]
        assert isinstance(handler.formatter, JsonFormatter)

    def test_json_formatter_output(self):
        formatter = JsonFormatter()
        record = logging.LogRecord(
            name="test",
            level=logging.INFO,
            pathname="",
            lineno=0,
            msg="hello",
            args=(),
            exc_info=None,
        )
        out = formatter.format(record)
        parsed = json.loads(out)
        assert parsed["level"] == "INFO"
        assert parsed["msg"] == "hello"
        assert "ts" in parsed

    def test_json_formatter_with_exception(self):
        formatter = JsonFormatter()
        try:
            raise ValueError("boom")
        except ValueError:
            record = logging.LogRecord(
                name="test",
                level=logging.ERROR,
                pathname="",
                lineno=0,
                msg="fail",
                args=(),
                exc_info=sys.exc_info(),
            )
        out = formatter.format(record)
        parsed = json.loads(out)
        assert parsed["level"] == "ERROR"
        assert "exception" in parsed
        assert "boom" in parsed["exception"]

"""Tests for config module."""

import pytest

from app.config import (
    Config,
    _parse_bool,
    _parse_date,
    _parse_float,
    _parse_int,
)


class TestParseBool:
    """Tests for _parse_bool function."""

    def test_default_value_when_missing(self, monkeypatch):
        monkeypatch.delenv("TEST_BOOL", raising=False)
        assert _parse_bool("TEST_BOOL", default=True) is True
        assert _parse_bool("TEST_BOOL", default=False) is False

    def test_true_values(self, monkeypatch):
        for value in ["true", "True", "TRUE", "1", "yes", "YES", "on", "ON"]:
            monkeypatch.setenv("TEST_BOOL", value)
            assert _parse_bool("TEST_BOOL", default=False) is True

    def test_false_values(self, monkeypatch):
        for value in ["false", "False", "FALSE", "0", "no", "NO", "off", "OFF"]:
            monkeypatch.setenv("TEST_BOOL", value)
            assert _parse_bool("TEST_BOOL", default=True) is False

    def test_invalid_uses_default(self, monkeypatch):
        monkeypatch.setenv("TEST_BOOL", "invalid")
        assert _parse_bool("TEST_BOOL", default=True) is True
        assert _parse_bool("TEST_BOOL", default=False) is False


class TestParseInt:
    """Tests for _parse_int function."""

    def test_default_when_missing(self, monkeypatch):
        monkeypatch.delenv("TEST_INT", raising=False)
        assert _parse_int("TEST_INT", default=42) == 42

    def test_parses_valid_integer(self, monkeypatch):
        monkeypatch.setenv("TEST_INT", "123")
        assert _parse_int("TEST_INT", default=0) == 123

    def test_parses_with_whitespace(self, monkeypatch):
        monkeypatch.setenv("TEST_INT", "  456  ")
        assert _parse_int("TEST_INT", default=0) == 456

    def test_invalid_raises_error(self, monkeypatch):
        monkeypatch.setenv("TEST_INT", "not_a_number")
        with pytest.raises(ValueError, match="Invalid integer value"):
            _parse_int("TEST_INT", default=0)

    def test_min_constraint(self, monkeypatch):
        monkeypatch.setenv("TEST_INT", "5")
        with pytest.raises(ValueError, match="must be >= 10"):
            _parse_int("TEST_INT", default=0, min=10)

    def test_max_constraint(self, monkeypatch):
        monkeypatch.setenv("TEST_INT", "100")
        with pytest.raises(ValueError, match="must be <= 50"):
            _parse_int("TEST_INT", default=0, max=50)


class TestParseFloat:
    """Tests for _parse_float function."""

    def test_default_when_missing(self, monkeypatch):
        monkeypatch.delenv("TEST_FLOAT", raising=False)
        assert _parse_float("TEST_FLOAT", default=1.5) == 1.5

    def test_parses_valid_float(self, monkeypatch):
        monkeypatch.setenv("TEST_FLOAT", "3.14")
        assert _parse_float("TEST_FLOAT", default=0.0) == 3.14

    def test_parses_integer_as_float(self, monkeypatch):
        monkeypatch.setenv("TEST_FLOAT", "42")
        assert _parse_float("TEST_FLOAT", default=0.0) == 42.0

    def test_min_constraint(self, monkeypatch):
        monkeypatch.setenv("TEST_FLOAT", "0.5")
        with pytest.raises(ValueError, match="must be >= 1.0"):
            _parse_float("TEST_FLOAT", default=0.0, min=1.0)

    def test_max_constraint(self, monkeypatch):
        monkeypatch.setenv("TEST_FLOAT", "10.0")
        with pytest.raises(ValueError, match="must be <= 5.0"):
            _parse_float("TEST_FLOAT", default=0.0, max=5.0)


class TestParseDate:
    """Tests for _parse_date function."""

    def test_none_when_missing(self, monkeypatch):
        monkeypatch.delenv("TEST_DATE", raising=False)
        assert _parse_date("TEST_DATE") is None

    def test_parses_yyyy_mm_dd_after(self, monkeypatch):
        monkeypatch.setenv("TEST_DATE_AFTER", "2023-06-15")
        result = _parse_date("TEST_DATE_AFTER")
        assert result == "2023-06-15T00:00:00.000Z"

    def test_parses_yyyy_mm_dd_before(self, monkeypatch):
        monkeypatch.setenv("TEST_DATE_BEFORE", "2023-06-15")
        result = _parse_date("TEST_DATE_BEFORE")
        assert result == "2023-06-15T23:59:59.999Z"

    def test_invalid_date_raises_error(self, monkeypatch):
        monkeypatch.setenv("TEST_DATE", "2023-13-45")
        with pytest.raises(ValueError, match="Invalid date"):
            _parse_date("TEST_DATE")

    def test_accepts_iso_format(self, monkeypatch):
        monkeypatch.setenv("TEST_DATE", "2023-06-15T10:30:00Z")
        result = _parse_date("TEST_DATE")
        assert result == "2023-06-15T10:30:00Z"


class TestConfigFromEnv:
    """Tests for Config.from_env factory method."""

    def test_required_values_missing(self, monkeypatch):
        monkeypatch.delenv("IMMICH_API_BASE", raising=False)
        monkeypatch.delenv("IMMICH_API_KEY", raising=False)
        with pytest.raises(ValueError, match="IMMICH_API_BASE is required"):
            Config.from_env()

    def test_required_api_key_missing(self, monkeypatch):
        monkeypatch.setenv("IMMICH_API_BASE", "https://example.com/api")
        monkeypatch.delenv("IMMICH_API_KEY", raising=False)
        with pytest.raises(ValueError, match="IMMICH_API_KEY is required"):
            Config.from_env()

    def test_adds_trailing_slash_to_base_url(self, monkeypatch):
        monkeypatch.setenv("IMMICH_API_BASE", "https://example.com/api")
        monkeypatch.setenv("IMMICH_API_KEY", "test_key")
        config = Config.from_env()
        assert config.immich_api_base == "https://example.com/api/"

    def test_keeps_trailing_slash_if_present(self, monkeypatch):
        monkeypatch.setenv("IMMICH_API_BASE", "https://example.com/api/")
        monkeypatch.setenv("IMMICH_API_KEY", "test_key")
        config = Config.from_env()
        assert config.immich_api_base == "https://example.com/api/"

    def test_default_values(self, monkeypatch):
        monkeypatch.setenv("IMMICH_API_BASE", "https://example.com/api")
        monkeypatch.setenv("IMMICH_API_KEY", "test_key")
        config = Config.from_env()
        assert config.dry_run is True
        assert config.concurrency == 1
        assert config.max_assets == 0
        assert config.asset_types == ("IMAGE", "VIDEO")
        assert config.image_distance == 1.0
        assert config.video_crf == 36

    def test_custom_asset_types(self, monkeypatch):
        monkeypatch.setenv("IMMICH_API_BASE", "https://example.com/api")
        monkeypatch.setenv("IMMICH_API_KEY", "test_key")
        monkeypatch.setenv("ASSET_TYPES", "IMAGE")
        config = Config.from_env()
        assert config.asset_types == ("IMAGE",)

    def test_invalid_asset_type_raises_error(self, monkeypatch):
        monkeypatch.setenv("IMMICH_API_BASE", "https://example.com/api")
        monkeypatch.setenv("IMMICH_API_KEY", "test_key")
        monkeypatch.setenv("ASSET_TYPES", "AUDIO")
        with pytest.raises(ValueError, match="Invalid ASSET_TYPES"):
            Config.from_env()

    def test_path_methods(self, monkeypatch):
        monkeypatch.setenv("IMMICH_API_BASE", "https://example.com/api")
        monkeypatch.setenv("IMMICH_API_KEY", "test_key")
        monkeypatch.setenv("WORKDIR", "/custom/work")
        config = Config.from_env()
        assert config.input_dir() == "/custom/work/in"
        assert config.output_dir() == "/custom/work/out"

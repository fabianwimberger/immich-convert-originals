"""Tests for the interactive wizard."""

from unittest.mock import MagicMock

import pytest

from app.config import Config
from app.interactive import FakePrompt, _parse_date_input, run_interactive


def _make_client(ok=True, info=None, albums=None):
    client = MagicMock()
    client.test_connection.return_value = (ok, None if ok else "bad")
    client.server_info.return_value = info or {"major": 1, "minor": 2, "patch": 3}
    client.list_albums.return_value = albums or []
    return client


def _client_factory(client):
    def factory(api_base, api_key):
        return client

    return factory


class TestParseDateInput:
    def test_empty_returns_none(self):
        assert _parse_date_input("") is None
        assert _parse_date_input("   ") is None

    def test_yyyy_mm_dd_start(self):
        assert _parse_date_input("2023-06-15") == "2023-06-15T00:00:00.000Z"

    def test_yyyy_mm_dd_end(self):
        assert (
            _parse_date_input("2023-06-15", end_of_day=True)
            == "2023-06-15T23:59:59.999Z"
        )

    def test_iso_passthrough(self):
        assert _parse_date_input("2023-06-15T10:00:00Z") == "2023-06-15T10:00:00Z"

    def test_invalid_raises(self):
        with pytest.raises(ValueError):
            _parse_date_input("not-a-date")

    def test_invalid_iso_raises(self):
        with pytest.raises(ValueError):
            _parse_date_input("2023-13-45T10:00:00Z")

    def test_iso_without_z_passthrough(self):
        assert (
            _parse_date_input("2023-06-15T10:00:00+00:00")
            == "2023-06-15T10:00:00+00:00"
        )


class TestRunInteractiveHappyPath:
    def test_returns_config_with_dry_run_true(self):
        client = _make_client()
        answers = [
            "https://example.com/api/",  # api_base
            "key123",  # api_key
            ["IMAGE"],  # asset types
            "library",  # scope
            "25",  # max_assets
            True,  # use defaults
            True,  # confirm
        ]
        prompt = FakePrompt(answers)
        config = run_interactive(
            prompt=prompt,
            env_defaults={},
            client_factory=_client_factory(client),
        )
        assert isinstance(config, Config)
        assert config.dry_run is True
        assert config.asset_types == ("IMAGE",)
        assert config.immich_api_base == "https://example.com/api/"
        assert config.immich_api_key == "key123"
        assert config.max_assets == 25

    def test_uses_env_defaults(self):
        client = _make_client()
        answers = [
            "",  # api_base (default from env)
            "",  # api_key (default from env)
            ["IMAGE"],
            "library",
            "25",
            True,
            True,
        ]
        prompt = FakePrompt(answers)
        config = run_interactive(
            prompt=prompt,
            env_defaults={
                "api_base": "https://env.example.com/api/",
                "api_key": "envkey",
            },
            client_factory=_client_factory(client),
        )
        assert config.immich_api_base == "https://env.example.com/api/"
        assert config.immich_api_key == "envkey"

    def test_connection_fail_then_succeed(self):
        client = _make_client(ok=False)
        client2 = _make_client(ok=True)
        call_count = 0

        def factory(api_base, api_key):
            nonlocal call_count
            call_count += 1
            return client if call_count == 1 else client2

        answers = [
            "https://example.com/api/",
            "key",
            "",  # retry prompt (press Enter)
            "https://example.com/api/",
            "key",
            ["VIDEO"],
            "library",
            "10",
            True,
            True,
        ]
        prompt = FakePrompt(answers)
        config = run_interactive(
            prompt=prompt,
            env_defaults={},
            client_factory=factory,
        )
        assert config is not None
        assert config.asset_types == ("VIDEO",)

    def test_connection_fails_three_times_returns_none(self):
        client = _make_client(ok=False)
        answers = [
            "https://example.com/api/",
            "key",
            "",  # retry 1
            "https://example.com/api/",
            "key",
            "",  # retry 2
            "https://example.com/api/",
            "key",
        ]
        prompt = FakePrompt(answers)
        result = run_interactive(
            prompt=prompt,
            env_defaults={},
            client_factory=_client_factory(client),
        )
        assert result is None

    def test_no_asset_types_reprompts(self):
        client = _make_client()
        answers = [
            "https://example.com/api/",
            "key",
            [],  # no types selected
            ["IMAGE", "VIDEO"],  # second try
            "library",
            "25",
            True,
            True,
        ]
        prompt = FakePrompt(answers)
        config = run_interactive(
            prompt=prompt,
            env_defaults={},
            client_factory=_client_factory(client),
        )
        assert config.asset_types == ("IMAGE", "VIDEO")

    def test_album_scope_with_albums(self):
        client = _make_client(
            albums=[
                {"id": "album-1", "album_name": "Vacation", "asset_count": 42},
                {"id": "album-2", "album_name": "Screenshots", "asset_count": 3},
            ]
        )
        answers = [
            "https://example.com/api/",
            "key",
            ["IMAGE"],
            "album",
            "album-1",
            "25",
            True,
            True,
        ]
        prompt = FakePrompt(answers)
        config = run_interactive(
            prompt=prompt,
            env_defaults={},
            client_factory=_client_factory(client),
        )
        assert config.filter_album_id == "album-1"

    def test_album_scope_no_albums_returns_none(self):
        client = _make_client(albums=[])
        answers = [
            "https://example.com/api/",
            "key",
            ["IMAGE"],
            "album",
        ]
        prompt = FakePrompt(answers)
        result = run_interactive(
            prompt=prompt,
            env_defaults={},
            client_factory=_client_factory(client),
        )
        assert result is None

    def test_date_scope_custom(self):
        client = _make_client()
        answers = [
            "https://example.com/api/",
            "key",
            ["IMAGE"],
            "dates",
            "custom",
            "2023-01-01",
            "2023-12-31",
            "25",
            True,
            True,
        ]
        prompt = FakePrompt(answers)
        config = run_interactive(
            prompt=prompt,
            env_defaults={},
            client_factory=_client_factory(client),
        )
        assert config.filter_date_after == "2023-01-01T00:00:00.000Z"
        assert config.filter_date_before == "2023-12-31T23:59:59.999Z"

    def test_date_scope_preset_all(self):
        client = _make_client()
        answers = [
            "https://example.com/api/",
            "key",
            ["IMAGE"],
            "dates",
            "all",
            "25",
            True,
            True,
        ]
        prompt = FakePrompt(answers)
        config = run_interactive(
            prompt=prompt,
            env_defaults={},
            client_factory=_client_factory(client),
        )
        assert config.filter_date_after is None
        assert config.filter_date_before is None

    def test_date_scope_preset_last_month(self):
        client = _make_client()
        answers = [
            "https://example.com/api/",
            "key",
            ["IMAGE"],
            "dates",
            "last_month",
            "25",
            True,
            True,
        ]
        prompt = FakePrompt(answers)
        config = run_interactive(
            prompt=prompt,
            env_defaults={},
            client_factory=_client_factory(client),
        )
        assert config.filter_date_after is not None
        assert config.filter_date_before is None

    def test_date_scope_preset_last_year(self):
        client = _make_client()
        answers = [
            "https://example.com/api/",
            "key",
            ["IMAGE"],
            "dates",
            "last_year",
            "25",
            True,
            True,
        ]
        prompt = FakePrompt(answers)
        config = run_interactive(
            prompt=prompt,
            env_defaults={},
            client_factory=_client_factory(client),
        )
        assert config.filter_date_after is not None
        assert config.filter_date_before is None

    def test_user_declines_confirmation_returns_none(self):
        client = _make_client()
        answers = [
            "https://example.com/api/",
            "key",
            ["IMAGE"],
            "library",
            "25",
            True,
            False,  # decline confirm
        ]
        prompt = FakePrompt(answers)
        result = run_interactive(
            prompt=prompt,
            env_defaults={},
            client_factory=_client_factory(client),
        )
        assert result is None

    def test_auto_confirm_skips_prompt(self):
        client = _make_client()
        answers = [
            "https://example.com/api/",
            "key",
            ["IMAGE"],
            "library",
            "25",
            True,
            # no confirm answer needed because auto_confirm=True
        ]
        prompt = FakePrompt(answers)
        config = run_interactive(
            prompt=prompt,
            env_defaults={},
            auto_confirm=True,
            client_factory=_client_factory(client),
        )
        assert config is not None

    def test_custom_encoding_values(self):
        client = _make_client()
        answers = [
            "https://example.com/api/",
            "key",
            ["IMAGE"],
            "library",
            "25",
            False,  # don't use defaults
            "2.5",  # image distance
            "30",  # video crf
            True,
        ]
        prompt = FakePrompt(answers)
        config = run_interactive(
            prompt=prompt,
            env_defaults={},
            client_factory=_client_factory(client),
        )
        assert config.image_distance == 2.5
        assert config.video_crf == 30

    def test_bad_max_assets_fallback(self):
        client = _make_client()
        answers = [
            "https://example.com/api/",
            "key",
            ["IMAGE"],
            "library",
            "bad",  # invalid max_assets
            True,
            True,
        ]
        prompt = FakePrompt(answers)
        config = run_interactive(
            prompt=prompt,
            env_defaults={},
            client_factory=_client_factory(client),
        )
        assert config.max_assets == 25

    def test_negative_max_assets_fallback(self):
        client = _make_client()
        answers = [
            "https://example.com/api/",
            "key",
            ["IMAGE"],
            "library",
            "-5",  # negative max_assets
            True,
            True,
        ]
        prompt = FakePrompt(answers)
        config = run_interactive(
            prompt=prompt,
            env_defaults={},
            client_factory=_client_factory(client),
        )
        assert config.max_assets == 25

    def test_negative_image_distance_fallback(self):
        client = _make_client()
        answers = [
            "https://example.com/api/",
            "key",
            ["IMAGE"],
            "library",
            "25",
            False,  # custom encoding
            "-1.0",  # negative distance
            "99",  # out of range CRF
            True,
        ]
        prompt = FakePrompt(answers)
        config = run_interactive(
            prompt=prompt,
            env_defaults={},
            client_factory=_client_factory(client),
        )
        assert config.image_distance == 1.0
        assert config.video_crf == 36

    def test_bad_encoding_values_fallback(self):
        client = _make_client()
        answers = [
            "https://example.com/api/",
            "key",
            ["IMAGE"],
            "library",
            "25",
            False,  # custom encoding
            "bad",  # invalid distance
            "bad",  # invalid CRF
            True,
        ]
        prompt = FakePrompt(answers)
        config = run_interactive(
            prompt=prompt,
            env_defaults={},
            client_factory=_client_factory(client),
        )
        assert config.image_distance == 1.0
        assert config.video_crf == 36

    def test_server_info_none(self):
        client = _make_client(info=None)
        answers = [
            "https://example.com/api/",
            "key",
            ["IMAGE"],
            "library",
            "25",
            True,
            True,
        ]
        prompt = FakePrompt(answers)
        config = run_interactive(
            prompt=prompt,
            env_defaults={},
            client_factory=_client_factory(client),
        )
        assert config is not None

    def test_server_info_empty_dict(self):
        client = _make_client(info={})
        answers = [
            "https://example.com/api/",
            "key",
            ["IMAGE"],
            "library",
            "25",
            True,
            True,
        ]
        prompt = FakePrompt(answers)
        config = run_interactive(
            prompt=prompt,
            env_defaults={},
            client_factory=_client_factory(client),
        )
        assert config is not None

    def test_empty_api_base_returns_none(self):
        client = _make_client()
        answers = [
            "",  # empty api_base
        ]
        prompt = FakePrompt(answers)
        result = run_interactive(
            prompt=prompt,
            env_defaults={},
            client_factory=_client_factory(client),
        )
        assert result is None

    def test_empty_api_key_returns_none(self):
        client = _make_client()
        answers = [
            "https://example.com/api/",
            "",  # empty api_key
        ]
        prompt = FakePrompt(answers)
        result = run_interactive(
            prompt=prompt,
            env_defaults={},
            client_factory=_client_factory(client),
        )
        assert result is None


class TestFakePrompt:
    def test_records_calls(self):
        prompt = FakePrompt(["a", "b", True])
        assert prompt.text("msg", default="x") == "a"
        assert prompt.password("pw") == "b"
        assert prompt.confirm("ok?") is True
        assert len(prompt.calls) == 3
        assert prompt.calls[0][0] == "text"
        assert prompt.calls[1][0] == "password"
        assert prompt.calls[2][0] == "confirm"

    def test_exhaustion_raises(self):
        prompt = FakePrompt([])
        with pytest.raises(RuntimeError):
            prompt.text("msg")

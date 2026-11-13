"""The video codec lists live in app.video_codecs; the JS keeps its own copies
for rendering, so these tests fail if the two drift apart."""

import re
from pathlib import Path

from app import video_codecs
from app.models.schemas import SettingsUpdate
from app.models.settings import Settings

FRONTEND_JS = Path(__file__).resolve().parents[2] / "frontend" / "js"


def _js_block(filename: str, const_name: str) -> str:
    source = (FRONTEND_JS / filename).read_text()
    match = re.search(rf"const {const_name} = \[(.*?)\n\];", source, re.S)
    assert match, f"{const_name} not found in {filename}"
    return match.group(1)


class TestSourceCodecBucket:
    def test_known_codec_is_its_own_bucket(self):
        assert video_codecs.source_codec_bucket("h264") == "h264"
        assert video_codecs.source_codec_bucket("prores") == "prores"

    def test_unlisted_codec_is_other(self):
        assert video_codecs.source_codec_bucket("theora") == "other"

    def test_other_itself_is_not_a_probe_name(self):
        # ffprobe never reports "other"; it only exists as a bucket.
        assert video_codecs.source_codec_bucket("other") == "other"


class TestDerivedValues:
    def test_default_allow_list_is_every_source_codec_in_order(self):
        assert (
            video_codecs.DEFAULT_CONVERT_VIDEO_CODECS
            == "h264,hevc,av1,vp9,vp8,mpeg4,mjpeg,prores,other"
        )

    def test_settings_column_default_matches(self):
        default = Settings.__table__.c.convert_video_codecs.default.arg
        assert default == video_codecs.DEFAULT_CONVERT_VIDEO_CODECS

    def test_hevc_column_defaults_match(self):
        cols = Settings.__table__.c
        assert cols.video_crf_hevc.default.arg == video_codecs.DEFAULT_HEVC_CRF
        assert (
            cols.video_crf_hevc_retry.default.arg == video_codecs.DEFAULT_HEVC_CRF_RETRY
        )
        assert cols.video_preset_hevc.default.arg == video_codecs.DEFAULT_HEVC_PRESET

    def test_validator_accepts_every_source_codec_and_rejects_others(self):
        SettingsUpdate(convert_video_codecs=video_codecs.DEFAULT_CONVERT_VIDEO_CODECS)
        for bad in ("divx", "h264,divx"):
            try:
                SettingsUpdate(convert_video_codecs=bad)
            except ValueError:
                continue
            raise AssertionError(f"{bad!r} should be rejected")


class TestFrontendCopiesMatch:
    def test_codec_options_match_source_codecs(self):
        block = _js_block("settings-fields.js", "VIDEO_CODEC_OPTIONS")
        values = re.findall(r'\["([a-z0-9]+)",', block)
        assert tuple(values) == video_codecs.SOURCE_VIDEO_CODECS

    def test_x265_presets_match(self):
        block = _js_block("settings-panel.js", "X265_PRESETS")
        values = re.findall(r'"([a-z]+)"', block)
        assert tuple(values) == video_codecs.X265_PRESETS

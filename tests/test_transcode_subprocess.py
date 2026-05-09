"""Tests for transcode subprocess paths using mocked subprocess.run."""

from unittest.mock import patch

import subprocess

from app.transcode import (
    Timeouts,
    copy_metadata,
    detect_video_codec,
    transcode,
    transcode_video,
    validate_video_output,
)


class FakeCompletedProcess:
    def __init__(self, returncode=0, stdout="", stderr=b""):
        self.returncode = returncode
        self.stdout = stdout
        self.stderr = stderr


class TestTranscodeImage:
    def test_jpeg_calls_cjxl(self, tmp_path):
        input_path = tmp_path / "input.jpg"
        input_path.write_bytes(b"\xff\xd8\xff" + b"\x00" * 29)
        output_path = tmp_path / "output.jxl"

        with patch("app.transcode.subprocess.run") as mock_run:
            mock_run.return_value = FakeCompletedProcess(returncode=0)
            result = transcode(str(input_path), str(output_path), 1.0)

        assert result.success is True
        # cjxl only — EXIF is preserved natively by lossless repack
        assert mock_run.call_count == 1
        assert mock_run.call_args_list[0][0][0][0] == "cjxl"

    def test_jpeg_cjxl_not_found_falls_back_to_magick(self, tmp_path):
        input_path = tmp_path / "input.jpg"
        input_path.write_bytes(b"\xff\xd8\xff" + b"\x00" * 29)
        output_path = tmp_path / "output.jxl"

        with patch("app.transcode.subprocess.run") as mock_run:
            mock_run.side_effect = [
                FileNotFoundError("cjxl not found"),
                FakeCompletedProcess(returncode=0),
                FakeCompletedProcess(returncode=0),
            ]
            result = transcode(str(input_path), str(output_path), 1.0)

        assert result.success is True
        assert mock_run.call_count == 3
        assert mock_run.call_args_list[1][0][0][0] == "magick"

    def test_jpeg_cjxl_nonzero_exit_falls_back_to_magick(self, tmp_path):
        input_path = tmp_path / "input.jpg"
        input_path.write_bytes(b"\xff\xd8\xff" + b"\x00" * 29)
        output_path = tmp_path / "output.jxl"

        with patch("app.transcode.subprocess.run") as mock_run:
            mock_run.side_effect = [
                FakeCompletedProcess(returncode=1),
                FakeCompletedProcess(returncode=0),
                FakeCompletedProcess(returncode=0),
            ]
            result = transcode(str(input_path), str(output_path), 1.0)

        assert result.success is True
        assert mock_run.call_count == 3
        assert mock_run.call_args_list[1][0][0][0] == "magick"

    def test_non_jpeg_goes_straight_to_magick(self, tmp_path):
        input_path = tmp_path / "input.png"
        input_path.write_bytes(b"\x89\x50\x4e\x47\x0d\x0a\x1a\x0a" + b"\x00" * 24)
        output_path = tmp_path / "output.jxl"

        with patch("app.transcode.subprocess.run") as mock_run:
            mock_run.side_effect = [
                FakeCompletedProcess(returncode=0),
                FakeCompletedProcess(returncode=0),
            ]
            result = transcode(str(input_path), str(output_path), 1.0)

        assert result.success is True
        assert mock_run.call_count >= 1
        assert mock_run.call_args_list[0][0][0][0] == "magick"

    def test_refuses_jxl_input(self, tmp_path):
        input_path = tmp_path / "input.jxl"
        input_path.write_bytes(b"\xff\x0a" + b"\x00" * 30)
        output_path = tmp_path / "output.jxl"

        result = transcode(str(input_path), str(output_path), 1.0)
        assert result.success is False
        assert "Already JXL" in result.error

    def test_unknown_format(self, tmp_path):
        input_path = tmp_path / "input.xyz"
        input_path.write_bytes(b"UNKNOWN")
        output_path = tmp_path / "output.jxl"

        result = transcode(str(input_path), str(output_path), 1.0)
        assert result.success is False
        assert "Could not detect input format" in result.error

    def test_custom_timeouts_passed_through(self, tmp_path):
        input_path = tmp_path / "input.jpg"
        input_path.write_bytes(b"\xff\xd8\xff" + b"\x00" * 29)
        output_path = tmp_path / "output.jxl"

        timeouts = Timeouts(image=42)
        with patch("app.transcode.subprocess.run") as mock_run:
            mock_run.return_value = FakeCompletedProcess(returncode=0)
            transcode(str(input_path), str(output_path), 1.0, timeouts=timeouts)

        # cjxl call uses the image timeout.
        assert mock_run.call_args_list[0][1]["timeout"] == 42

    def test_jpeg_cjxl_timeout_returns_error(self, tmp_path):
        input_path = tmp_path / "input.jpg"
        input_path.write_bytes(b"\xff\xd8\xff" + b"\x00" * 29)
        output_path = tmp_path / "output.jxl"

        with patch("app.transcode.subprocess.run") as mock_run:
            mock_run.side_effect = subprocess.TimeoutExpired(cmd="cjxl", timeout=5)
            result = transcode(str(input_path), str(output_path), 1.0)

        assert result.success is False
        assert "cjxl timed out" in result.error

    def test_magick_timeout_returns_error(self, tmp_path):
        input_path = tmp_path / "input.png"
        input_path.write_bytes(b"\x89\x50\x4e\x47\x0d\x0a\x1a\x0a" + b"\x00" * 24)
        output_path = tmp_path / "output.jxl"

        with patch("app.transcode.subprocess.run") as mock_run:
            mock_run.side_effect = subprocess.TimeoutExpired(cmd="magick", timeout=5)
            result = transcode(str(input_path), str(output_path), 1.0)

        assert result.success is False
        assert "ImageMagick timed out" in result.error

    def test_magick_called_process_error(self, tmp_path):
        input_path = tmp_path / "input.png"
        input_path.write_bytes(b"\x89\x50\x4e\x47\x0d\x0a\x1a\x0a" + b"\x00" * 24)
        output_path = tmp_path / "output.jxl"

        with patch("app.transcode.subprocess.run") as mock_run:
            mock_run.side_effect = subprocess.CalledProcessError(
                returncode=1, cmd="magick", stderr=b"bad input"
            )
            result = transcode(str(input_path), str(output_path), 1.0)

        assert result.success is False
        assert "ImageMagick failed" in result.error
        assert "bad input" in result.error

    def test_magick_missing_returns_not_found_error(self, tmp_path):
        input_path = tmp_path / "input.png"
        input_path.write_bytes(b"\x89\x50\x4e\x47\x0d\x0a\x1a\x0a" + b"\x00" * 24)
        output_path = tmp_path / "output.jxl"

        with patch("app.transcode.subprocess.run") as mock_run:
            mock_run.side_effect = FileNotFoundError("nope")
            result = transcode(str(input_path), str(output_path), 1.0)

        assert result.success is False
        assert "ImageMagick not found" in result.error


class TestTranscodeVideo:
    def test_skips_av1_input(self, tmp_path):
        input_path = tmp_path / "input.mp4"
        input_path.write_bytes(b"\x00" * 100)
        output_path = tmp_path / "output.mp4"

        with patch("app.transcode.subprocess.run") as mock_run:
            mock_run.return_value = FakeCompletedProcess(stdout="av1")
            result = transcode_video(
                str(input_path), str(output_path), 36, "4", 0, "64k"
            )

        assert result.success is False
        assert "Already AV1" in result.error

    def test_builds_correct_ffmpeg_args_without_scaling(self, tmp_path):
        input_path = tmp_path / "input.mp4"
        input_path.write_bytes(b"\x00" * 100)
        output_path = tmp_path / "output.mp4"

        with patch("app.transcode.subprocess.run") as mock_run:
            mock_run.return_value = FakeCompletedProcess(stdout="h264")
            result = transcode_video(
                str(input_path), str(output_path), 30, "4", 0, "128k"
            )

        assert result.success is True
        args = mock_run.call_args[0][0]
        assert "ffmpeg" in args
        assert "-crf" in args
        assert args[args.index("-crf") + 1] == "30"
        assert "-preset" in args
        assert args[args.index("-preset") + 1] == "4"
        assert "-b:a" in args
        assert args[args.index("-b:a") + 1] == "128k"
        assert "-vf" not in args

    def test_builds_correct_ffmpeg_args_with_scaling(self, tmp_path):
        input_path = tmp_path / "input.mp4"
        input_path.write_bytes(b"\x00" * 100)
        output_path = tmp_path / "output.mp4"

        with patch("app.transcode.subprocess.run") as mock_run:
            mock_run.return_value = FakeCompletedProcess(stdout="h264")
            result = transcode_video(
                str(input_path), str(output_path), 36, "4", 1080, "64k"
            )

        assert result.success is True
        args = mock_run.call_args[0][0]
        assert "-vf" in args
        scale_idx = args.index("-vf") + 1
        assert "1080" in args[scale_idx]

    def test_wires_retry_crf(self, tmp_path):
        input_path = tmp_path / "input.mp4"
        input_path.write_bytes(b"\x00" * 100)
        output_path = tmp_path / "output.mp4"

        with patch("app.transcode.subprocess.run") as mock_run:
            mock_run.return_value = FakeCompletedProcess(stdout="h264")
            result = transcode_video(
                str(input_path), str(output_path), 40, "6", 0, "64k"
            )

        assert result.success is True
        args = mock_run.call_args[0][0]
        assert args[args.index("-crf") + 1] == "40"
        assert args[args.index("-preset") + 1] == "6"

    def test_cannot_detect_codec(self, tmp_path):
        input_path = tmp_path / "input.mp4"
        input_path.write_bytes(b"\x00" * 100)
        output_path = tmp_path / "output.mp4"

        with patch("app.transcode.subprocess.run") as mock_run:
            mock_run.return_value = FakeCompletedProcess(returncode=1)
            result = transcode_video(
                str(input_path), str(output_path), 36, "4", 0, "64k"
            )

        assert result.success is False
        assert "Could not detect video codec" in result.error

    def test_ffmpeg_not_found(self, tmp_path):
        input_path = tmp_path / "input.mp4"
        input_path.write_bytes(b"\x00" * 100)
        output_path = tmp_path / "output.mp4"

        with patch("app.transcode.subprocess.run") as mock_run:
            mock_run.side_effect = [
                FakeCompletedProcess(stdout="h264"),
                FileNotFoundError("ffmpeg not found"),
            ]
            result = transcode_video(
                str(input_path), str(output_path), 36, "4", 0, "64k"
            )

        assert result.success is False
        assert "ffmpeg not found" in result.error

    def test_ffmpeg_timeout(self, tmp_path):
        input_path = tmp_path / "input.mp4"
        input_path.write_bytes(b"\x00" * 100)
        output_path = tmp_path / "output.mp4"

        with patch("app.transcode.subprocess.run") as mock_run:
            mock_run.side_effect = [
                FakeCompletedProcess(stdout="h264"),
                subprocess.TimeoutExpired("ffmpeg", 43200),
            ]
            result = transcode_video(
                str(input_path), str(output_path), 36, "4", 0, "64k"
            )

        assert result.success is False
        assert "timed out" in result.error

    def test_custom_timeouts(self, tmp_path):
        input_path = tmp_path / "input.mp4"
        input_path.write_bytes(b"\x00" * 100)
        output_path = tmp_path / "output.mp4"

        timeouts = Timeouts(video=99, probe=11)
        with patch("app.transcode.subprocess.run") as mock_run:
            mock_run.side_effect = [
                FakeCompletedProcess(stdout="h264"),
                FakeCompletedProcess(returncode=0),
            ]
            transcode_video(
                str(input_path),
                str(output_path),
                36,
                "4",
                0,
                "64k",
                timeouts=timeouts,
            )

        probe_call = mock_run.call_args_list[0]
        video_call = mock_run.call_args_list[1]
        assert probe_call[1]["timeout"] == 11
        assert video_call[1]["timeout"] == 99


class TestDetectVideoCodec:
    def test_returns_codec_on_success(self, tmp_path):
        video = tmp_path / "video.mp4"
        video.write_bytes(b"\x00" * 10)

        with patch("app.transcode.subprocess.run") as mock_run:
            mock_run.return_value = FakeCompletedProcess(stdout="h264")
            codec = detect_video_codec(str(video))

        assert codec == "h264"

    def test_returns_none_on_timeout(self, tmp_path):
        video = tmp_path / "video.mp4"
        video.write_bytes(b"\x00" * 10)

        with patch("app.transcode.subprocess.run") as mock_run:
            mock_run.side_effect = subprocess.TimeoutExpired("ffprobe", 60)
            codec = detect_video_codec(str(video))

        assert codec is None

    def test_returns_none_on_missing_binary(self, tmp_path):
        video = tmp_path / "video.mp4"
        video.write_bytes(b"\x00" * 10)

        with patch("app.transcode.subprocess.run") as mock_run:
            mock_run.side_effect = FileNotFoundError("ffprobe not found")
            codec = detect_video_codec(str(video))

        assert codec is None

    def test_custom_probe_timeout(self, tmp_path):
        video = tmp_path / "video.mp4"
        video.write_bytes(b"\x00" * 10)

        timeouts = Timeouts(probe=7)
        with patch("app.transcode.subprocess.run") as mock_run:
            mock_run.return_value = FakeCompletedProcess(stdout="hevc")
            detect_video_codec(str(video), timeouts=timeouts)

        assert mock_run.call_args[1]["timeout"] == 7


class TestCopyMetadata:
    def test_returns_true_on_success(self, tmp_path):
        src = tmp_path / "src.jpg"
        dst = tmp_path / "dst.jxl"
        src.write_bytes(b"a")
        dst.write_bytes(b"b")

        with patch("app.transcode.subprocess.run") as mock_run:
            mock_run.return_value = FakeCompletedProcess(returncode=0)
            assert copy_metadata(str(src), str(dst)) is True

    def test_returns_false_on_called_process_error(self, tmp_path):
        src = tmp_path / "src.jpg"
        dst = tmp_path / "dst.jxl"
        src.write_bytes(b"a")
        dst.write_bytes(b"b")

        with patch("app.transcode.subprocess.run") as mock_run:
            mock_run.side_effect = subprocess.CalledProcessError(1, "exiftool")
            assert copy_metadata(str(src), str(dst)) is False

    def test_returns_false_on_timeout(self, tmp_path):
        src = tmp_path / "src.jpg"
        dst = tmp_path / "dst.jxl"
        src.write_bytes(b"a")
        dst.write_bytes(b"b")

        with patch("app.transcode.subprocess.run") as mock_run:
            mock_run.side_effect = subprocess.TimeoutExpired("exiftool", 120)
            assert copy_metadata(str(src), str(dst)) is False

    def test_returns_false_on_missing_binary(self, tmp_path):
        src = tmp_path / "src.jpg"
        dst = tmp_path / "dst.jxl"
        src.write_bytes(b"a")
        dst.write_bytes(b"b")

        with patch("app.transcode.subprocess.run") as mock_run:
            mock_run.side_effect = FileNotFoundError("exiftool not found")
            assert copy_metadata(str(src), str(dst)) is False

    def test_custom_metadata_timeout(self, tmp_path):
        src = tmp_path / "src.jpg"
        dst = tmp_path / "dst.jxl"
        src.write_bytes(b"a")
        dst.write_bytes(b"b")

        timeouts = Timeouts(metadata=13)
        with patch("app.transcode.subprocess.run") as mock_run:
            mock_run.return_value = FakeCompletedProcess(returncode=0)
            copy_metadata(str(src), str(dst), timeouts=timeouts)

        assert mock_run.call_args[1]["timeout"] == 13


class TestValidateVideoOutput:
    def test_valid_video(self, tmp_path):
        video = tmp_path / "video.mp4"
        video.write_bytes(b"\x00" * 10)

        with patch("app.transcode.subprocess.run") as mock_run:
            mock_run.return_value = FakeCompletedProcess(stdout="12.5")
            assert validate_video_output(str(video)) is True

    def test_empty_file(self, tmp_path):
        video = tmp_path / "video.mp4"
        video.write_bytes(b"")
        assert validate_video_output(str(video)) is False

    def test_nonexistent_file(self, tmp_path):
        assert validate_video_output(str(tmp_path / "missing.mp4")) is False

    def test_invalid_duration(self, tmp_path):
        video = tmp_path / "video.mp4"
        video.write_bytes(b"\x00" * 10)

        with patch("app.transcode.subprocess.run") as mock_run:
            mock_run.return_value = FakeCompletedProcess(stdout="N/A")
            assert validate_video_output(str(video)) is False

    def test_custom_timeout(self, tmp_path):
        video = tmp_path / "video.mp4"
        video.write_bytes(b"\x00" * 10)

        timeouts = Timeouts(probe=5)
        with patch("app.transcode.subprocess.run") as mock_run:
            mock_run.return_value = FakeCompletedProcess(stdout="1.0")
            validate_video_output(str(video), timeouts=timeouts)

        assert mock_run.call_args[1]["timeout"] == 5

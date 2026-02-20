"""Tests for transcode module."""

from app.transcode import (
    MAGIC_BYTES,
    detect_format,
    validate_output,
)


class TestDetectFormat:
    """Tests for detect_format function using magic bytes."""

    def test_detects_png(self, tmp_path):
        # PNG magic bytes: 0x89 0x50 0x4E 0x47 0x0D 0x0A 0x1A 0x0A
        png_file = tmp_path / "test.png"
        png_file.write_bytes(b"\x89\x50\x4e\x47\x0d\x0a\x1a\x0a" + b"\x00" * 24)
        assert detect_format(str(png_file)) == "png"

    def test_detects_jpg(self, tmp_path):
        # JPEG magic bytes: 0xFF 0xD8 0xFF
        jpg_file = tmp_path / "test.jpg"
        jpg_file.write_bytes(b"\xff\xd8\xff" + b"\x00" * 29)
        assert detect_format(str(jpg_file)) == "jpg"

    def test_detects_jxl_codestream(self, tmp_path):
        # JXL bare codestream: 0xFF 0x0A
        jxl_file = tmp_path / "test.jxl"
        jxl_file.write_bytes(b"\xff\x0a" + b"\x00" * 30)
        assert detect_format(str(jxl_file)) == "jxl"

    def test_detects_jxl_container(self, tmp_path):
        # JXL ISOBMFF container
        jxl_file = tmp_path / "test.jxl"
        magic = b"\x00\x00\x00\x0c\x4a\x58\x4c\x20\x0d\x0a\x87\x0a"
        jxl_file.write_bytes(magic + b"\x00" * 20)
        assert detect_format(str(jxl_file)) == "jxl"

    def test_detects_gif(self, tmp_path):
        # GIF magic bytes: 0x47 0x49 0x46 0x38
        gif_file = tmp_path / "test.gif"
        gif_file.write_bytes(b"\x47\x49\x46\x38" + b"\x00" * 28)
        assert detect_format(str(gif_file)) == "gif"

    def test_detects_bmp(self, tmp_path):
        # BMP magic bytes: 0x42 0x4D
        bmp_file = tmp_path / "test.bmp"
        bmp_file.write_bytes(b"\x42\x4d" + b"\x00" * 30)
        assert detect_format(str(bmp_file)) == "bmp"

    def test_detects_tiff_le(self, tmp_path):
        # TIFF little-endian: 0x49 0x49 0x2A 0x00
        tiff_file = tmp_path / "test.tiff"
        tiff_file.write_bytes(b"\x49\x49\x2a\x00" + b"\x00" * 28)
        assert detect_format(str(tiff_file)) == "tiff"

    def test_detects_tiff_be(self, tmp_path):
        # TIFF big-endian: 0x4D 0x4D 0x00 0x2A
        tiff_file = tmp_path / "test.tiff"
        tiff_file.write_bytes(b"\x4d\x4d\x00\x2a" + b"\x00" * 28)
        assert detect_format(str(tiff_file)) == "tiff"

    def test_detects_webp(self, tmp_path):
        # RIFF container with WEBP brand
        webp_file = tmp_path / "test.webp"
        # RIFF....WEBP
        data = b"\x52\x49\x46\x46" + b"\x00" * 4 + b"\x57\x45\x42\x50"
        webp_file.write_bytes(data + b"\x00" * 20)
        assert detect_format(str(webp_file)) == "webp"

    def test_detects_avi(self, tmp_path):
        # RIFF container with AVI brand
        avi_file = tmp_path / "test.avi"
        # RIFF....AVI
        data = b"\x52\x49\x46\x46" + b"\x00" * 4 + b"\x41\x56\x49\x20"
        avi_file.write_bytes(data + b"\x00" * 20)
        assert detect_format(str(avi_file)) == "avi"

    def test_detects_mkv(self, tmp_path):
        # Matroska magic bytes: 0x1A 0x45 0xDF 0xA3
        mkv_file = tmp_path / "test.mkv"
        mkv_file.write_bytes(b"\x1a\x45\xdf\xa3" + b"\x00" * 28)
        assert detect_format(str(mkv_file)) == "mkv"

    def test_detects_heic(self, tmp_path):
        # ftyp container with heic brand
        heic_file = tmp_path / "test.heic"
        # ....ftypheic
        data = b"\x00" * 4 + b"ftyp" + b"heic"
        heic_file.write_bytes(data + b"\x00" * 24)
        assert detect_format(str(heic_file)) == "heic"

    def test_detects_avif(self, tmp_path):
        # ftyp container with avif brand
        avif_file = tmp_path / "test.avif"
        # ....ftypavif
        data = b"\x00" * 4 + b"ftyp" + b"avif"
        avif_file.write_bytes(data + b"\x00" * 24)
        assert detect_format(str(avif_file)) == "avif"

    def test_detects_mp4(self, tmp_path):
        # ftyp container with mp42 brand
        mp4_file = tmp_path / "test.mp4"
        # ....ftypmp42
        data = b"\x00" * 4 + b"ftyp" + b"mp42"
        mp4_file.write_bytes(data + b"\x00" * 24)
        assert detect_format(str(mp4_file)) == "mp4"

    def test_detects_quicktime(self, tmp_path):
        # Older QuickTime without ftyp (moov atom)
        mov_file = tmp_path / "test.mov"
        # ....moov
        data = b"\x00" * 4 + b"moov" + b"\x00" * 24
        mov_file.write_bytes(data)
        assert detect_format(str(mov_file)) == "mp4"

    def test_returns_none_for_unknown(self, tmp_path):
        unknown_file = tmp_path / "test.xyz"
        unknown_file.write_bytes(b"UNKNOWN FORMAT DATA" * 2)
        assert detect_format(str(unknown_file)) is None

    def test_returns_none_for_empty_file(self, tmp_path):
        empty_file = tmp_path / "empty"
        empty_file.write_bytes(b"")
        assert detect_format(str(empty_file)) is None

    def test_returns_none_for_nonexistent_file(self, tmp_path):
        nonexistent = tmp_path / "does_not_exist"
        assert detect_format(str(nonexistent)) is None


class TestValidateOutput:
    """Tests for validate_output function."""

    def test_validates_existing_file_with_correct_format(self, tmp_path):
        # Create a valid PNG file
        png_file = tmp_path / "output.png"
        png_file.write_bytes(b"\x89\x50\x4e\x47\x0d\x0a\x1a\x0a" + b"\x00" * 24)
        assert validate_output(str(png_file), "png") is True

    def test_fails_for_wrong_format(self, tmp_path):
        # Create a PNG but claim it's JXL
        png_file = tmp_path / "output.png"
        png_file.write_bytes(b"\x89\x50\x4e\x47\x0d\x0a\x1a\x0a" + b"\x00" * 24)
        assert validate_output(str(png_file), "jxl") is False

    def test_fails_for_nonexistent_file(self, tmp_path):
        nonexistent = tmp_path / "does_not_exist"
        assert validate_output(str(nonexistent), "png") is False

    def test_fails_for_empty_file(self, tmp_path):
        empty_file = tmp_path / "empty"
        empty_file.write_bytes(b"")
        assert validate_output(str(empty_file), "png") is False


class TestMagicBytesConstants:
    """Tests for MAGIC_BYTES dictionary."""

    def test_all_signatures_are_bytes(self):
        for signature, fmt in MAGIC_BYTES.items():
            assert isinstance(signature, bytes)
            assert isinstance(fmt, str)

    def test_jpeg_has_short_signature(self):
        # JPEG only needs 3 bytes
        assert MAGIC_BYTES[b"\xff\xd8\xff"] == "jpg"

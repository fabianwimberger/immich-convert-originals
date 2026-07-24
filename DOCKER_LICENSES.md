# Third-Party Licenses

This Docker image contains the following third-party software packages.

**How this project uses them:** the application's own code (MIT-licensed) invokes `ffmpeg`, `magick`, `cjxl`, and `exiftool` as separate subprocesses via their command-line interfaces — it never links against any of the libraries below in-process. Copyleft obligations (LGPL, GPL) attach to those binaries as bundled in this image, not to this project's own source. What GPL/LGPL does require of anyone distributing this image is covered below: making source available and keeping license notices intact for the affected packages, which this document and Alpine's own package repositories satisfy.

## Core Dependencies

### libjxl / libjxl-tools
- **License:** Apache-2.0 / BSD-3-Clause
- **Source:** https://github.com/libjxl/libjxl
- **Description:** JPEG XL image format reference implementation

### ImageMagick
- **License:** Apache-2.0
- **Source:** https://github.com/ImageMagick/ImageMagick
- **Description:** Image manipulation suite

### FFmpeg
- **License:** GPL-2.0-or-later (as built by Alpine)
- **Source:** https://ffmpeg.org/download.html
- **Description:** Audio/video processing toolkit
- **Note:** FFmpeg itself is dual-licensed LGPL/GPL depending on build configuration. Alpine's official `ffmpeg` package links directly against x264 and x265 (both GPL, see below), which makes the compiled binary GPL-2.0-or-later as distributed in this image — not LGPL-only. Source is available via Alpine's package repositories (see below).

### libheif
- **License:** LGPL-3.0-or-later
- **Source:** https://github.com/strukturag/libheif
- **Description:** HEIF/HEIC/AVIF encoder and decoder library backing ImageMagick's HEIC delegate; used for HEIC and AVIF input and output

### libde265
- **License:** LGPL-3.0-or-later
- **Source:** https://github.com/strukturag/libde265
- **Description:** HEVC (H.265) decoder used by libheif to read HEIC images

### x265
- **License:** GPL-2.0-or-later (commercial license also available from MulticoreWare)
- **Source:** https://bitbucket.org/multicoreware/x265_git
- **Description:** HEVC (H.265) encoder — the codec libheif uses to write HEIC output

### x264
- **License:** GPL-2.0-or-later (commercial license also available)
- **Source:** https://www.videolan.org/developers/x264.html
- **Description:** H.264 encoder, bundled as one of libheif's available encoder plugins

### libaom
- **License:** BSD-2-Clause, with an accompanying Alliance for Open Media Patent License 1.0
- **Source:** https://aomedia.googlesource.com/aom/
- **Description:** AV1 encoder/decoder reference implementation, used for AVIF output

### dav1d
- **License:** BSD-2-Clause
- **Source:** https://code.videolan.org/videolan/dav1d
- **Description:** AV1 decoder, used for reading AVIF images

### rav1e
- **License:** BSD-2-Clause
- **Source:** https://github.com/xiph/rav1e
- **Description:** AV1 encoder, available as one of libheif's AVIF encoder plugins

### SVT-AV1
- **License:** BSD-2-Clause-Patent
- **Source:** https://gitlab.com/AOMediaCodec/SVT-AV1
- **Description:** AV1 encoder used both for video conversion (via FFmpeg's libsvtav1) and as one of libheif's AVIF encoder plugins

### ExifTool (perl-image-exiftool)
- **License:** Artistic-1.0-Perl OR GPL-1.0-or-later
- **Source:** https://exiftool.org/
- **Description:** EXIF metadata reader/writer

### Python
- **License:** PSF-2.0
- **Source:** https://www.python.org/downloads/source/
- **Description:** Programming language runtime

## Alpine Linux Base

### Alpine Linux
- **License:** MIT
- **Source:** https://alpinelinux.org/downloads/
- **Description:** Linux distribution

## Source Code Availability

In compliance with open-source license requirements (particularly LGPL/GPL for FFmpeg and its codec libraries), source code for all included packages can be obtained from:

1. **Alpine Package Repositories:** https://pkgs.alpinelinux.org/packages
2. **Individual project websites:** Listed above for each package

To extract the exact source packages used in a specific image version:

```bash
# Run this inside the container to list installed packages
apk info -v | sort

# Download specific package sources from Alpine
# Example for libjxl version X.Y.Z:
# https://pkgs.alpinelinux.org/package/v3.21/community/x86_64/libjxl
```

## License Texts

Full license texts are included in the image at `/usr/share/licenses/` (where available) or can be found at:
- Apache-2.0: https://www.apache.org/licenses/LICENSE-2.0
- BSD-3-Clause: https://opensource.org/licenses/BSD-3-Clause
- BSD-2-Clause: https://opensource.org/licenses/BSD-2-Clause
- GPL-2.0: https://www.gnu.org/licenses/old-licenses/gpl-2.0.html
- LGPL-2.1: https://www.gnu.org/licenses/old-licenses/lgpl-2.1.html
- LGPL-3.0: https://www.gnu.org/licenses/lgpl-3.0.html
- Artistic-1.0-Perl: https://dev.perl.org/licenses/artistic.html
- GPL-1.0: https://www.gnu.org/licenses/old-licenses/gpl-1.0.html
- MIT: https://opensource.org/licenses/MIT
- PSF-2.0: https://docs.python.org/3/license.html

## Trademarks

All trademarks, service marks, and trade names are the property of their respective owners.

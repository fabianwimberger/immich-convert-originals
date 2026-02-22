# Third-Party Licenses

This Docker image contains the following third-party software packages:

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
- **License:** LGPL-2.1-or-later
- **Source:** https://ffmpeg.org/download.html
- **Description:** Audio/video processing toolkit
- **Note:** This is dynamically linked as required by LGPL. Source code is available at the URL above.

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

In compliance with open-source license requirements (particularly LGPL for FFmpeg), source code for all included packages can be obtained from:

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
- LGPL-2.1: https://www.gnu.org/licenses/old-licenses/lgpl-2.1.html
- Artistic-1.0-Perl: https://dev.perl.org/licenses/artistic.html
- GPL-1.0: https://www.gnu.org/licenses/old-licenses/gpl-1.0.html
- MIT: https://opensource.org/licenses/MIT
- PSF-2.0: https://docs.python.org/3/license.html

## Trademarks

All trademarks, service marks, and trade names are the property of their respective owners.

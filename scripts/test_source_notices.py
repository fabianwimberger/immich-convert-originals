import unittest
from unittest.mock import patch

from source_notices import render_notice


class SourceNoticesTest(unittest.TestCase):
    def test_installed_packages_are_listed_for_their_own_architectures(self):
        commit = "a" * 40
        common = f"P:ffmpeg\nV:8.1-r0\nL:GPL-2.0-or-later\no:ffmpeg\nc:{commit}\n"
        arm_only = f"P:libavcodec\nV:8.1-r0\nL:GPL-2.0-or-later\no:ffmpeg\nc:{commit}\n"
        permissive = "P:musl\nL:MIT\no:musl\n"
        with patch(
            "source_notices.packaging_url", return_value="https://example.org/ffmpeg"
        ) as url:
            notice = render_notice(
                "image@index",
                "v2.9.0",
                {"amd64": "amd64-digest", "arm64": "arm64-digest"},
                {
                    "amd64": common + "\n" + permissive,
                    "arm64": common + "\n" + arm_only,
                },
            )
        url.assert_called_once_with(("ffmpeg", commit))
        self.assertIn("| ffmpeg | GPL-2.0-or-later | amd64, arm64 |", notice)
        self.assertIn("| libavcodec | GPL-2.0-or-later | arm64 |", notice)
        self.assertNotIn("musl", notice)

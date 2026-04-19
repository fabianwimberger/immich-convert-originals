"""Tests for app.__main__ entrypoint."""

import sys
from unittest.mock import patch


class TestMainModule:
    def test_imports_main(self):
        with patch.dict(sys.modules, {"app.main": type(sys)("app.main")}):
            import app.main

            app.main.main = lambda argv=None: 0
            import app.__main__

            assert hasattr(app.__main__, "main")

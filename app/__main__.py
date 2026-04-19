"""Allow running as `python -m app`."""

import sys
from pathlib import Path

package_dir = Path(__file__).parent
sys.path.insert(0, str(package_dir))

from main import main  # noqa: E402

if __name__ == "__main__":
    sys.exit(main())

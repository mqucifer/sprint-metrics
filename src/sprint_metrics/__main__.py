"""Allow the command to run as ``python -m sprint_metrics``."""

import sys

from sprint_metrics.cli import main

if __name__ == "__main__":
    sys.exit(main())

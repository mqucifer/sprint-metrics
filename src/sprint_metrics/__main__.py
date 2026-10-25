"""Allow the service to start as ``python -m sprint_metrics``."""

import sys

from sprint_metrics.service import main

if __name__ == "__main__":
    sys.exit(main())

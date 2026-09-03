"""arafix CLI entrypoint for python -m arafix."""

from __future__ import annotations

import sys

from arafix.cli import main

if __name__ == "__main__":
    sys.exit(main())

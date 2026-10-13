#!/usr/bin/env python3
"""Bootstrap the native manager from this explicit, trusted source checkout."""
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from mia.operations import main

if __name__ == "__main__":
    main()

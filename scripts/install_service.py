#!/usr/bin/env python3
"""Explicit operator entrypoint: render/review a plan, then apply its exact hash."""
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from mia.installation import main

if __name__ == "__main__":
    main()

#!/usr/bin/env python3
"""airc — point d'entrée du compilateur AirLang (voir `compiler/cli.py`)."""
import sys

from compiler.cli import main

if __name__ == "__main__":
    sys.exit(main())

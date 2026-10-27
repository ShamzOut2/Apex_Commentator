"""Entry point for the packaged app (PyInstaller runs this file)."""

import multiprocessing
import sys

from apex.__main__ import main

if __name__ == "__main__":
    multiprocessing.freeze_support()
    sys.exit(main())

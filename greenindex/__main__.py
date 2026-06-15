"""Permette di eseguire il pacchetto con `python -m greenindex`."""

import sys

from .cli import main

if __name__ == "__main__":
    sys.exit(main())

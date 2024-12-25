#!./venv/bin/python

import pathlib

from common.db import apply_migrations

def main() -> None:
    apply_migrations(pathlib.Path(__file__).parent / "migrations")

if __name__ == "__main__":
    main()

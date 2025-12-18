"""
Compile the translations so that they could be used by the application
"""

import os
import pathlib
import subprocess


def main():
    os.chdir(pathlib.Path(__file__).parent)

    subprocess.run(['pybabel', 'compile', '--directory=locales', '--domain=bot', '--use-fuzzy'])


if __name__ == "__main__":
    main()

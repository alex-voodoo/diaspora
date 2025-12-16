#!./venv/bin/python

import subprocess

subprocess.run(['pybabel', 'compile', '--directory=locales', '--domain=bot', '--use-fuzzy'])

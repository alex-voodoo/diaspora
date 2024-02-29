#!./venv/bin/python

import subprocess

subprocess.run(['pybabel', 'extract', '--input-dirs=.', '--output-file=locales/bot.pot', '--ignore-dirs=venv', '--no-wrap', '--omit-header'])

subprocess.run(['pybabel', 'update', '--input-file=locales/bot.pot', '--output-dir=locales', '--domain=bot', '--no-wrap', '--omit-header'])

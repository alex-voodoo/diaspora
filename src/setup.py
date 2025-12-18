"""
Sets up a new instance of the bot

This script creates a new empty database and renders `settings.yaml` based on `common/settings.py` and the Telegram API
key provided by the user at the run time.
"""

import os.path
import pathlib

from common.settings import INVALID_BOT_TOKEN, settings, update_settings_yaml


def main() -> None:
    os.chdir(pathlib.Path(__file__).parent)

    # Create settings.yaml
    bot_token = input("Please enter the API token of your bot: ") if settings.BOT_TOKEN == INVALID_BOT_TOKEN else ""

    update_settings_yaml(bot_token)

    print("The first step of your setup is complete.  Refer to README.md for more information.")


if __name__ == "__main__":
    main()

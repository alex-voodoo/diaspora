"""
Create or update the configuration file

This script either renders a new `settings.yaml` with a Telegram API token provided by the user at run time, or updates
the existing settings, preserving the values overridden by the user.
"""

import os.path
import pathlib

from common.settings import INVALID_BOT_TOKEN, settings, update_settings_yaml


def main() -> None:
    os.chdir(pathlib.Path(__file__).parent)

    # Create settings.yaml
    bot_token = input("Please enter the API token of your bot: ") if settings.BOT_TOKEN == INVALID_BOT_TOKEN else ""

    update_settings_yaml(bot_token)


if __name__ == "__main__":
    main()

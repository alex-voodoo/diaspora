"""
Effective configuration of the bot

Defines the default configuration and loads the user-defined settings from the external configuration file, which is
either `settings.yaml` located near the entry point script (`./bot.py`) if the bot works in direct mode, or
`/usr/local/etc/diaspora/settings.yaml` in system service mode.
"""

import logging
import os
import pathlib
import shutil
import datetime

import yaml


INVALID_BOT_TOKEN = "%BOT_TOKEN%"

_SETTINGS_FILENAME = "settings.yaml"


class Settings:
    def __init__(self):
        # Part of this file between two YAML_SETTINGS markers is parsed by setup.py to generate settings.yaml.
        # Each setting must have a default value that will be used if the user does not override it.
        # The value is parsed with eval(), and must be compatible with yaml.dump().  In particular, tuples are not
        # welcome, lists should be used instead.

        # YAML_SETTINGS
        # --------------------------------------------------------------------------------------------------------------
        # Mandatory settings

        # Token of the bot, obtained from BotFather.
        self.BOT_TOKEN = "%BOT_TOKEN%"
        # ID of the chat with the developer
        self.DEVELOPER_CHAT_ID = 0
        # ID of the main chat where the bot should have administrator privileges
        self.MAIN_CHAT_ID = 0

        # --------------------------------------------------------------------------------------------------------------
        # General settings

        # Bot name may imply its "gender" that affects "personal" messages, like "I am the host" vs. "I am the hostess".
        # This setting tells which one to pick.  Default is false.
        self.BOT_IS_MALE = False
        # Generic delay in seconds for self-destructing messages.  Default is 60.
        self.DELETE_MESSAGE_TIMEOUT = 60
        # Administrators (list of objects where each record has Telegram ID and Telegram username of the administrator).
        # These users have access to the bot's `/admin` command.  Example:
        #
        # ADMINISTRATORS:
        # - id: 0
        #   username: AlexVoodoo
        # - id: 1
        #   username: JoeBlade
        #
        # Default is empty list.
        self.ADMINISTRATORS = []

        # --------------------------------------------------------------------------------------------------------------
        # Internationalisation
        #
        # The official documentation suggests that bots should switch to the user's language or fall back to English.
        # This is not completely adequate for this bot that is designed for groups where certain language may be
        # desirable by most users, and the default English may be not optimal.
        #
        # The settings below define the "standard" behaviour suggested by the Telegram documentation, but may be
        # overridden in settings.yaml.

        # Whether the bot should try to switch to the user's language.  Default is true.
        self.SPEAK_USER_LANGUAGE = True
        # Language to fall back to if there is no translation to the user's language. Default is "en".
        self.DEFAULT_LANGUAGE = "en"
        # Supported languages.  Must be a subset of languages that present in the `locales` directory.  Default is a
        # list that contains all available languages.
        self.SUPPORTED_LANGUAGES = ["en", "ru"]

        # --------------------------------------------------------------------------------------------------------------
        # User directory settings
        #
        # The core function of this bot is to keep records submitted by users, and to render the list of those records
        # at request.  The more users register themselves with the bot, the longer the list becomes, and at some moment
        # it can exceed the limit that Telegram has for message size.  Should that happen, the bot will switch to
        # two-step mode when  displaying the user directory: first only the list of categories will be rendered, and the
        # user will then select a category and get the list of users in that category.

        # Maximum length of a message that the bot should send to the users.  Default is 4096, which is the hard limit
        # at the server side.
        self.MAX_MESSAGE_LENGTH = 4096
        # Whether to force two-step mode always.  Default is false.
        self.SHOW_CATEGORIES_ALWAYS = False
        # Maximum length of the Location.  0 means no limit (not recommended).  Default is 30.
        self.SERVICES_LOCATION_MAX_LENGTH = 30
        # Maximum length of the Occupation.  0 means no limit (not recommended).  Default is 30.
        self.SERVICES_OCCUPATION_MAX_LENGTH = 30
        # Maximum length of the Description.  0 means no limit (not recommended).  Default is 1000.
        self.SERVICES_DESCRIPTION_MAX_LENGTH = 1000
        # Whether to include administrators into statistics report.  Default is false.
        self.SERVICES_STATS_INCLUDE_ADMINISTRATORS = False

        # --------------------------------------------------------------------------------------------------------------
        # Greeting new users
        #
        # The bot can reply to each service message about a new user joining the group.  These bot replies can be
        # deleted by the bot after the specified delay.

        # Whether to greet users that join the group.  Default is true.
        self.GREETING_ENABLED = True
        # Delay in seconds for deleting the greeting, 0 for not deleting the greetings.  Default is 300.
        self.GREETING_TIMEOUT = 300

        # --------------------------------------------------------------------------------------------------------------
        # Services moderation
        #
        # The bot can ask the moderators to approve changes made by users to their data records.

        # Whether moderation of services is enabled.  Default is true.
        self.SERVICES_MODERATION_ENABLED = True
        # Whether moderation of services is "lazy" (true) or "mandatory" (false).  Default is true.
        self.SERVICES_MODERATION_IS_LAZY = True

        # --------------------------------------------------------------------------------------------------------------
        # Language moderation
        #
        # The bot can ask people in the main chat to speak the default language.  If the bot detects too many messages
        # written in languages other than the default one, it posts a message that reminds the people about rules of the
        # group.

        # Whether bot controls languages.  Default is false.
        self.LANGUAGE_MODERATION_ENABLED = False
        #
        # Maximum number of languages in non-default language.  Default is 3.
        self.LANGUAGE_MODERATION_MAX_FOREIGN_MESSAGE_COUNT = 3
        #
        # Minimum number of words in a message that the bot should evaluate when detecting the language.  Default is 3.
        self.LANGUAGE_MODERATION_MIN_WORD_COUNT = 3

        # --------------------------------------------------------------------------------------------------------------
        # Antispam
        #
        # The bot can detect and delete spam messages.  Spammers in Telegram are normally regular users that join the
        # group, sit silent for some time, and then send their junk, hoping that someone will see and buy it before the
        # moderators react.
        # Telegram blocks user accounts that have been reported as spammers, which makes it not worth it trying to mimic
        # the good user before sending spam.  Therefore, to eliminate most spam, it should be enough to evaluate the
        # first message a new user sends to the group.

        # Enabled layers of spam detection.  Can be any combination of: emojis, keywords, openai.  Order does not make
        # any difference.  Example:
        #
        # ANTISPAM_ENABLED:
        # - openai
        # - emojis
        # - keywords
        #
        # Default is empty list.
        self.ANTISPAM_ENABLED = []
        # Maximum number of custom emojis in a message.  Default is 5.
        self.ANTISPAM_EMOJIS_MAX_CUSTOM_EMOJI_COUNT = 5
        # API key for the OpenAI-backed filter (the openai layer).  Mandatory for that layer if it is enabled.
        self.ANTISPAM_OPENAI_API_KEY = ""
        # Confidence threshold for the OpenAI model.  Default is 0.5.
        self.ANTISPAM_OPENAI_CONFIDENCE_THRESHOLD = 0.5

        # --------------------------------------------------------------------------------------------------------------
        # Glossary
        #
        # The bot can react to messages that contain certain words that may be natural for the community but not easy to
        # understand for newcomers.  Such "local language" often contains lots of loan words which are not properly
        # assimilated into the native language of the community, which creates additional confusion.  This feature helps
        # in such situations.
        #
        # The glossary contains a set of trigger words which are sought for in every message sent to the main chat.
        # If a trigger word is found, the bot can react one or more way, as configured below.

        # Whether glossary is enabled.  Default is false.
        self.GLOSSARY_ENABLED = False
        # Whether the bot should send a reply to every message that contains triggers.  Default is false.
        self.GLOSSARY_REPLY_TO_TRIGGER = False
        # Minimum number of triggers in a message that the bot will reply to.  Default is 3.
        self.GLOSSARY_REPLY_TO_MIN_TRIGGER_COUNT = 3
        # Delay in seconds for deleting a reply sent if GLOSSARY_REPLY_TO_TRIGGER is True, 0 for not deleting it.
        # Default is 30.
        self.GLOSSARY_REPLY_TO_TRIGGER_TIMEOUT = 30
        # Whether the bot should react with an emoji to every message that contains a trigger.  Default is false.
        self.GLOSSARY_REACT_TO_TRIGGER = False
        # Maximum age in seconds of a trigger to explain.  Default is 300.
        self.GLOSSARY_MAX_TRIGGER_AGE = 300
        # Optional URL of an external web page that has more information on the glossary.  Default is empty string.
        self.GLOSSARY_EXTERNAL_URL = ""

        # --------------------------------------------------------------------------------------------------------------
        # Public moderation (experimental, work in progress)
        #
        # The bot can coordinate public-driven moderation in the chat.  The additional chat of moderators is configured.
        # Users of the main chat may send requests to moderate messages to the bot, these requests are redirected to the
        # moderation chat, and the bot helps with reaching consensus and doing the actual moderation in the main chat.
        #
        # Settings marked with asterisks should be tuned or at least revised to be adequate to the size of the group.

        # Whether moderation is enabled.  See also MODERATION_IS_REAL.  Default is false.
        self.MODERATION_ENABLED = False
        # ID of the moderators' chat.  Mandatory if the feature is enabled.  Default is 0.
        self.MODERATION_CHAT_ID = 0
        # Number of bots in the moderator's chat.  Makes sense for calculating the thresholds for voting.  Default is 1.
        self.MODERATION_CHAT_BOT_COUNT = 1
        # * Number of complaints required for a message to start the moderation poll.  Default is 5.
        self.MODERATION_COMPLAINT_THRESHOLD = 5
        # Minimum number of moderators that should vote to start evaluating the result.  Defined as a fraction of the
        # total number of people in the moderators' chat.  Default is 0.75.
        self.MODERATION_QUORUM_THRESHOLD = 0.75
        # Minimum number of votes that is enough to be given for an option to have that option accepted after the
        # quorum is reached.  Default is 0.75.
        self.MODERATION_WINNING_THRESHOLD = 0.75
        # Whether the bot should work in earnest and punish participants when complaints are approved.  When this is
        # False, the bot will only announce in the moderation chat what it would do, and also it will reset the
        # moderation persistent state (complaints, polls and restrictions) upon restart.  Default is false.
        self.MODERATION_IS_REAL = False
        # Ladder of restrictions.  Defines how a participant would progress if they keep violating rules of the chat and
        # do not let their most recent restriction to cool down (see README for the detailed explanation).
        self.MODERATION_RESTRICTION_LADDER = [{"action": "warn", "cooldown": 60},
                                              {"action": "restrict", "duration": 60, "cooldown": 60},
                                              {"action": "restrict", "duration": 1800, "cooldown": 1800},
                                              {"action": "ban"}]

        # YAML_SETTINGS

        # Working mode.
        self.SERVICE_MODE = os.getenv("DIASPORA_SERVICE_MODE") == "1"

        # Ensure that directories exist.
        for p in (self.conf_dir, self.data_dir):
            p.mkdir(parents=True, exist_ok=True)

        # Try to load settings.
        config_path = self.conf_dir / "settings.yaml"
        if not config_path.is_file():
            logging.warning(f"{config_path} does not exist (yet?), cannot load settings.")
            return

        logging.info(f"Loading settings from {config_path}")
        _user_settings = yaml.safe_load(open(config_path))

        for k, v in _user_settings.items():
            if hasattr(self, k):
                setattr(self, k, v)
            else:
                logging.warning(f"Unknown setting \"{k}\"")

        # TODO: Move this out of settings to some better place?
        self._start_timestamp = datetime.datetime.now().replace(microsecond=0)

    @property
    def data_dir(self) -> pathlib.Path:
        if self.SERVICE_MODE:
            return pathlib.Path("/var") / "local" / "diaspora"
        return pathlib.Path(__file__).parent.parent / "data"

    @property
    def conf_dir(self) -> pathlib.Path:
        if self.SERVICE_MODE:
            return pathlib.Path("/usr") / "local" / "etc" / "diaspora"
        return pathlib.Path(__file__).parent.parent / "conf"

    @property
    def start_timestamp(self) -> datetime.datetime:
        return self._start_timestamp

    @property
    def uptime(self) -> datetime.timedelta:
        return datetime.datetime.now().replace(microsecond=0) - self._start_timestamp


settings = Settings()


def update_settings_yaml(bot_token) -> None:
    """Renders a new settings.yaml, preserving the existing settings and adding new ones"""

    target_yaml_path = settings.conf_dir / _SETTINGS_FILENAME
    existing_user_settings = yaml.safe_load(open(target_yaml_path)) if target_yaml_path.is_file() else dict()
    assert bot_token != "" or (settings.BOT_TOKEN != "" and settings.BOT_TOKEN != INVALID_BOT_TOKEN)

    new_path = target_yaml_path.with_suffix(".yaml.new")

    with open(__file__, "r") as inp:
        yaml_settings = inp.read().split("# YAML_SETTINGS\n")[1].replace(INVALID_BOT_TOKEN,
                                                                         bot_token.replace("\"", "\\\""))

        with open(new_path, "w") as new_settings:
            new_settings.write("%YAML 1.2\n"
                               "---\n"
                               "# Configuration for the Diaspora Telegram bot\n"
                               "\n")

            lines = []

            current_name = ""
            current_value = ""

            def commit():
                nonlocal current_name, current_value, existing_user_settings, lines

                if not current_name and not current_value:
                    return

                assert current_name and current_value

                overridden = current_name in existing_user_settings.keys()
                mandatory = current_name in ("BOT_TOKEN", "DEVELOPER_CHAT_ID", "MAIN_CHAT_ID")
                for l in yaml.dump({current_name: existing_user_settings[current_name] if overridden else eval(
                        current_value)}).splitlines():
                    if overridden or mandatory:
                        lines.append(l)
                    else:
                        lines.append("# " + l)
                current_name = ""
                current_value = ""

            for line in yaml_settings.splitlines():
                line = line.strip()
                if line.startswith("#") or len(line) == 0:
                    commit()
                    lines.append(line)
                    continue
                if line.startswith("self."):
                    commit()
                    line = line[len("self."):]
                    current_name, current_value = [p.strip() for p in line.split("=")]
                else:
                    current_value += line

            new_settings.write("\n".join(lines))

    try:
        backup_path = target_yaml_path.with_suffix(".yaml.backup")
        backup_backup_path = ""

        if os.path.exists(target_yaml_path):
            if os.path.exists(backup_path):
                backup_backup_path = backup_path.with_suffix(".yaml.backup.backup")
                shutil.move(backup_path, backup_backup_path)

            shutil.move(target_yaml_path, backup_path)

        shutil.move(new_path, target_yaml_path)

        if backup_backup_path and os.path.exists(backup_backup_path):
            os.remove(backup_backup_path)
    except OSError as e:
        logging.error(e)


import os.path
import sqlite3


def main() -> None:
    if os.path.exists("secret.py") or os.path.exists("people.db"):
        print("ERROR: local files already exist!  Please remove secret.py and people.db before running this script.")
        return

    # Create secret.py
    bot_token = input("Please enter your bot's token: ")

    with open(__file__, "r") as this_file:
        secret_lines = this_file.read()
        secret_lines = secret_lines.split("# %TEMPLATE%\n")[-1].format(bot_token=bot_token.replace("\"", "\\\""))
        with open("secret.py", "w") as secret:
            secret.write(secret_lines)
    print("- Created secret.py: bot configuration")

    # Create people.db
    conn = sqlite3.connect("people.db")
    c = conn.cursor()

    c.execute("CREATE TABLE \"people\" ("
              "\"tg_id\" INTEGER,"
              "\"tg_username\" TEXT,"
              "\"occupation\" TEXT,"
              "\"location\" TEXT,"
              "\"last_modified\" DATETIME DEFAULT CURRENT_TIMESTAMP,"
              "\"is_suspended\" INTEGER DEFAULT 0,"
              "PRIMARY KEY(\"tg_id\"))")
    c.execute("CREATE TABLE \"new_members\" ("
              "\"tg_id\" INTEGER,"
              "PRIMARY KEY(\"tg_id\"))")

    conn.commit()
    conn.close()

    print("- Created people.db: the empty database")

    print("The minimal setup is complete.  Refer to README.md for more information.")

if __name__ == "__main__":
    main()

# Below is the template for the secret.py.
# %TEMPLATE%
# ----------------------------------------------------------------------------------------------------------------------
# Mandatory settings
#
# Token of the bot, obtained from BotFather
BOT_TOKEN = "{bot_token}"
# ID of the chat with the developer
DEVELOPER_CHAT_ID = 0
# ID of the main chat where the bot should have administrator privileges
MAIN_CHAT_ID = 0

# ----------------------------------------------------------------------------------------------------------------------
# Internationalisation
#
# The official documentation suggests that bots should switch to the user's language or fall back to English.  This is
# not completely adequate for this bot that is designed for groups of nationals; the default English may be not optimal.
# The settings below define the "standard" behaviour suggested by the documentation, but may be overridden in secret.py.
#
# Whether the bot should try to switch to the user's language.  Default is True.
# SPEAK_USER_LANGUAGE = True
#
# Language to fall back to if there is no translation to the user's language. Default is "en".
# DEFAULT_LANGUAGE = "en"
#
# Supported languages.  Must be a subset of languages that present in the `locales` directory.  Default is tuple that
# contains all available languages.
# SUPPORTED_LANGUAGES = ('en', 'ru')

# ----------------------------------------------------------------------------------------------------------------------
# Bot personality
#
# Bot name may imply its "gender" that affects "personal" messages (like "I am the host" vs. "I am the hostess").  This
# setting tells which one to pick.  Default is False.
# BOT_IS_MALE = False

# ----------------------------------------------------------------------------------------------------------------------
# Greeting new users
#
# The bot can reply to each service message about a new user joining the group.  These bot replies can be deleted by the
# bot after the specified delay.
#
# Whether to greet users that join the group.  Default is True.
# GREETING_ENABLED = True
#
# Delay in seconds for deleting the greeting, 0 for not deleting the greetings.  Default is 300.
# GREETING_TIMEOUT = 300

# ----------------------------------------------------------------------------------------------------------------------
# Moderation
#
# The bot may ask the moderators to approve changes made by users to their data records.
#
# Whether moderation is enabled.  Default is True.
# MODERATION_ENABLED = True
#
# Whether moderation is "lazy" (True, default) or "mandatory" (False).
# "Lazy" moderation (also known as post-moderation) means that all changes are initially visible, but moderators may
# decide later to decline them.  "Mandatory" moderation means that the data is initially hidden, and becomes visible
# only after the explicit approval of a moderator.
# Moderators' votes work symmetrically: with "lazy" moderation one "decline" vote is enough to hide the data, and in
# "mandatory" mode one "approve" vote is enough to make it visible.
# MODERATION_IS_LAZY = True
#
# Telegram IDs of moderators, each of them will receive requests to approve changes.
# - If it is empty (default), the only moderator is the developer.
# - If it is not empty, only those users are moderators.  Each moderator must be a member of the main chat.
# MODERATOR_IDS = tuple()

# ----------------------------------------------------------------------------------------------------------------------
# Language moderation
#
# The bot may ask people in the main chat to speak the default language.  If the bot detects too many messages written
# in languages other than the default one, it posts a message that reminds the people about rules of the group.
#
# Whether bot controls languages.  Default is False.
# LANGUAGE_MODERATION_ENABLED = False
#
# Maximum number of languages in non-default language.  Default is 3.
# LANGUAGE_MODERATION_MAX_FOREIGN_MESSAGE_COUNT = 3
#
# Minimum number of words in a message that the bot should evaluate when detecting the language.  Language detection may
# fail for short messages.  Default is 3.
# LANGUAGE_MODERATION_MIN_WORD_COUNT = 3

# ----------------------------------------------------------------------------------------------------------------------
# Antispam
#
# The bot may detect and delete spam messages.  Spammers in Telegram are normally regular users that join the group, sit
# silent for some time, and then send their junk, hoping that someone will see and buy it before the moderators react.
# Telegram blocks user accounts that have been reported as spammers, which makes it not worth it trying to mimic the
# good user before sending spam.  Therefore, to eliminate most spam, it should be enough to evaluate the first message
# sent by a new user to the group.
#
# Whether the feature is enabled.  Default is False.
# ANTISPAM_ENABLED = False
# Whether to use simple filter that triggers on a single word.  Default is False.
# ANTISPAM_STOP_WORDS_ENABLED = False
# Whether to use OpenAI-backed filter.  Default is False.
# ANTISPAM_OPENAI_ENABLED = False
# API key for the OpenAI API
# ANTISPAM_OPENAI_API_KEY = ""

# ----------------------------------------------------------------------------------------------------------------------
# General settings
#
# Generic delay in seconds for self-destructing messages.  Default is 60.
# DELETE_MESSAGE_TIMEOUT = 60

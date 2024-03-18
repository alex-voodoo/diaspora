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
# Language to fall back to if there is no translation to the user's language. Default is "en".
# DEFAULT_LANGUAGE = "en"
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
# fot after the specified delay.
#
# Whether to greet users that join the group.  Default is True.
# GREETING_ENABLED = True
# Delay in seconds for deleting the greeting, 0 for not deleting the greetings.  Default is 300.
# GREETING_TIMEOUT = 300

# ----------------------------------------------------------------------------------------------------------------------
# Moderation
#
# The bot may ask the moderators to approve changes made by users to their data records.  This setting tells whether
# moderation is enabled.  Default is True.
# MODERATION_ENABLED = True

# Generic delay in seconds for self-destructing messages.  Default is 60.
# DELETE_MESSAGE_TIMEOUT = 60

# Diaspora: User Directory Bot

This is a Telegram bot for communities of expats and emigrants.  Such communities typically have specific needs such as services in their native language, certain goods that are not typical for the place, etc.

The bot runs in a chat, and maintains a database of users of the chat who could address these specific needs of the community by providing these special services.  This database is populated by these chat members, and is then available to all users of the chat.

For example, some chat member might be a hairdresser that speaks the language of the chat.  Another person knows a lot about how the immigration office works in this city, and can help with advice.  They talk to the bot and say what they do and where they are located.  Others may then ask the bot about services available in the location, and they will see users who registered their services.

## Setup

Clone this repository, create a virtual Python environment with Python version 3.12, and install there `requirements.txt`.  (Older versions may work too but this is not tested.)

Now you need to configure the bot.  Follow these steps to complete this process:
1. Follow the [official documentation](https://core.telegram.org/bots#how-do-i-create-a-bot) to register your bot with BotFather and obtain its token.
2. Run `python setup.py` and provide your token when requested.  The script will render `secret.py` that is necessary for the bot to run.
3. Run `python bot.py` in the terminal.  Find your bot in Telegram and talk to it in private.  Initiate the conversation, the bot will welcome you and show the buttons for its functions.  In the terminal you will see a log message: `"INFO Welcoming user {username} (chat ID {id})"`.  Stop the bot by pressing `Ctrl+C` in the terminal.  Copy the chat ID, open `secret.py` and paste that number as the new value of the `DEVELOPER_CHAT_ID` parameter.  Should any error occur in the bot, it will send error messages to you.

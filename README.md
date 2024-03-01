# Diaspora: User Directory Bot

This is a Telegram bot for communities of expats and emigrants.  Such communities typically have specific needs such as services in their native language, certain goods that are not typical for the place, etc.

The bot runs in a Telegram group (aka chat) and maintains a database of users of that chat who could address these specific needs of the community by providing these special services.  The database is populated with data provided by these chat members, and is then available to all users of the chat.

For example, some chat member might be a hairdresser that speaks the language of the chat.  Another person knows a lot about how the immigration office works in this city, and can help with advice.  They can talk to the bot and declare what they do and where they are located.  Others can then ask the bot about services available in the location, and they will see users who registered their services.

## Setup and usage

Clone this repository.  Create a virtual Python environment with Python version 3.12.  (Older versions may work too but that is not tested.) Install `requirements.txt` in the virtual environment.

Follow the [official documentation](https://core.telegram.org/bots#how-do-i-create-a-bot) to register your bot with BotFather and obtain its token.

Now you need to configure your instance of the bot.  Follow these steps to complete this process:
1. Open the command terminal and activate the virtual environment that you created above
2. Run `python setup.py` and provide your token when requested.  The script will render `secret.py` that is necessary for the bot to run.
3. Run `python bot.py`.  Find your bot in Telegram and talk to it in private.  Initiate the conversation by clicking the Start button in the chat.  The bot will welcome you and show the buttons for its functions.  In the terminal you will see a log message: `"INFO Welcoming user {username} (chat ID {id})"`.  Stop the bot by pressing `Ctrl+C` in the terminal.  Copy the chat ID, open `secret.py` and paste that number as the new value of the `DEVELOPER_CHAT_ID` parameter.

Finally, complete the setup from the Telegram side.

1. Add the bot to the Telegram group that you want it to serve
2. Grant the bot the administrator privilege (this is needed to allow the bot deleting its own messages)
3. Disallow chats in the bot settings via BotFather to prevent random people from finding your bot and adding it to their chats

Now you can start the bot by running `python bot.py` or adding it to some system auto-run.  The script will run indefinitely, unless something severe causes it to crash.  Should any error occur in the bot, it will send error messages to you.

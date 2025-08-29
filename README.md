# Diaspora: User Directory Bot

This is a Telegram bot for communities of expats and emigrants.  Such communities typically have specific needs such as services in their native language, certain goods that are not common in that place, etc.

The bot runs in a Telegram group (aka chat) and maintains a database of users of that chat who could address needs of the community by providing these special services.  The database is populated with data provided by these chat members, and is then available to all users of the chat.

For example, some chat member might be a hairdresser that speaks the language of the chat.  Another person knows a lot about how the immigration office works in this city, and can help with advice.  They can talk to the bot and declare what they do and where they are located.  Others can then ask the bot about services available in the location, and they will see users who registered their services.

The bot deletes most of its own messages some time after posting them, to keep the chat clean of automatic replies.  Users are supposed to talk to bot using private messages.  The bot does not respond to Telegram users who are not members of the chat.

## Features

The bot has a number of additional features, most of them are off by default, and can be enabled independently of each other.  

A couple of features are very simple: 

- Greeting new users.  The bot reacts when a new user joins the group by sending a greeting message to the group.
- Language moderation.  The bot detects language of messages posted by the users, and post a warning about preferred (or required) language if too many messages were sent in other languages.

See <a href="features/README.md">README</a> in the `features` module for detailed information on other features.

## Setup and usage

Clone this repository.  Create a virtual Python environment with Python version 3.12.  (Older versions may work too but that is not tested.) Install `requirements.txt` in the virtual environment.

Follow the [official documentation](https://core.telegram.org/bots#how-do-i-create-a-bot) to register your bot with BotFather.

Now you need to configure your instance of the bot.  Follow these steps to complete this process:
1. Open the command terminal and activate the virtual environment that you created above
2. Run `python setup.py` and provide the API token of your bot when requested.  The script will render `settings.py` that is necessary for the bot to run.
3. Run `python bot.py`.  The command should start the bot and run indefinitely.  Find your bot in Telegram and talk to it in private.  Initiate the conversation by clicking the Start button in the direct message chat.  The bot will welcome you and show the buttons for its functions.  Stop the bot by pressing `Ctrl+C` in the terminal.
4. In the directory where you have your bot, find `bot.log`, open it, and find a log message: `"Welcoming user {username} (chat ID {chat_id}), is this the admin?"` where `username` should be your Telegram username.  Copy the chat ID, open `settings.py` and paste that number as the new value of the `DEVELOPER_CHAT_ID` parameter.

Finally, complete the setup from the Telegram side.

1. Add the bot to the Telegram group that you want it to serve (aka "main chat")
2. In the main chat, grant the bot the administrator privilege to allow the bot to 1) check that the user is eligible for using it, and 2) delete certain messages in the main chat
3. In the BotFather settings, disallow chats for your bots to prevent random people from finding your bot and adding it to their groups, and disable the inline mode.
4. Run `python bot.py` again.  In the main chat, issue the `/start` command of your bot, like this: `/start@YourGroupBot`, where `YourGroupBot` is the username of the bot that you registered earlier with BotFather.  The bot will send you the ID of the main chat in a private message.  Note that IDs of Telegram groups can be negative.  Copy that ID and paste it as the new value of the `MAIN_CHAT_ID` parameter in the `settings.py` file.  Stop the bot by pressing `Ctrl+C` in the terminal.

Now the bot is ready to work.  You can start it by running `python bot.py` in a command terminal or adding it to some system auto-run.  The script will run indefinitely, unless something severe causes it to crash.  Should any non-fatal error occur in the bot, it will send error messages to you via private Telegram message.

## Configuration

To tune your bot, read and edit `settings.py`.  Uncomment settings that you want to alter and put your values.

Do not forget to restart the bot after you have changed the settings!

## Updating

To get the newest version of the bot, stop it, update your working copy by running `git pull`, then update Python packages by running `pip install -r requirements.txt`, and update the DB schema by running `python migrate.py`.

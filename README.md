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

## Installation step-by-step

Clone this repository.  Create a virtual Python environment with Python version 3.12.  (Older versions may work too but that is not tested.) Install `requirements.txt` in the virtual environment.

Follow the [official documentation](https://core.telegram.org/bots#how-do-i-create-a-bot) to register your bot with BotFather.

Now you need to configure your instance of the bot.  Follow these steps to complete this process:
1. Open the command terminal and activate the virtual environment that you created above
2. ~~Run `python src/setup.py` and provide the API token of your bot when requested.  The script will render `settings.py` that is necessary for the bot to run.~~  This is currently broken.  You will have to write `settings.yaml` manually.
3. Run `python src/bot.py`.  The command should start the bot and run indefinitely.  Find your bot in Telegram and talk to it in private.  Initiate the conversation by clicking the Start button in the direct message chat.  The bot will welcome you and show the buttons for its functions.  Stop the bot by pressing `Ctrl+C` in the terminal.
4. In the directory where you have your bot, find `bot.log`, open it, and find a log message: `"Welcoming user {username} (chat ID {chat_id}), is this the admin?"` where `username` should be your Telegram username.  Copy the chat ID, open `settings.py` and paste that number as the new value of the `DEVELOPER_CHAT_ID` parameter.

Finally, complete the setup from the Telegram side.

1. Add the bot to the Telegram group that you want it to serve (aka "main chat")
2. In the main chat, grant the bot the administrator privilege to allow the bot to 1) check that the user is eligible for using it, and 2) delete certain messages in the main chat
3. In the BotFather settings, disallow chats for your bots to prevent random people from finding your bot and adding it to their groups, and disable the inline mode.
4. Run `python bot.py` again.  In the main chat, issue the `/start` command of your bot, like this: `/start@YourGroupBot`, where `YourGroupBot` is the username of the bot that you registered earlier with BotFather.  The bot will send you the ID of the main chat in a private message.  Note that IDs of Telegram groups can be negative.  Copy that ID and paste it as the new value of the `MAIN_CHAT_ID` parameter in the `settings.py` file.  Stop the bot by pressing `Ctrl+C` in the terminal.

Now the bot is ready to work.  You can start it by running `python bot.py` in a command terminal or adding it to some system auto-run.  The script will run indefinitely, unless something severe causes it to crash.  Should any non-fatal error occur in the bot, it will send error messages to you via private Telegram message.

Now the bot is ready to work.  It can be launched directly by running `python src/bot.py` in a command terminal, or it can be installed as a Linux system service.  The recommended way is first testing the bot in direct mode, tuning the configuration, and then installing it as the system service.  To change the configuration, edit `settings.py` (the exact location depends on the mode), then restart the bot.

## Running the bot in direct mode

The bot runs in direct mode if the `DIASPORA_SERVICE_MODE` environment variable is not set or not equal to "1".

To launch the bot, activate the Python virtual environment and run `python src/bot.py` in a command terminal.  To stop it gracefully, press `Ctrl+C`.

## Running the bot as a Linux system service

The bot can be registered as a Linux service daemon in a system that runs systemd.  The bot runs in service mode if the `DIASPORA_SERVICE_MODE` environment variable is set and is equal to "1", which is provided by the systemd unit configuration.

You will need superuser privileges to proceed.

First configure the bot as explained above, then continue from here.

Run `sudo make install` to install the systemd unit.  The script will copy the bot program files to `/usr/local/lib/diaspora`, create the virtual Python environment there, and register the systemd unit named `diaspora`.

Start the service by running `sudo sustemctl start diaspora`, stop it by running `sudo sustemctl stop diaspora`.

## Troubleshooting and error handling

The bot writes log messages to `stdout` and `stderr`.  In service mode these are redirected to `/var/log/diaspora.log`.

Should any non-fatal errors occur in the bot, it will send error messages to its administrator user via private Telegram messages.

## Configuration

To tune your bot, read and edit `settings.yaml` located near the entry point script.  Uncomment settings that you want to alter and put your values.

Do not forget to restart the bot after you have changed the settings!

## Updating

To get the newest version of the bot, stop it, update your working copy by running `git pull`, then update Python packages by running `pip install -r requirements.txt`.

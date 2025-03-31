"""
April's fool
"""

import datetime
import pathlib
import random

from telegram import Update
from telegram.ext import Application, CommandHandler, ContextTypes

import settings

URLS_FILENAME = "aprils_fool_urls.txt"
URLS_FILE_PATH = pathlib.Path(__file__).parent / "resources" / URLS_FILENAME

COMMAND_ASTANAVITES = "astanavites"

EMOJI_REPLIES = ("✋", "🛑", "🙅‍♀️", "️⛔", "❌", "🚧")
urls = None
latest_url_timestamp = None
MIN_URL_DELAY = 5
URL_CHANCE = 50


async def handle_command_astanavites(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle the April's fool command"""

    global urls
    global latest_url_timestamp

    if urls is None:
        urls = []
        with open(URLS_FILE_PATH) as f:
            for line in f.readlines():
                urls.append(line.strip())

    if datetime.datetime.now().month != 4 or datetime.datetime.now().day != 1:
        return

    if random.randint(0, 100) < URL_CHANCE and (
            latest_url_timestamp is None or datetime.datetime.now() - datetime.timedelta(
            minutes=MIN_URL_DELAY) > latest_url_timestamp):
        latest_url_timestamp = datetime.datetime.now()
        await context.bot.send_message(chat_id=settings.MAIN_CHAT_ID, text=random.sample(urls, 1)[0])
    else:
        await context.bot.send_message(chat_id=settings.MAIN_CHAT_ID, text=random.sample(EMOJI_REPLIES, 1)[0])


def init(application: Application, group):
    application.add_handler(CommandHandler(COMMAND_ASTANAVITES, handle_command_astanavites))

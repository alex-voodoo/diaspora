"""
This is the main script that contains the entry point of the bot.  Execute this file to run the bot.

See README.md for details.
"""

import io
import json
import logging
import traceback
import uuid
from collections import deque

import httpx
import telegram
from langdetect import detect, lang_detect_exception
from telegram import BotCommand, LinkPreviewOptions, MenuButtonCommands, Update
from telegram.constants import ParseMode, ChatType
from telegram.ext import Application, CommandHandler, ContextTypes, Defaults, filters, MessageHandler

# Configure logging before importing settings and other project modules to have messages that may be rendered during
# initialisation logged correctly.
# Set higher logging level for httpx to avoid all GET and POST requests being logged.
# noinspection SpellCheckingInspection
logging.basicConfig(format="[%(asctime)s %(levelname)s %(name)s %(filename)s:%(lineno)d] %(message)s",
                    level=logging.INFO)
logging.getLogger("httpx").setLevel(logging.WARNING)

from common import db, i18n
from common.admin import get_main_keyboard
from common.checks import is_admin, is_member_of_main_chat
from common.messaging_helpers import safe_delete_message, self_destructing_reply
from common.settings import settings
from features import antispam, aprils_fool, glossary, moderation, services

# Commands, sequences, and responses
COMMAND_START, COMMAND_HELP, COMMAND_ADMIN = ("start", "help", "admin")

message_languages: deque


async def talking_private(update: Update, context: ContextTypes.DEFAULT_TYPE) -> bool:
    """Helper for handlers that require private conversation

    Most features of the bot should not be accessed from the main chat, instead users should talk to the bot directly
    via private conversation.  This function checks if the update came from the private conversation, and if that is not
    the case, sends a self-destructing reply that suggests talking private.  The caller can simply return if this
    returned false.
    """

    if not update.effective_chat or update.effective_chat.type != ChatType.PRIVATE:
        await self_destructing_reply(update, context, i18n.trans(update.effective_message.from_user).gettext(
            "MESSAGE_MC_LET_US_TALK_PRIVATE"), settings.DELETE_MESSAGE_TIMEOUT)
        return False
    return True


async def greet_new_member(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Show the welcome message to the user that has just joined the main chat"""

    for user in update.message.new_chat_members:
        if user.is_bot:
            continue

        logging.info("Greeting new user {username} (chat ID {chat_id})".format(username=user.username, chat_id=user.id))

        greeting_message = i18n.trans(user).gettext(
            "MESSAGE_MC_GREETING_M {user_first_name} {bot_first_name}") if settings.BOT_IS_MALE else i18n.trans(
            user).gettext("MESSAGE_MC_GREETING_F {user_first_name} {bot_first_name}")

        await self_destructing_reply(update, context, greeting_message.format(user_first_name=user.first_name,
                                                                              bot_first_name=context.bot.first_name),
                                     settings.GREETING_TIMEOUT, False)


async def detect_language(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Detect language of the incoming message in the main chat, and show a warning if there are too many messages
    written in non-default languages."""

    if (update.effective_message.chat_id != settings.MAIN_CHAT_ID or not hasattr(update.message, "text") or len(
            update.message.text.split(" ")) < settings.LANGUAGE_MODERATION_MIN_WORD_COUNT):
        return

    global message_languages

    try:
        message_languages.append(detect(update.message.text))
    except lang_detect_exception.LangDetectException:
        logging.warning("Caught LangDetectException while processing a message")
        return

    if len(message_languages) < settings.LANGUAGE_MODERATION_MAX_FOREIGN_MESSAGE_COUNT:
        return

    while len(message_languages) > settings.LANGUAGE_MODERATION_MAX_FOREIGN_MESSAGE_COUNT:
        message_languages.popleft()

    if settings.DEFAULT_LANGUAGE not in message_languages:
        message_languages = deque()
        await context.bot.send_message(chat_id=settings.MAIN_CHAT_ID,
                                       text=i18n.default().gettext("MESSAGE_MC_SPEAK_DEFAULT_LANGUAGE"))


async def handle_command_help(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Show the help message"""

    message = update.effective_message
    user = message.from_user

    trans = i18n.trans(user)

    if message.chat_id != user.id:
        await self_destructing_reply(update, context, trans.gettext("MESSAGE_MC_HELP"), settings.DELETE_MESSAGE_TIMEOUT)
        return

    if not await is_member_of_main_chat(user, context):
        return

    await message.reply_text(trans.gettext("MESSAGE_DM_HELP"), reply_markup=services.get_standard_keyboard(user))


async def handle_command_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Welcome the user and show them the selection of options"""

    message = update.effective_message
    user = message.from_user

    if user.id == settings.DEVELOPER_CHAT_ID and message.chat.id != settings.DEVELOPER_CHAT_ID:
        logging.info("This is the admin user {username} talking from \"{chat_name}\" (chat ID {chat_id})".format(
            username=user.username, chat_name=message.chat.title, chat_id=message.chat.id))

        await safe_delete_message(context, message.id, message.chat.id)
        await context.bot.send_message(chat_id=settings.DEVELOPER_CHAT_ID,
                                       text=i18n.trans(user).gettext("MESSAGE_ADMIN_MAIN_CHAT_ID {title} {id}").format(
                                           title=message.chat.title, id=str(message.chat.id)))
        return

    if not await talking_private(update, context):
        return

    if settings.MAIN_CHAT_ID == 0:
        logging.info("Welcoming user {username} (chat ID {chat_id}), is this the admin?".format(username=user.username,
                                                                                                chat_id=user.id))
        return

    if not await is_member_of_main_chat(user, context):
        return

    await services.show_main_status(context, message, user)


async def handle_command_admin(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Show the admin menu"""

    message = update.effective_message
    user = message.from_user

    if not is_admin(user):
        logging.info("User {username} tried to invoke the admin UI".format(username=user.username))
        return

    if not await talking_private(update, context):
        await safe_delete_message(context, message.id, message.chat.id)

    await context.bot.send_message(chat_id=user.id,
                                   text=i18n.trans(user).gettext("MESSAGE_DM_ADMIN {since} {uptime}").format(
                                       since=settings.start_timestamp, uptime=settings.uptime),
                                   reply_markup=get_main_keyboard())


async def handle_error(update: object, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Log the error and send a Telegram message to notify the developer"""

    exception = context.error

    if isinstance(exception, telegram.error.BadRequest):
        logging.error(f"An exception of type {type(exception)} was raised: {exception}.")
        return
    if isinstance(exception, httpx.RemoteProtocolError) or isinstance(exception, telegram.error.NetworkError):
        # Connection errors happen regularly, and they are caused by reasons external to the bot, so it makes no
        # sense notifying the developer about them.  Log an error and bail out.
        logging.error(f"An exception of type {type(exception)} was raised.")
        return

    trans = i18n.default()

    error_uuid = uuid.uuid4()

    # Log the error before we do anything else, so we can see it even if something breaks.
    logging.error(f"Exception of type {type(exception)} (error UUID {error_uuid}):", exc_info=exception)

    update_str = update.to_dict() if isinstance(update, Update) else str(update)

    error_message = trans.gettext("ERROR_REPORT_BODY {error_uuid} {traceback} {update} {chat_data} {user_data}").format(
        chat_data=str(context.chat_data), error_uuid=error_uuid,
        traceback="".join(traceback.format_exception(None, exception, exception.__traceback__)),
        update=json.dumps(update_str, indent=2, ensure_ascii=False), user_data=str(context.user_data))

    # Notify the developer.
    await context.bot.send_document(chat_id=settings.DEVELOPER_CHAT_ID,
                                    caption=trans.gettext("ERROR_REPORT_CAPTION {error_uuid}").format(
                                        error_uuid=error_uuid), document=io.BytesIO(bytes(error_message, "utf-8")),
                                    filename=f"diaspora-error-{error_uuid}.txt")

    # Optionally, respond to the user whose message caused the error, if that message was sent in private (do not
    # make noise in the group).
    if not isinstance(update, Update) or not update.effective_message or not await talking_private(update, context):
        return

    await update.effective_message.reply_text(
        i18n.trans(update.effective_message.from_user).gettext("MESSAGE_DM_INTERNAL_ERROR {error_uuid}").format(
            error_uuid=error_uuid))


async def post_init(application: Application) -> None:
    bot = application.bot

    trans = i18n.default()

    await bot.set_my_commands(
        [BotCommand(command=COMMAND_START, description=trans.gettext("COMMAND_DESCRIPTION_START")),
         BotCommand(command=COMMAND_ADMIN, description=trans.gettext("COMMAND_DESCRIPTION_ADMIN"))])

    for administrator in settings.ADMINISTRATORS:
        await bot.set_chat_menu_button(administrator["id"], MenuButtonCommands())

    antispam.post_init(application, group=1)
    glossary.post_init(application, group=4)

    if settings.DEVELOPER_CHAT_ID:
        await bot.send_message(chat_id=settings.DEVELOPER_CHAT_ID,
                               text=i18n.default().gettext("MESSAGE_ADMIN_HELLO_ON_STARTUP"))


def main() -> None:
    """Run the bot"""

    logging.info("The bot starts in {m} mode".format(m="service" if settings.SERVICE_MODE else "direct"))

    db.connect()

    application = (Application.builder()
                   .token(settings.BOT_TOKEN)
                   .defaults(Defaults(link_preview_options=LinkPreviewOptions(is_disabled=True),
                                      parse_mode=ParseMode.HTML))
                   .post_init(post_init)
                   .build())

    # ------------------------------------------------------------------------------------------------------------------
    # The services feature has stateful conversation handlers, and they should go first, to act correctly if the user
    # does something unexpected during the conversation.

    services.init(application, group=0)

    application.add_handler(CommandHandler(COMMAND_START, handle_command_start))
    application.add_handler(CommandHandler(COMMAND_HELP, handle_command_help))
    application.add_handler(CommandHandler(COMMAND_ADMIN, handle_command_admin))

    if settings.GREETING_ENABLED:
        application.add_handler(MessageHandler(filters.StatusUpdate.NEW_CHAT_MEMBERS, greet_new_member))

    if settings.LANGUAGE_MODERATION_ENABLED:
        global message_languages
        message_languages = deque()

        application.add_handler(MessageHandler(filters.TEXT & (~ filters.COMMAND), detect_language), group=3)

    antispam.init(application, group=1)
    glossary.init(application, group=4)
    aprils_fool.init(application, group=5)
    moderation.init(application, group=6)

    application.add_error_handler(handle_error)

    # Run the bot until the user presses Ctrl-C
    application.run_polling(allowed_updates=Update.ALL_TYPES)

    db.disconnect()


if __name__ == "__main__":
    main()

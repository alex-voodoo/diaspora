"""
Moderation
"""

import gettext
import logging
import re
from math import ceil

# noinspection PyPackageRequirements
from telegram import Update, InlineKeyboardMarkup, InlineKeyboardButton, Poll, User
# noinspection PyPackageRequirements
from telegram.constants import ChatType
# noinspection PyPackageRequirements
from telegram.ext import Application, CallbackQueryHandler, ContextTypes, filters, MessageHandler, PollHandler

from common import i18n
from common.checks import is_member_of_main_chat
from common.settings import settings
from . import state

(_MODERATION_REASON_FRAUD, _MODERATION_REASON_OFFENSE, _MODERATION_REASON_RACISM, _MODERATION_REASON_SPAM,
 _MODERATION_REASON_TOXIC) = range(5)


def _reason_to_explanation(reason: int, trans: gettext.GNUTranslations) -> str:
    if reason == _MODERATION_REASON_FRAUD:
        return trans.gettext("MODERATION_REASON_FRAUD")
    if reason == _MODERATION_REASON_OFFENSE:
        return trans.gettext("MODERATION_REASON_OFFENSE")
    if reason == _MODERATION_REASON_RACISM:
        return trans.gettext("MODERATION_REASON_RACISM")
    if reason == _MODERATION_REASON_SPAM:
        return trans.gettext("MODERATION_REASON_SPAM")
    if reason == _MODERATION_REASON_TOXIC:
        return trans.gettext("MODERATION_REASON_TOXIC")
    raise RuntimeError(f"Unknown reason {reason}")


def _accept_complaint_option() -> str:
    return i18n.default().gettext("MODERATION_ACCEPT_COMPLAINT_ANSWER_ACCEPT")


def _reject_complaint_option() -> str:
    return i18n.default().gettext("MODERATION_ACCEPT_COMPLAINT_ANSWER_REJECT")


def _get_complaint_reason_keyboard(user: User, original_message_id: int) -> InlineKeyboardMarkup:
    """Build the keyboard for selecting a reason for sending a moderation request

    Returns an instance of InlineKeyboardMarkup that contains a vertically aligned set of reasons:

    +----------+
    | Reason 1 |
    +----------+
    | Reason 2 |
    +----------+
    | ...      |
    +----------+

    Each button has the reason ID in its callback data.
    """

    trans = i18n.trans(user)

    buttons = [(InlineKeyboardButton(_reason_to_explanation(reason_id, trans),
                                     callback_data=f"{original_message_id}:{user.id}:{reason_id}"),) for reason_id in
               range(5)]
    return InlineKeyboardMarkup(buttons)


def _maybe_log_normal_message(update: Update) -> None:
    """Record a normal message or an edit that happened in the main chat"""

    assert update.effective_chat.id == settings.MAIN_CHAT_ID

    if not update.message and not update.edited_message:
        logging.info("Skipping an update that does not have a new or edited message.")
        return

    state.MainChatMessage.log(update.effective_message)


async def _maybe_start_complaint(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Start the complaint process if the initial message meets required criteria"""

    user = update.effective_user

    if not await is_member_of_main_chat(user, context):
        return

    message = update.effective_message

    assert update.effective_chat.type == ChatType.PRIVATE and message.forward_origin is not None

    trans = i18n.trans(user)

    original_message = state.MainChatMessage.find_original(message)
    if original_message is None:
        logging.info("Forwarded message was not found in the log, cannot accept complaint.")
        await message.reply_text(trans.gettext("DM_MODERATION_MESSAGE_NOT_FOUND"))
        return

    # TODO: do not let moderators send requests for moderation?

    if state.complaint_get(original_message).has_user(user.id):
        logging.info("This user has already complained about this message, cannot accept another complaint.")
        await message.reply_text(trans.gettext("DM_MODERATION_MESSAGE_ALREADY_COMPLAINED"))
        return

    await context.bot.send_message(chat_id=user.id,
                                   text=i18n.trans(user).gettext("DM_MODERATION_MESSAGE_SELECT_COMPLAINT_REASON"),
                                   reply_markup=_get_complaint_reason_keyboard(user, original_message.tg_id))


async def _accept_complaint_reason(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Add one more reason to a complaint, and start a moderation poll if there are enough reasons"""

    query = update.callback_query

    await query.answer()

    original_message_id, from_user_id, reason_id = (int(x) for x in query.data.split(":"))

    complaint = state.complaint_maybe_add(original_message_id, from_user_id, reason_id)

    await context.bot.send_message(chat_id=update.effective_chat.id,
                                   text=i18n.trans(update.effective_user).gettext("DM_MODERATION_REQUEST_REGISTERED"))

    if complaint.count < settings.MODERATION_COMPLAINT_THRESHOLD:
        logging.info(f"Message {original_message_id} currently has {complaint.count} complaints, which is below "
                     f"threshold of {settings.MODERATION_COMPLAINT_THRESHOLD}, waiting for more")
        return

    trans = i18n.default()

    chat_id = settings.MODERATION_CHAT_ID

    moderation_request = [trans.gettext("MODERATION_NEW_REQUEST")]
    for reason, count in complaint.reasons.items():
        moderation_request.append(trans.ngettext("MODERATION_NEW_REQUEST_DETAILS_S {reason} {count}",
                                                 "MODERATION_NEW_REQUEST_DETAILS_P {reason} {count}",
                                                 count).format(reason=_reason_to_explanation(reason, trans),
                                                               count=count))
    await context.bot.send_message(chat_id, text="\n".join(moderation_request))
    await context.bot.forward_message(chat_id, settings.MAIN_CHAT_ID, message_id=original_message_id)
    new_poll_message = await context.bot.send_poll(chat_id, is_anonymous=True,
                                                   question=trans.gettext("MODERATION_ACCEPT_COMPLAINT_QUESTION"),
                                                   options=(_accept_complaint_option(), _reject_complaint_option()))

    state.poll_register(original_message_id, new_poll_message.id, new_poll_message.poll.id)

    logging.info(f"Started a new moderation poll {new_poll_message.poll.id}")


async def _handle_complaint_poll(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle updates to polls

    Evaluates the updated poll state and decides if the decision can be made.  If there are enough votes to proceed,
    closes the poll and calls `_handle_poll_outcome()`.
    """

    chat_id = settings.MODERATION_CHAT_ID
    # TODO: move setting the moderator count to init()?  Maybe add handler for people joining the group and recalculate?
    moderator_count = await context.bot.get_chat_member_count(chat_id) - settings.MODERATION_CHAT_BOT_COUNT
    poll = update.poll

    if poll.is_closed:
        logging.info("Ignoring an update for a poll that is already closed.")
        return

    quorum_threshold = ceil(moderator_count * settings.MODERATION_QUORUM_THRESHOLD)

    if poll.total_voter_count < quorum_threshold:
        logging.info(f"Poll {poll.id} has {poll.total_voter_count} votes which is still fewer than threshold of "
                     f"{quorum_threshold}")
        return

    winning_vote_count = ceil(quorum_threshold * settings.MODERATION_WINNING_THRESHOLD)
    winner_option = ""
    for option in poll.options:
        if option.voter_count >= winning_vote_count:
            assert winner_option == ""
            winner_option = option.text
    if winner_option != "":
        logging.info(f"Poll {poll.id} has quorum, and option {winner_option} got enough votes to be accepted")
        await _handle_complaint_poll_outcome(poll, winner_option, context)
        return

    if poll.total_voter_count < moderator_count:
        logging.info(
            f"Poll {poll.id} has quorum but no options got enough votes to be accepted, so going on with voting")
        return

    logging.info("All moderators voted, calculating the winner option")
    score = {option.text: option.voter_count for option in poll.options}
    assert len(score.keys()) == 2
    accept, reject = _accept_complaint_option(), _reject_complaint_option()
    winner_option = accept if score[accept] >= score[accept] else reject

    await _handle_complaint_poll_outcome(poll, winner_option, context)


async def _handle_complaint_poll_outcome(poll: Poll, resolution: str, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle outcome of a complaint poll"""

    poll_metadata = state.poll_get(poll.id)

    chat_id = settings.MODERATION_CHAT_ID

    trans = i18n.default()
    if poll.is_closed:
        logging.info(f"Poll {poll.id} is already closed.")
    else:
        logging.info(f"Closing poll {poll.id}.")
        await context.bot.stop_poll(chat_id, poll_metadata.poll_message_id)

    if resolution == _reject_complaint_option():
        logging.info("Complaint was rejected.")
        await context.bot.send_message(chat_id, text=trans.gettext("MODERATION_RESULT_REJECTED"))
    else:
        logging.info("Complaint was accepted.  Setting a restriction.")
        original_message = state.MainChatMessage.get(poll_metadata.original_message_id)
        current_restriction = state.Restriction.get_or_create(original_message.sender_tg_id)
        state.Restriction.elevate(current_restriction)
        await context.bot.send_message(chat_id, text=trans.gettext("MODERATION_RESULT_ACCEPTED"))

    # TODO: the state should not be cleaned immediately.  The data should be kept within the time frame of accepting new
    # moderation requests.
    state.clean(poll_metadata.original_message_id)


async def _handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle an incoming message.  This is the single entry point for all normal messages."""

    chat = update.effective_chat

    if chat is None:
        logging.warning("moderation._handle_message() has got an update where chat is None")
        return

    if chat.id == settings.MAIN_CHAT_ID:
        _maybe_log_normal_message(update)
    elif chat.type == ChatType.PRIVATE and update.effective_message.forward_origin is not None:
        await _maybe_start_complaint(update, context)
    elif chat.id == settings.MODERATION_CHAT_ID:
        pass
    else:
        logging.error("This should not come here!")


def init(application: Application, group):
    """Prepare the feature as defined in the configuration"""

    if not settings.MODERATION_ENABLED:
        return

    state.init()

    # TODO: handle images
    application.add_handler(MessageHandler(filters.TEXT & (~ filters.COMMAND), _handle_message), group=group)

    application.add_handler(
        CallbackQueryHandler(_accept_complaint_reason, pattern=re.compile("^[0-9]+:[0-9]+:[0-9]+$")), group=group)

    application.add_handler(PollHandler(_handle_complaint_poll))


def post_init(application: Application, group):
    """Post-init"""

    if not settings.MODERATION_ENABLED:
        return

    pass

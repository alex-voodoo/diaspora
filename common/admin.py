"""
Admin utilities
"""

from telegram import InlineKeyboardMarkup

buttons = None

def register_buttons(row) -> None:
    """Register one or more rows of buttons in the main administrator's keyboard"""

    global buttons

    if not buttons:
        buttons = []

    buttons += row


def get_main_keyboard() -> InlineKeyboardMarkup:
    """Return main administrator's keyboard

    The keyboard is built based on the global `buttons` sequence prepared at init time with calls to `register_button()`
    from the core module and features.
    """

    global buttons

    return InlineKeyboardMarkup(buttons)

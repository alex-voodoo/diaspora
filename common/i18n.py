"""
Internationalisation utilities
"""

import gettext

from telegram import User

from settings import SPEAK_USER_LANGUAGE, DEFAULT_LANGUAGE, SUPPORTED_LANGUAGES


_last_used_lang = None
_last_used_trans = None


def default():
    """Get the default translator"""

    return gettext.translation("bot", localedir="locales", languages=[DEFAULT_LANGUAGE])


def trans(user: User):
    """Get a translator for the given user

    Respects the language-related settings.  Caches the translator and only loads another one if the language changes.
    """

    if not SPEAK_USER_LANGUAGE or user.language_code not in SUPPORTED_LANGUAGES:
        user_lang = DEFAULT_LANGUAGE
    else:
        user_lang = user.language_code

    global _last_used_lang, _last_used_trans
    if _last_used_lang != user_lang:
        _last_used_lang = user_lang
        _last_used_trans = gettext.translation("bot", localedir="locales", languages=[user_lang])

    return _last_used_trans

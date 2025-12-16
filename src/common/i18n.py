"""
Internationalisation utilities
"""

import gettext
import pathlib

from telegram import User

from common.settings import settings


_last_used_lang = None
_last_used_trans = None


def _get_locale_directory() -> pathlib.Path:
    """Get absolute path to the locale directory"""

    return pathlib.Path(__file__).parent.parent / "locales"


def default():
    """Get the default translator"""

    return gettext.translation("bot", localedir=_get_locale_directory(), languages=[settings.DEFAULT_LANGUAGE])


def trans(user: User):
    """Get a translator for the given user

    Respects the language-related settings.  Caches the translator and only loads another one if the language changes.
    """

    if not settings.SPEAK_USER_LANGUAGE or user.language_code not in settings.SUPPORTED_LANGUAGES:
        user_lang = settings.DEFAULT_LANGUAGE
    else:
        user_lang = user.language_code

    global _last_used_lang, _last_used_trans
    if _last_used_lang != user_lang:
        _last_used_lang = user_lang
        _last_used_trans = gettext.translation("bot", localedir=_get_locale_directory(), languages=[user_lang])

    return _last_used_trans

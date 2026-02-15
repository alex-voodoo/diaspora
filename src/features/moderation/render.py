import gettext

from . import const


def reason_title(trans: gettext.GNUTranslations, reason_id: int) -> str:
    if reason_id == const.MODERATION_REASON_FRAUD:
        return trans.gettext("MODERATION_REASON_FRAUD")
    if reason_id == const.MODERATION_REASON_OFFENSE:
        return trans.gettext("MODERATION_REASON_OFFENSE")
    if reason_id == const.MODERATION_REASON_RACISM:
        return trans.gettext("MODERATION_REASON_RACISM")
    if reason_id == const.MODERATION_REASON_SPAM:
        return trans.gettext("MODERATION_REASON_SPAM")
    if reason_id == const.MODERATION_REASON_TOXIC:
        return trans.gettext("MODERATION_REASON_TOXIC")
    raise RuntimeError(f"Unknown reason {reason_id}")

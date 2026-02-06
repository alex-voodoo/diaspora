"""
Functions used to produce user-facing text in messages
"""

import gettext
from collections.abc import Iterable

from . import state


def service_description_for_owner(service: state.Service) -> str:
    return (f"<b>{service.category.title}:</b> <a href=\"{service.deep_link}\">{service.occupation}</a> ("
            f"{service.location})")


def service_description_for_public(service: state.Service) -> str:
    return f"- @{service.tg_username} ({service.location}): <a href=\"{service.deep_link}\">{service.occupation}</a>"


def category_with_services(category: state.ServiceCategory, services: Iterable[state.Service]) -> str:
    return "\n".join([f"<b>{category.title}</b>", *[service_description_for_public(service) for service in services]])


def append_disclaimer(trans: gettext.GNUTranslations, message: str) -> str:
    return "\n\n".join([message, trans.gettext("SERVICES_DM_WHO_DISCLAIMER")])


def prepend_disclaimer(trans: gettext.GNUTranslations, message: str) -> str:
    return "\n\n".join([trans.gettext("SERVICES_DM_WHO_DISCLAIMER"), message])


def text_too_long(trans: gettext.GNUTranslations, text: str, limit: int) -> str:
    new_text = f"<b>{text[:limit]}</b>{text[limit:limit + 10]}…"

    return trans.ngettext("SERVICES_DM_TEXT_TOO_LONG_S {limit} {text}", "SERVICES_DM_TEXT_TOO_LONG_P {limit} {text}",
                          limit).format(limit=limit, text=new_text)


def categories_with_services(trans: gettext.GNUTranslations, services: dict) -> str:
    user_list = [trans.gettext("SERVICES_DM_WHO_LIST_HEADING")]
    for category in state.ServiceCategory.all():
        if category.id not in services:
            continue
        user_list.append("")
        user_list.append(category_with_services(category, services[category.id]))
    return append_disclaimer(trans, "\n".join(user_list))

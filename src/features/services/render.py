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

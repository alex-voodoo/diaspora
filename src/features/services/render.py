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
    return f"- @{service.provider.tg_username} ({service.location}): <a href=\"{service.deep_link}\">{service.occupation}</a>"


def category_with_services(category: state.ServiceCategory, services: Iterable[state.Service],
                           show_category_title: bool) -> str:
    if show_category_title:
        return "\n".join(
            [f"<b>{category.title}</b>", *[service_description_for_public(service) for service in services]])
    return "\n".join([service_description_for_public(service) for service in services])


def append_disclaimer(trans: gettext.GNUTranslations, message: str) -> str:
    return "\n\n".join([message, trans.gettext("SERVICES_DM_WHO_DISCLAIMER")])


def prepend_disclaimer(trans: gettext.GNUTranslations, message: str) -> str:
    return "\n\n".join([trans.gettext("SERVICES_DM_WHO_DISCLAIMER"), message])


def text_too_long(trans: gettext.GNUTranslations, text: str, limit: int) -> str:
    new_text = f"<b>{text[:limit]}</b>{text[limit:limit + 10]}…"

    return trans.ngettext("SERVICES_DM_TEXT_TOO_LONG_S {limit} {text}", "SERVICES_DM_TEXT_TOO_LONG_P {limit} {text}",
                          limit).format(limit=limit, text=new_text)


def data_field_limit(trans: gettext.GNUTranslations, limit: int) -> str:
    return trans.ngettext("SERVICES_DM_DATA_FIELD_LIMIT_S {limit}", "SERVICES_DM_DATA_FIELD_LIMIT_P {limit}",
                          limit).format(limit=limit)


def categories_with_services(trans: gettext.GNUTranslations, services: dict) -> str:
    user_list = [trans.gettext("SERVICES_DM_WHO_LIST_HEADING")]
    for category in state.ServiceCategory.all():
        if category.id not in services:
            continue
        user_list.append("")
        user_list.append(category_with_services(category, services[category.id], len(services) > 1))
    return append_disclaimer(trans, "\n".join(user_list))


def occupation_request_new_with_limit(trans: gettext.GNUTranslations, limit: int) -> str:
    lines = [trans.gettext("SERVICES_DM_ENROLL_ASK_OCCUPATION")]
    if limit > 0:
        lines.append(data_field_limit(trans, limit))
    return "\n".join(lines)


def occupation_request_update_with_limit(trans: gettext.GNUTranslations, category_title: str, current_value: str,
                                         limit: int) -> str:
    lines = ([trans.gettext("SERVICES_DM_UPDATE_OCCUPATION {title} {current_value}").format(
        title=category_title, current_value=current_value)])
    if limit > 0:
        lines.append(data_field_limit(trans, limit))
    return "\n".join(lines)


def select_category_to_retire(trans: gettext.GNUTranslations) -> str:
    return trans.gettext("SERVICES_DM_SELECT_CATEGORY_FOR_RETIRE")


def retired_confirmation(trans: gettext.GNUTranslations) -> str:
    return trans.gettext("SERVICES_DM_RETIRE")


def admin_user_record_approved(trans: gettext.GNUTranslations) -> str:
    return trans.gettext("SERVICES_ADMIN_USER_RECORD_APPROVED")


def admin_user_record_suspended(trans: gettext.GNUTranslations) -> str:
    return trans.gettext("SERVICES_ADMIN_USER_RECORD_SUSPENDED")


def enroll_declined_illegal_service(trans: gettext.GNUTranslations) -> str:
    return trans.gettext("SERVICES_DM_ENROLL_DECLINED_ILLEGAL_SERVICE")


def enroll_completed(trans: gettext.GNUTranslations) -> str:
    return trans.gettext("SERVICES_DM_ENROLL_COMPLETED")


def enroll_completed_post_moderation(trans: gettext.GNUTranslations) -> str:
    return trans.gettext("SERVICES_DM_ENROLL_COMPLETED_POST_MODERATION")


def enroll_completed_pre_moderation(trans: gettext.GNUTranslations) -> str:
    return trans.gettext("SERVICES_DM_ENROLL_COMPLETED_PRE_MODERATION")


def ping(trans: gettext.GNUTranslations, user_first_name: str, services: list[state.Service]) -> str:
    lines = []
    if len(services) == 1:
        lines.append(
            trans.gettext("SERVICES_DM_PING {user_first_name}").format(user_first_name=user_first_name))
    else:
        lines.append(trans.ngettext("SERVICES_DM_PING_S {user_first_name} {record_count}",
                                   "SERVICES_DM_PING_P {user_first_name} {record_count}",
                                    len(services)).format(user_first_name=user_first_name, record_count=len(services)))

    lines.append("")

    for record in services:
        lines.append(service_description_for_owner(record))

    lines.append("")

    lines.append(trans.gettext("SERVICES_DM_PING_QUESTION"))

    return "\n".join(lines)

def ping_confirmed_all(trans: gettext.GNUTranslations, days: int) -> str:
    return trans.ngettext("SERVICES_DM_PING_CONFIRMED_ALL_S {days}",
                          "SERVICES_DM_PING_CONFIRMED_ALL_P {days}",
                          days).format(days=days)


def ping_confirmed_all_with_edits(trans: gettext.GNUTranslations, days: int) -> str:
    return trans.ngettext("SERVICES_DM_PING_NEED_EDIT_S {days}",
                          "SERVICES_DM_PING_NEED_EDIT_P {days}",
                          days).format(days=days)


def ping_confirm_delete_all(trans: gettext.GNUTranslations) -> str:
    return trans.gettext("SERVICES_DM_PING_CONFIRM_DELETE_ALL")

def ping_delete_all_cancelled(trans) -> str:
    return trans.gettext("SERVICES_DM_PING_DELETE_ALL_CANCELLED")

def ping_delete_all_completed(trans) -> str:
    return trans.gettext("SERVICES_DM_PING_DELETE_ALL_COMPLETED")

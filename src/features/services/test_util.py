"""
Helper functions and constants used in tests
"""

import datetime
from collections.abc import Iterator

from telegram import User

from common.settings import settings

CATEGORY_1_ID = 1
CATEGORY_1_TITLE = "Category 1"

CATEGORY_2_ID = 2
CATEGORY_2_TITLE = "Category 2"

SERVICE_101_TG_ID = 101
SERVICE_101_CATEGORY_ID = CATEGORY_1_ID


def return_single_category(*args, **kwargs) -> Iterator[dict]:
    yield data_row_for_service_category(CATEGORY_1_ID)


def return_two_categories(*args, **kwargs) -> Iterator[dict]:
    yield data_row_for_service_category(CATEGORY_1_ID)
    yield data_row_for_service_category(CATEGORY_2_ID)


def return_no_categories(*args, **kwargs) -> Iterator[dict]:
    for _c in []:
        yield {}


def tg_username(tg_id: int) -> str:
    return f"username_{tg_id}"


def tg_first_name(tg_id: int) -> str:
    return f"Firstname_{tg_id}"


def occupation(tg_id: int) -> str:
    return f"Occupation {tg_id}"


def description(tg_id: int) -> str:
    return f"Description {tg_id}"


def location(tg_id: int) -> str:
    return f"Location {tg_id}"


def is_suspended(tg_id: int) -> bool:
    return tg_id % 2 == 1


def category_title(category_id: int) -> str:
    return f"Category {category_id}"


def last_modified(tg_id: int) -> datetime:
    return datetime.datetime.fromisoformat("2026-01-14 12:00:00") - datetime.timedelta(days=tg_id)


def create_test_user(tg_id: int) -> User:
    return User(id=tg_id, first_name=tg_first_name(tg_id), is_bot=False, username=tg_username(tg_id),
                language_code=settings.DEFAULT_LANGUAGE)


def data_row_for_service(tg_id: int, category_id: int) -> dict:
    """Return a dict sufficient to create a Service object with the given IDs

    @param tg_id: Telegram ID of the owner of the service
    @param category_id: ID of the category the service belongs to
    @return: dictionary that contains generated test values for all data fields necessary to construct a Service object
    """

    return {"tg_id": tg_id, "tg_username": tg_username(tg_id), "category_id": category_id,
            "occupation": occupation(tg_id), "description": description(tg_id), "location": location(tg_id),
            "is_suspended": is_suspended(tg_id), "last_modified": last_modified(tg_id)}


def data_row_for_service_category(category_id: int) -> dict:
    """Return a dict sufficient to create a ServiceCategory object with the given ID

    @param category_id: ID of the service category
    @return: dictionary that contains generated test values for all data fields necessary to construct a
    ServiceCategory object
    """

    return {"id": category_id, "title": category_title(category_id)}

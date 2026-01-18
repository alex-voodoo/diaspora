import datetime

from telegram import User

from common.settings import settings

CATEGORY_1_ID = 1
CATEGORY_1_TITLE = "Category 1"

CATEGORY_2_ID = 2
CATEGORY_2_TITLE = "Category 2"

SERVICE_101_TG_ID = 101
SERVICE_101_CATEGORY_ID = CATEGORY_1_ID


def return_single_category(*args, **kwargs) -> list:
    return [{"id": CATEGORY_1_ID, "title": CATEGORY_1_TITLE}]


def return_two_categories(*args, **kwargs) -> list:
    return [{"id": CATEGORY_1_ID, "title": CATEGORY_1_TITLE}, {"id": CATEGORY_2_ID, "title": CATEGORY_2_TITLE}]


def return_no_categories(*args, **kwargs) -> list:
    return []


def tg_username(tg_id: int) -> str:
    return f"username_{tg_id}"


def occupation(tg_id: int) -> str:
    return f"Occupation {tg_id}"


def description(tg_id: int) -> str:
    return f"Description {tg_id}"


def location(tg_id: int) -> str:
    return f"Location {tg_id}"


def is_suspended(tg_id: int) -> bool:
    return tg_id % 2 == 1


def last_modified(tg_id: int) -> datetime:
    return datetime.datetime.fromisoformat("2026-01-14 12:00:00") - datetime.timedelta(days=tg_id)


def service_get(tg_id: int, category_id: int = 0) -> list:
    return [
        {"tg_id": tg_id, "tg_username": tg_username(tg_id), "category_id": category_id, "occupation": occupation(tg_id),
         "description": description(tg_id), "location": location(tg_id), "is_suspended": is_suspended(tg_id),
         "last_modified": last_modified(tg_id)}]


def create_test_user(tg_id: int) -> User:
    return User(id=tg_id, first_name="Joe", is_bot=False, username=tg_username(tg_id),
                language_code=settings.DEFAULT_LANGUAGE)

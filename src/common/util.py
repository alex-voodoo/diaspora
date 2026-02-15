import datetime

def rounded_now() -> datetime.datetime:
    return datetime.datetime.now().replace(microsecond=0)


def db_format(value: datetime) -> str:
    return value.strftime("%Y-%m-%d %H:%M:%S")

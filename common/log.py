"""
Logging helpers
"""

import logging
from logging import Logger
from time import perf_counter


# noinspection SpellCheckingInspection
def get_file_logger(name: str, filename: str, fmt="[%(asctime)s] %(message)s") -> logging.Logger:
    """Create a file logger"""

    logger = logging.getLogger(name)
    file_handler = logging.FileHandler(filename)
    file_handler.setFormatter(logging.Formatter(fmt))
    logger.addHandler(file_handler)
    logger.propagate = False
    return logger


class LogTime:
    """Time measuring context manager, logs time elapsed while executing the context

    Usage:

        with LogTime("<task>", logging.getLogger("<module>"):
            ...

    The above will send an info level event to the given logger with text: "<task> took X ms".
    """

    def __init__(self, name: str, logger: Logger):
        self.name = name
        self.logger = logger

    def __enter__(self):
        self.started_at = perf_counter()

    def __exit__(self, exc_type, exc_val, exc_tb):
        elapsed = (perf_counter() - self.started_at) * 1000
        self.logger.info("{name} took {elapsed} ms".format(name=self.name, elapsed=elapsed))

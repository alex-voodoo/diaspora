"""
Logging helpers
"""

import logging
from time import perf_counter


class LogTime:
    """Time measuring context manager, logs time elapsed while executing the context

    Usage:

        with LogTime("<task description>"):
            ...

    The above will send an info level event with text: "<task description> took X ms".
    """

    def __init__(self, name: str):
        self.name = name

    def __enter__(self):
        self.started_at = perf_counter()

    def __exit__(self, exc_type, exc_val, exc_tb):
        elapsed = (perf_counter() - self.started_at) * 1000
        logging.info(f"{self.name} took {elapsed:.3f} ms")

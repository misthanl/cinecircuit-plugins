"""Per-run timings written through the public plugin logger."""

from contextlib import contextmanager
from time import monotonic
from typing import Any, Iterator


@contextmanager
def stage_timing(context: Any, stage: str, item: str = "") -> Iterator[None]:
    started = monotonic()
    status = "completed"
    try:
        yield
    except BaseException:
        status = "interrupted"
        raise
    finally:
        logger = getattr(context, "logger", None)
        if logger is not None:
            logger.debug(
                "Rank timing stage=%s item=%s status=%s seconds=%.3f",
                stage,
                item,
                status,
                monotonic() - started,
            )

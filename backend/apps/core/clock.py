"""A strictly increasing clock for append-only history.

History (audit trail, price chains, verification steps) is ordered by time. The OS clock can
return the same value for consecutive calls (Windows resolution is ~15.6 ms), which would make
"which came first?" undefined. This clock never returns a value <= the previous one inside a
process, so rows written one after the other always sort in the order they were written.
"""

import threading
from datetime import UTC, datetime, timedelta

_lock = threading.Lock()
_last: datetime | None = None


def now() -> datetime:
    global _last
    with _lock:
        current = datetime.now(UTC)
        if _last is not None and current <= _last:
            current = _last + timedelta(microseconds=1)
        _last = current
        return current

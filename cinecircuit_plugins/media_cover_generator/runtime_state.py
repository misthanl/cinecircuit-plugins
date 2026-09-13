"""Plugin-private state survives the host reloading its package per API request."""

import sys
import threading
from types import ModuleType
from _thread import LockType
from typing import Any, Protocol, cast


class CoverRuntimeState(Protocol):
    gate: LockType
    jobs: dict[str, Any]

_name = "_cinecircuit_cover_encoder_state_v1"
_module = sys.modules.get(_name)
if _module is None:
    _module = ModuleType(_name)
    setattr(_module, "gate", threading.Lock())
    setattr(_module, "jobs", {})
    sys.modules[_name] = _module
state = cast(CoverRuntimeState, _module)

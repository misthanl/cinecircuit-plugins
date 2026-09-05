"""Plugin-private state survives the host reloading its package per API request."""
import sys
import threading
from types import ModuleType

_name = '_cinecircuit_cover_encoder_state_v1'
state = sys.modules.get(_name)
if state is None:
    state = ModuleType(_name)
    state.gate = threading.Lock()
    state.jobs = {}
    sys.modules[_name] = state

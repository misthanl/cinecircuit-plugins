from types import SimpleNamespace

from cinecircuit_plugins.subtitle_manager.online_sources.base import SourceCandidate
from cinecircuit_plugins.subtitle_manager.sessions import SubtitleSessions


def test_candidate_handle_can_be_loaded_repeatedly_during_its_ttl():
    sessions = SubtitleSessions()
    context = SimpleNamespace(state=None)
    candidate = SourceCandidate("test", "one", "one.srt", downloadable=True)
    handle = sessions.remember_candidate(context, "/media/one.mkv", candidate)

    assert sessions.load_candidate(context, handle, "/media/one.mkv") == candidate
    assert sessions.load_candidate(context, handle, "/media/one.mkv") == candidate

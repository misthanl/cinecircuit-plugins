"""Provider-neutral subtitle search-plan generation."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from .identity import MediaIdentity


@dataclass(frozen=True, slots=True)
class SearchQuery:
    keyword: str
    title: str
    year: int | None = None
    season: int | None = None
    episode: int | None = None
    tmdb_id: str = ""
    imdb_id: str = ""
    douban_id: str = ""

    def parameters(self) -> dict[str, Any]:
        """Structured parameters for sources that support identity fields."""

        return {
            key: value
            for key, value in {
                "query": self.keyword,
                "title": self.title,
                "year": self.year,
                "season": self.season,
                "episode": self.episode,
                "tmdb_id": self.tmdb_id,
                "imdb_id": self.imdb_id,
                "douban_id": self.douban_id,
            }.items()
            if value not in (None, "")
        }


@dataclass(frozen=True, slots=True)
class SearchPlan:
    identity: MediaIdentity
    queries: tuple[SearchQuery, ...]
    season_pack: bool = False
    errors: tuple[str, ...] = ()


def build_search_plan(identity: MediaIdentity, *, season_pack: bool = False) -> SearchPlan:
    """Build deterministic queries without unsafe title-only episode fallback."""

    titles = identity.titles()
    if not titles:
        return SearchPlan(identity, (), season_pack, ("missing_title",))

    is_tv = (
        identity.media_type == "tv" or identity.season is not None or identity.episode is not None
    )
    if is_tv:
        if identity.season is None:
            return SearchPlan(identity, (), season_pack, ("missing_season",))
        if season_pack:
            token = f"S{identity.season:02d}"
            queries = [_query(identity, title, token, episode=None) for title in titles]
        else:
            if identity.episode is None:
                return SearchPlan(identity, (), False, ("missing_episode",))
            token = f"S{identity.season:02d}E{identity.episode:02d}"
            queries = [_query(identity, title, token, episode=identity.episode) for title in titles]
    else:
        queries = [
            _query(
                identity,
                title,
                str(identity.year) if identity.year else "",
                episode=None,
            )
            for title in titles
        ]
    deduplicated = {query.keyword.casefold(): query for query in queries}
    return SearchPlan(identity, tuple(deduplicated.values()), season_pack)


def _query(identity: MediaIdentity, title: str, suffix: str, *, episode: int | None) -> SearchQuery:
    return SearchQuery(
        keyword=" ".join(part for part in (title, suffix) if part),
        title=title,
        year=identity.year,
        season=identity.season,
        episode=episode,
        tmdb_id=identity.tmdb_id,
        imdb_id=identity.imdb_id,
        douban_id=identity.douban_id,
    )

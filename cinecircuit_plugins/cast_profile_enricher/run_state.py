from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from typing import Any


@dataclass(slots=True)
class RunState:
    profiles: dict[str, dict[str, Any]] = field(default_factory=dict)
    casts: dict[str, list[dict[str, Any]]] = field(default_factory=dict)
    updated_people: set[str] = field(default_factory=set)
    changed_people: set[str] = field(default_factory=set)
    scanned_media: int = 0
    scanned_people: int = 0
    updated_media: int = 0
    updated_profiles: int = 0
    updated_images: int = 0
    removed_people: int = 0
    failures: int = 0
    updated_names: int = 0
    updated_roles: int = 0
    updated_biographies: int = 0
    no_chinese_role: int = 0
    unmatched_people: int = 0
    request_failures: int = 0
    skipped_people: int = 0
    cache_hits: int = 0
    resumed_media: int = 0
    maintenance: Any = None
    media_written: set[str] = field(default_factory=set)
    retry_media: set[str] = field(default_factory=set)
    person_locks: dict[str, asyncio.Lock] = field(default_factory=dict)

    def result(self) -> dict[str, Any]:
        return {
            "scanned_media": self.scanned_media,
            "scanned_people": self.scanned_people,
            "updated_media": self.updated_media,
            "updated_profiles": self.updated_profiles,
            "updated_images": self.updated_images,
            "removed_people": self.removed_people,
            "failures": self.failures,
            **{
                key: getattr(self, key)
                for key in (
                    "updated_names",
                    "updated_roles",
                    "updated_biographies",
                    "no_chinese_role",
                    "unmatched_people",
                    "request_failures",
                    "skipped_people",
                    "cache_hits",
                    "resumed_media",
                )
            },
        }

"""Explicit opt-in removal after successful negative identity lookups."""


def can_remove(plugin, context, state, media, person, profile, cast):
    return (
        bool(context.config.get("remove_unresolved", False))
        and plugin._eligible(context, person)
        and bool(profile.get("_lookup_complete"))
        and set(profile.get("_checked_sources") or []) == {"tmdb", "douban"}
        and not profile.get("_source_matched")
        and bool(cast)
        and str(media.get("id")) not in state.retry_media
        and not plugin._identity_cast(person, cast)
        and not any(plugin._person_matches(str(person.get("Name") or ""), row) for row in cast)
        and not plugin._has_han(person.get("Name"))
        and not plugin._has_han(person.get("Role"))
    )


def role_changes(previous, updated):
    originals = {str(p.get("Id") or p.get("Name")): p for p in previous}
    return sum(
        originals.get(str(p.get("Id") or p.get("Name")), {}).get("Role") != p.get("Role")
        for p in updated
    )


def annotate_profile(merged, existing, metadata, complete, checked, matched):
    merged.update(
        _lookup_complete=complete,
        _checked_sources=list(checked),
        _source_matched=matched,
        _existing=existing,
        _locked_fields=list(metadata.get("locked_fields") or []),
        _provider_ids=dict(metadata.get("provider_ids") or {}),
    )
    return merged

"""Read persisted copy journals without remote requests."""


def records_from(state):
    after = ""
    while True:
        groups = state.list(prefix="records-", limit=500, after=after)
        for group in groups:
            for identity, record in (group.get("value") or {}).items():
                yield {**record, "identity": identity}
        if len(groups) < 500:
            return
        next_after = groups[-1]["key"]
        if next_after <= after:
            raise ValueError("复制记录分页没有前进")
        after = next_after


def all_batches(index):
    return sorted(iter_batches(index), key=lambda row: row["created_at"], reverse=True)


def iter_batches(index):
    """Bound each storage read; statistics need no creation-time materialization."""
    after = ""
    while True:
        page = index.list(prefix="task-", limit=500, after=after)
        yield from (row["value"] for row in page)
        if len(page) < 500:
            return
        next_after = page[-1]["key"]
        if next_after <= after:
            raise ValueError("复制批次分页没有前进")
        after = next_after

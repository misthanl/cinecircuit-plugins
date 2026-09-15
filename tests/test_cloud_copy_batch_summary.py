import pytest
from cinecircuit_plugins.cloud_copy.batch_summary import present_batch
from test_cloud_copy_manual import NamespacedState


@pytest.mark.parametrize("records,outcome,methods", [
    ([{"status":"skipped","reason":"rapid_material_unavailable"}], "skipped", []),
    ([{"status":"uncertain"}], "uncertain", []),
    ([{"status":"completed","method":"rapid"}], "completed", ["rapid"]),
    ([{"status":"completed","method":"relay"},{"status":"skipped"}], "partial", ["relay"]),
    ([{"status":"completed","method":"existing"},{"status":"completed","method":"rapid"}], "completed", ["existing","rapid"]),
])
def test_old_completed_batches_report_actual_results(records, outcome, methods):
    state=NamespacedState()
    state.set("records-fixture", {str(index):record for index,record in enumerate(records)})
    result=present_batch({"status":"completed","attention":1},state)
    assert result["outcome"]==outcome
    assert result["methods"]==methods
    assert result["skipped"]==sum(row["status"]=="skipped" for row in records)
    assert result["uncertain"]==sum(row["status"]=="uncertain" for row in records)
    if records[0].get("reason")=="rapid_material_unavailable":
        assert "当前策略无法直接秒传" in result["notes"][0]
        assert "rapid_material" not in result["notes"][0]
    assert state.get("records-fixture")["0"]==records[0]


def test_inflight_file_is_not_reported_as_uncertain():
    state=NamespacedState()
    state.set("records-fixture", {"1":{"status":"uncertain","path":"active.mkv"}})
    result=present_batch({"status":"running","current_file":"active.mkv"},state)
    assert result["uncertain"]==0
    assert result["notes"]==[]
    assert result["outcome"]=="running"

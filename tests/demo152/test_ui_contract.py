"""DEMO-152 single-page UI contract (static source checks)."""

from pathlib import Path

UI_PATH = Path(__file__).resolve().parents[2] / "ai_service" / "static" / "travel.html"


def _source():
    return UI_PATH.read_text(encoding="utf-8")


def test_independent_action_state_cancel_and_no_global_freeze():
    source = _source()
    for needle in ("chatBusy", "planBusy", "chatToken", "planToken",
                   "planController", "cancel-plan", "AbortController",
                   "Máy chủ có thể vẫn tiếp tục xử lý"):
        assert needle in source, needle
    assert "state.busy" not in source
    assert "beginFlight" not in source


def test_multiselect_sends_full_selection_and_has_explicit_controls():
    source = _source()
    for needle in ("<select id=\"area\" multiple", "source_area_ids",
                   "Toàn bộ vùng trong tập dữ liệu TP.HCM", "Bỏ chọn vùng",
                   "buildSelection", "source_scope: state.selection"):
        assert needle in source, needle
    # both planners receive the exact selection object, not a rebuilt single key
    assert source.count("source_area_id: state.selection.source_area_id") == 0


def test_route_layer_uses_only_validated_feature_collection_and_textcontent():
    source = _source()
    for needle in ("safeRouteGeometry", "route_geometry", "graphhopper",
                   "addSource", "removeSource", "renderRouteDirections",
                   "Chưa có hình học đường thực tế"):
        assert needle in source, needle
    assert "setHTML" not in source
    assert "innerHTML" not in source
    # The line source is the validated FeatureCollection, never marker pins.
    assert "data: route" in source
    assert "bounds.extend([pin.longitude, pin.latitude])" in source

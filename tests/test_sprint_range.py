"""Tests for the sprint_range module's window attachment and description fragment."""


def test_attach_range_window_lives_in_sprint_range_module():
    """AC1: the window attachment is importable from sprint_metrics.sprint_range,
    not from sprint_metrics.service, where the window was assembled inline in
    the /range handler before the move — the definition lives in the
    sprint_range module."""
    from sprint_metrics.sprint_range import _attach_range_window

    assert callable(_attach_range_window)
    assert _attach_range_window.__module__ == "sprint_metrics.sprint_range"


def test_attach_range_window_builds_top_level_window_object():
    """AC1/AC2: applying the window attachment from sprint_range.py puts the
    top-level window object on the range response: start, the first sprint
    label; end, the last sprint label; sprint_count, the number of sprints
    in the window; and no_data, the sprint labels that had no events — a
    range whose middle sprint has no events names it, a range with no gap
    sprints reads no_data as an empty list."""
    from sprint_metrics.sprint_range import _attach_range_window

    labels = ["2024-01", "2024-02", "2024-03"]
    result = {"sprints": {label: {} for label in labels}}
    _attach_range_window(result, labels, {"2024-01", "2024-03"})
    assert result["window"] == {
        "start": "2024-01",
        "end": "2024-03",
        "sprint_count": 3,
        "no_data": ["2024-02"],
    }

    result = {"sprints": {label: {} for label in ["2024-01", "2024-02"]}}
    _attach_range_window(result, ["2024-01", "2024-02"], {"2024-01", "2024-02"})
    assert result["window"] == {
        "start": "2024-01",
        "end": "2024-02",
        "sprint_count": 2,
        "no_data": [],
    }


def test_range_window_description_fragment_lives_in_sprint_range_module():
    """AC3: the window answer's description fragment is owned by
    sprint_range.py and tells the reader what the generated /range row tells
    them about the window: the response carries a top-level window object
    naming the window it is judging — start, the first sprint label; end,
    the last sprint label; sprint_count, the number of sprints in the
    window; and no_data, the sprint labels that had no events."""
    from sprint_metrics.service import SERVICE_ENDPOINTS
    from sprint_metrics.sprint_range import _RANGE_WINDOW_DESCRIPTION

    for phrase in (
        "top-level window object",
        "first sprint label",
        "last sprint label",
        "number of sprints in the window",
        "sprint labels that had no events",
    ):
        assert phrase in _RANGE_WINDOW_DESCRIPTION, f"fragment missing {phrase!r}"
    # The generated /range row tells the reader exactly this: the fragment is
    # composed into the /range endpoint description.
    range_desc = next(desc for method, path, desc in SERVICE_ENDPOINTS if path == "/range")
    assert _RANGE_WINDOW_DESCRIPTION in range_desc

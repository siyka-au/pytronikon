"""Regression tests for the live_selector index assigned by each discovery function.

These indices were verified against the manufacturer's own web UI JavaScript source
(fetched directly from a live controller) after a real-world data integrity bug was
found: digital_inputs was reading digital_outputs' live index (0x3005 instead of
0x3003), digital_outputs was reading analog_outputs' index (0x3006 instead of 0x3005),
counters pointed at an unused index (0x3008 instead of 0x3007), and special_protections
was reading service_plan's index (0x3009 instead of 0x300E). Each of these silently
returned plausible-looking but wrong (or entirely absent) data instead of erroring.
"""

from pytronikon.catalog import (
    _discover_counters,
    _discover_digital_inputs,
    _discover_digital_outputs,
    _discover_special_protections,
)
from pytronikon.codec import Answer, format_selector


class FakeTransport:
    """Returns one non-zero point at the first queried selector, "X" for the rest."""

    def __init__(self, live_index: int, live_subindex: int = 1):
        self.live_index = live_index
        self.live_subindex = live_subindex

    def query_selectors(self, selectors):
        answers = []
        for i, sel in enumerate(selectors):
            if i == 0:
                # "00010001": byte 0 (last 2 hex chars) = 1 -- point exists;
                # word 1 (first 4 hex chars) = 1 -- MPL = 1.
                raw = "00010001"
            else:
                raw = "X"
            answers.append(Answer(key=sel.key, index=sel.index, subindex=sel.subindex, raw=raw))
        return answers


def test_discover_digital_inputs_uses_0x3003():
    """Test digital_inputs' live selector is 0x3003, not digital_outputs' 0x3005."""
    points = _discover_digital_inputs(FakeTransport(0x20B0), {})
    assert len(points) == 1
    assert points[0]["live_selectors"][0]["index"] == 0x3003
    assert points[0]["live_selectors"][0]["selector"] == format_selector(0x3003, 1)


def test_discover_digital_outputs_uses_0x3005():
    """Test digital_outputs' live selector is 0x3005, not analog_outputs' 0x3006."""
    points = _discover_digital_outputs(FakeTransport(0x2100), {})
    assert len(points) == 1
    assert points[0]["live_selectors"][0]["index"] == 0x3005
    assert points[0]["live_selectors"][0]["selector"] == format_selector(0x3005, 1)


def test_discover_counters_uses_0x3007():
    """Test counters' live selector is 0x3007, not the unused 0x3008."""
    points = _discover_counters(FakeTransport(0x2607), {})
    assert len(points) == 1
    assert points[0]["live_selectors"][0]["index"] == 0x3007
    assert points[0]["live_selectors"][0]["selector"] == format_selector(0x3007, 1)


def test_discover_special_protections_uses_0x300E():
    """Test special_protections' live selector is 0x300E, not service_plan's 0x3009."""
    points = _discover_special_protections(FakeTransport(0x2300), {})
    assert len(points) == 1
    assert points[0]["live_selectors"][0]["index"] == 0x300E
    assert points[0]["live_selectors"][0]["selector"] == format_selector(0x300E, 1)

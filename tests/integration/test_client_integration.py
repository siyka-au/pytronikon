"""Integration tests for the client against a live controller."""

import os

import pytest

from pytronikon.client import ElektronikonClient


pytestmark = pytest.mark.integration


@pytest.fixture
def host():
    """Get the integration test host."""
    return os.environ.get("ELEKTRONIKON_HOST", "192.168.100.100")


@pytest.mark.skipif(
    os.environ.get("ELEKTRONIKON_RUN_INTEGRATION") != "1",
    reason="ELEKTRONIKON_RUN_INTEGRATION not set",
)
def test_query_few_selectors(host):
    """Test querying a few raw selectors."""
    client = ElektronikonClient(host=host, timeout=10.0)
    result = client.query_raw(["300201", "300301", "300701"])

    assert result["selector_count"] == 3
    assert len(result["results"]) == 3

    # Pressure should be in bar (5000-9000 scaled down)
    pressure = [r for r in result["results"] if r["selector"] == "300201"][0]
    assert pressure["raw"] != "X"
    assert len(pressure["raw"]) == 8

    # Digital input should be 0 or 1
    digital = [r for r in result["results"] if r["selector"] == "300301"][0]
    assert digital["raw"] != "X"

    # Running hours should be large
    hours = [r for r in result["results"] if r["selector"] == "300701"][0]
    assert hours["raw"] != "X"


@pytest.mark.skipif(
    os.environ.get("ELEKTRONIKON_RUN_INTEGRATION") != "1",
    reason="ELEKTRONIKON_RUN_INTEGRATION not set",
)
def test_discover(host):
    """Test discovery reproduces the active surface."""
    client = ElektronikonClient(host=host, timeout=10.0)
    catalog = client.discover()

    assert catalog.family_counts["analog_inputs"] >= 4
    assert catalog.family_counts["digital_inputs"] >= 3
    assert catalog.family_counts["digital_outputs"] >= 6
    assert catalog.family_counts["counters"] >= 1
    assert "analog_inputs:compressor-outlet" in catalog.points_by_id


@pytest.mark.skipif(
    os.environ.get("ELEKTRONIKON_RUN_INTEGRATION") != "1",
    reason="ELEKTRONIKON_RUN_INTEGRATION not set",
)
def test_query_all_discovered(host):
    """Test querying all discovered points."""
    client = ElektronikonClient(host=host, timeout=10.0)
    client.discover()
    result = client.query(all_discovered=True)

    assert result["selector_count"] > 0
    assert len(result["point_results"]) > 20

    # Check that we have the compressor outlet
    compressor = [p for p in result["point_results"] if p.get("id") == "analog_inputs:compressor-outlet"]
    assert len(compressor) == 1
    assert "normalized" in compressor[0]
    assert compressor[0]["normalized"]["value"] > 5.0
    assert compressor[0]["normalized"]["value"] < 9.0
    assert compressor[0]["normalized"]["unit"] == "bar"

    # Check that we have machine state
    machine_state = [p for p in result["point_results"] if p.get("id") == "machine_state:current"]
    assert len(machine_state) == 1
    assert "primary_label" in machine_state[0]


@pytest.mark.skipif(
    os.environ.get("ELEKTRONIKON_RUN_INTEGRATION") != "1",
    reason="ELEKTRONIKON_RUN_INTEGRATION not set",
)
def test_mixed_query(host):
    """Test mixed query with selectors, points, and families."""
    client = ElektronikonClient(host=host, timeout=10.0)
    client.discover()
    result = client.query(
        selectors=["300201"],
        points=["analog_inputs:compressor-outlet"],
        families=["digital_outputs"],
    )

    # Direct result for 300201
    assert len(result["direct_results"]) == 1
    assert result["direct_results"][0]["selector"] == "300201"

    # Point results include compressor outlet
    assert any(p.get("id") == "analog_inputs:compressor-outlet" for p in result["point_results"])

    # Point results include all digital outputs
    digital_outputs = [p for p in result["point_results"] if p.get("family") == "digital_outputs"]
    assert len(digital_outputs) >= 6

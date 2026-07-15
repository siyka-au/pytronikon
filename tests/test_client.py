"""Tests for the client module."""

import pytest

from pytronikon.client import ElektronikonClient
from pytronikon.codec import Selector
from pytronikon.errors import UnknownFamilyError, UnknownPointError, UsageError
from pytronikon.protocol import ElektronikonTransport
from tests.conftest import FakeHTTPConnection, FakeResponse


@pytest.fixture
def mock_transport():
    """Create a mock transport for testing."""
    conn = FakeHTTPConnection()
    
    def fixed_factory():
        return conn
    
    return ElektronikonTransport(
        host="test.local",
        connection_factory=fixed_factory,
    ), conn


def test_client_query_raw(mock_transport):
    """Test query_raw without discovery."""
    transport, conn = mock_transport
    conn.set_response(FakeResponse(body=b"1B520080"))

    client = ElektronikonClient(transport=transport)
    result = client.query_raw(["300201"])

    assert result["selector_count"] == 1
    assert result["results"][0]["selector"] == "300201"
    assert result["results"][0]["raw"] == "1B520080"


def test_client_query_without_discovery_raises():
    """Test that querying by point without discovery raises error."""
    transport = ElektronikonTransport(host="test.local")
    client = ElektronikonClient(transport=transport)

    with pytest.raises(UsageError) as exc_info:
        client.query(points=["analog_inputs:compressor_outlet"])

    assert "discover()" in str(exc_info.value).lower()


def test_client_query_all_without_discovery_raises():
    """Test that querying all without discovery raises error."""
    transport = ElektronikonTransport(host="test.local")
    client = ElektronikonClient(transport=transport)

    with pytest.raises(UsageError) as exc_info:
        client.query(all_discovered=True)

    assert "discover()" in str(exc_info.value).lower()


def test_client_query_family_without_discovery_raises():
    """Test that querying family without discovery raises error."""
    transport = ElektronikonTransport(host="test.local")
    client = ElektronikonClient(transport=transport)

    with pytest.raises(UsageError) as exc_info:
        client.query(families=["digital_outputs"])

    assert "discover()" in str(exc_info.value).lower()


def test_client_query_with_selectors_no_discovery(mock_transport):
    """Test that query with selectors only doesn't require discovery."""
    transport, conn = mock_transport
    # Set up two responses: one for language file fetch, one for query
    language_response = FakeResponse(body=b"dummy$$test\r\n")
    query_response = FakeResponse(body=b"1B520080")
    conn.set_responses([language_response, query_response])

    client = ElektronikonClient(transport=transport)
    result = client.query(selectors=["300201"])

    assert result["selector_count"] == 1
    assert result["direct_results"][0]["selector"] == "300201"


def test_client_unknown_point_after_discovery():
    """Test that unknown point raises error."""
    conn = FakeHTTPConnection()
    
    def fixed_factory():
        return conn
    
    transport = ElektronikonTransport(host="test.local", connection_factory=fixed_factory)
    client = ElektronikonClient(transport=transport)

    # Mock the discover method to return an empty catalog
    from pytronikon.catalog import Catalog

    empty_catalog = Catalog(
        discovered_at="2026-01-01T00:00:00Z",
        families={},
        family_counts={},
        points_by_id={},
    )
    client.load_catalog(empty_catalog)

    with pytest.raises(UnknownPointError) as exc_info:
        client.query(points=["analog_inputs:nonexistent"])

    assert "analog_inputs:nonexistent" in str(exc_info.value)


def test_client_unknown_family_after_discovery():
    """Test that unknown family raises error."""
    conn = FakeHTTPConnection()
    
    def fixed_factory():
        return conn
    
    transport = ElektronikonTransport(host="test.local", connection_factory=fixed_factory)
    client = ElektronikonClient(transport=transport)

    # Mock the discover method to return an empty catalog
    from pytronikon.catalog import Catalog

    empty_catalog = Catalog(
        discovered_at="2026-01-01T00:00:00Z",
        families={},
        family_counts={},
        points_by_id={},
    )
    client.load_catalog(empty_catalog)

    with pytest.raises(UnknownFamilyError) as exc_info:
        client.query(families=["nonexistent_family"])

    assert "nonexistent_family" in str(exc_info.value)


def test_client_context_manager(mock_transport):
    """Test that client can be used as a context manager."""
    transport, conn = mock_transport
    conn.set_response(FakeResponse(body=b"1B520080"))

    with ElektronikonClient(transport=transport) as client:
        result = client.query_raw(["300201"])
        assert result["selector_count"] == 1

    assert conn.closed


def test_client_host_from_env(monkeypatch):
    """Test that host can be set from environment."""
    monkeypatch.setenv("ELEKTRONIKON_HOST", "192.168.100.50")
    client = ElektronikonClient()
    assert client.transport.host == "192.168.100.50"


def test_client_default_host(monkeypatch):
    """Test that default host is used when not specified."""
    # Clear ELEKTRONIKON_HOST env var if set
    monkeypatch.delenv("ELEKTRONIKON_HOST", raising=False)
    client = ElektronikonClient()
    assert client.transport.host == "192.168.100.100"


def test_client_custom_host():
    """Test that custom host is used."""
    client = ElektronikonClient(host="10.10.10.10")
    assert client.transport.host == "10.10.10.10"


def test_client_load_catalog_enables_query_without_discover(mock_transport):
    """Test that load_catalog() lets query(all_discovered=True) work without calling discover()."""
    from pytronikon.catalog import Catalog

    transport, conn = mock_transport
    language_response = FakeResponse(body=b"dummy$$test\r\n")
    query_response = FakeResponse(body=b"1B520080")
    conn.set_responses([language_response, query_response])

    catalog = Catalog(
        discovered_at="2026-01-01T00:00:00Z",
        families={
            "analog_inputs": [
                {
                    "id": "analog_inputs:test",
                    "family": "analog_inputs",
                    "live_selectors": [{"index": 0x3002, "subindex": 1}],
                }
            ]
        },
        family_counts={"analog_inputs": 1},
        points_by_id={
            "analog_inputs:test": {
                "id": "analog_inputs:test",
                "family": "analog_inputs",
                "live_selectors": [{"index": 0x3002, "subindex": 1}],
            }
        },
    )

    client = ElektronikonClient(transport=transport)
    client.load_catalog(catalog)

    result = client.query(all_discovered=True)

    assert result["catalog_summary"] == {"analog_inputs": 1}
    assert len(result["point_results"]) == 1
    assert result["point_results"][0]["id"] == "analog_inputs:test"


def test_client_load_catalog_round_trip_via_dict(mock_transport):
    """Test that a catalog serialized with to_dict() and restored with from_dict() works via load_catalog()."""
    from pytronikon.catalog import Catalog

    transport, conn = mock_transport

    original = Catalog(
        discovered_at="2026-01-01T00:00:00Z",
        families={"digital_inputs": [{"id": "digital_inputs:x", "family": "digital_inputs", "live_selectors": []}]},
        family_counts={"digital_inputs": 1},
        points_by_id={"digital_inputs:x": {"id": "digital_inputs:x", "family": "digital_inputs", "live_selectors": []}},
    )

    restored = Catalog.from_dict(original.to_dict())

    client = ElektronikonClient(transport=transport)
    client.load_catalog(restored)

    # No selectors to query for this point, so no HTTP call is made -- just confirm
    # query(all_discovered=True) no longer raises UsageError after load_catalog().
    result = client.query(all_discovered=True)
    assert result["point_results"][0]["id"] == "digital_inputs:x"

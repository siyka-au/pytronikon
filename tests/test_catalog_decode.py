"""Tests for catalog decoding."""

import pytest

from pytronikon.catalog import Catalog, decode_point


def test_decode_analog_input(english_language_map):
    """Test decoding an analog input point."""
    point = {
        "family": "analog_inputs",
        "id": "analog_inputs:compressor-outlet",
        "index": 0x2010,
        "rtd_si": 1,
        "mpl": 6994,
        "label": "Compressor Outlet Pressure",
        "input_type": 0,  # bar / 1000
        "live_selectors": [{"index": 0x3002, "subindex": 1}],
    }

    # Raw value: "61940000"
    # Status word 0 = 0x0000, Pressure word 1 = 0x6194 = 24980 / 1000 = 24.980 bar
    raw_map = {"300201": "61940000"}

    result = decode_point(point, raw_map, english_language_map)

    assert result["raw"] == "61940000"
    assert result["status"] == 0
    assert result["raw_value"] == 24980
    assert result["normalized"]["unit"] == "bar"
    assert result["normalized"]["value"] == 24.980


def test_decode_digital_input(english_language_map):
    """Test decoding a digital input point."""
    point = {
        "family": "digital_inputs",
        "id": "digital_inputs:switch-1",
        "index": 0x20B0,
        "rtd_si": 1,
        "mpl": 7000,
        "label": "Switch 1",
        "live_selectors": [{"index": 0x3003, "subindex": 1}],
    }

    # Status=0, Value=1
    raw_map = {"300301": "00010000"}

    result = decode_point(point, raw_map, english_language_map)

    assert result["raw"] == "00010000"
    assert result["status"] == 0
    assert result["value"] == 1


def test_decode_counter(english_language_map):
    """Test decoding a counter point."""
    point = {
        "family": "counters",
        "id": "counters:running-hours",
        "index": 0x2607,
        "rtd_si": 1,
        "mpl": 7001,
        "label": "Running Hours",
        "counter_unit": 0,  # hours (divide by 3600)
        "live_selectors": [{"index": 0x3007, "subindex": 1}],
    }

    # Raw value: 0x01F13D40 = 33000000 seconds = 9166.67 hours
    # In hex format as AABBCCDD where AA is byte 3, BB is byte 2, CC is byte 1, DD is byte 0
    # 0x01F13D40 is stored as "01F13D40" in the response
    raw_map = {"300701": "01F13D40"}

    result = decode_point(point, raw_map, english_language_map)

    assert result["raw"] == "01F13D40"
    assert result["raw_value"] == 0x01F13D40
    assert result["normalized"]["unit"] == "hours"
    assert result["normalized"]["value"] == 0x01F13D40 // 3600


def test_decode_missing_value(english_language_map):
    """Test decoding a missing (X) value."""
    point = {
        "family": "analog_inputs",
        "id": "analog_inputs:test",
        "index": 0x2010,
        "input_type": 0,
        "live_selectors": [{"index": 0x3002, "subindex": 1}],
    }

    raw_map = {"300201": "X"}

    result = decode_point(point, raw_map, english_language_map)

    assert result["raw"] == "X"
    assert result["raw_value"] is None
    assert result["normalized"] is None


def test_decode_machine_state(english_language_map):
    """Test decoding machine state point."""
    point = {
        "family": "machine_state",
        "id": "machine_state:current",
        "label": "Machine State",
        "count": 1,
        "live_selectors": [
            {"index": 0x3001, "subindex": 8},
        ],
        "state_labels": english_language_map,
    }

    # Primary state = 1 (Running)
    # read_int16(raw, 0) reads word 0 (low word)
    # Word 0 = chars 4-8 of "AABBCCDD" format
    # For word 0 = 1, we need "00000001"
    raw_map = {"300108": "00000001"}

    result = decode_point(point, raw_map, english_language_map)

    assert result["raw"] == "00000001"
    assert result["primary_state"] == 1
    assert result["primary_label"] == "Running"


def test_decode_service_plan(english_language_map):
    """Test decoding service plan point."""
    point = {
        "family": "service_plan",
        "id": "service_plan:level-1",
        "label": "Service level 1 running_hours",
        "level": 1,
        "kind": "running_hours",
        "rtd_si": 6,
        "live_selectors": [
            {"index": 0x3009, "subindex": 1},
            {"index": 0x3009, "subindex": 6},
        ],
    }

    # Mask with bit 0 set = next service is level 1
    # Current hours as word 1 = 0x1000
    raw_map = {
        "300901": "00000001",  # Mask
        "300906": "00001000",  # Current hours
    }

    result = decode_point(point, raw_map, english_language_map)

    assert result["next_mask_raw"] == "00000001"
    assert result["is_next"] is True
    assert result["current_value"] == 4096  # read_int16(word=1) of "00001000"


def test_decode_es_controller(english_language_map):
    """Test decoding ES controller point."""
    point = {
        "family": "es",
        "id": "es:controller",
        "label": "ES Controller",
        "live_selectors": [
            {"index": 0x3113, "subindex": 1},
        ],
    }

    # Format: AABBCCDD where:
    # AA = byte 3 (highest)
    # BB = byte 2
    # CC = byte 1
    # DD = byte 0 (lowest)
    # active is byte 1, nr_compressors is byte 0, nr_dryers is byte 2
    raw_map = {"311301": "02010102"}

    result = decode_point(point, raw_map, english_language_map)

    assert result["raw"] == "02010102"
    assert result["nr_compressors"] == 2  # byte 0
    assert result["active"] is True  # byte 1 == 1
    assert result["nr_dryers"] == 1  # byte 2


def test_decode_unsupported_family(english_language_map):
    """Test decoding unsupported family (should just return raw)."""
    point = {
        "family": "unknown_family",
        "id": "unknown:test",
        "live_selectors": [{"index": 0x3000, "subindex": 1}],
    }

    raw_map = {"300001": "12345678"}

    result = decode_point(point, raw_map, english_language_map)

    assert result["raw"] == "12345678"


def test_catalog_to_dict_omits_points_by_id():
    """Test that to_dict() serializes families/family_counts but not the derived points_by_id."""
    catalog = Catalog(
        discovered_at="2026-01-01T00:00:00Z",
        families={"analog_inputs": [{"id": "analog_inputs:test", "family": "analog_inputs"}]},
        family_counts={"analog_inputs": 1},
        points_by_id={"analog_inputs:test": {"id": "analog_inputs:test", "family": "analog_inputs"}},
    )

    data = catalog.to_dict()

    assert data == {
        "discovered_at": "2026-01-01T00:00:00Z",
        "families": {"analog_inputs": [{"id": "analog_inputs:test", "family": "analog_inputs"}]},
        "family_counts": {"analog_inputs": 1},
    }
    assert "points_by_id" not in data


def test_catalog_from_dict_rebuilds_points_by_id():
    """Test that from_dict() reconstructs points_by_id from families."""
    data = {
        "discovered_at": "2026-01-01T00:00:00Z",
        "families": {
            "analog_inputs": [{"id": "analog_inputs:a", "family": "analog_inputs"}],
            "counters": [{"id": "counters:b", "family": "counters"}],
        },
        "family_counts": {"analog_inputs": 1, "counters": 1},
    }

    catalog = Catalog.from_dict(data)

    assert catalog.discovered_at == "2026-01-01T00:00:00Z"
    assert catalog.family_counts == {"analog_inputs": 1, "counters": 1}
    assert set(catalog.points_by_id) == {"analog_inputs:a", "counters:b"}
    assert catalog.points_by_id["analog_inputs:a"]["family"] == "analog_inputs"


def test_catalog_to_dict_from_dict_round_trip():
    """Test that from_dict(to_dict(catalog)) reproduces an equivalent catalog."""
    original = Catalog(
        discovered_at="2026-01-01T00:00:00Z",
        families={"digital_inputs": [{"id": "digital_inputs:x", "family": "digital_inputs"}]},
        family_counts={"digital_inputs": 1},
        points_by_id={"digital_inputs:x": {"id": "digital_inputs:x", "family": "digital_inputs"}},
    )

    restored = Catalog.from_dict(original.to_dict())

    assert restored.discovered_at == original.discovered_at
    assert restored.families == original.families
    assert restored.family_counts == original.family_counts
    assert restored.points_by_id == original.points_by_id

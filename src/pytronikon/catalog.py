"""Catalog discovery and point decoding for Elektronikon controllers."""

import re
from dataclasses import dataclass, field
from typing import Any

from pytronikon.codec import Selector, format_selector, read_byte, read_int16, read_uint16, read_uint32
from pytronikon.protocol import ElektronikonTransport

# Analog input type normalization
ANALOG_INPUT_TYPES = {
    0: {"unit": "bar", "normalize": lambda v: v / 1000},
    1: {"unit": "°C", "normalize": lambda v: v / 10},
    9: {"unit": "bar", "normalize": lambda v: v / 100},
    10: {"unit": "%", "normalize": lambda v: v},
    19: {"unit": "kW", "normalize": lambda v: v / 10},
}

# Counter unit normalization
COUNTER_UNITS = {
    0: {"unit": "hours", "normalize": lambda v: v // 3600},
    1: {"unit": "count", "normalize": lambda v: v},
    2: {"unit": "1000m3", "normalize": lambda v: v},
    3: {"unit": "%", "normalize": lambda v: v},
    4: {"unit": "kW", "normalize": lambda v: v},
    6: {"unit": "kWh", "normalize": lambda v: v},
    7: {"unit": "hh:mm:ss", "normalize": lambda v: v},
}


def _selector_map(results: list) -> dict[str, str]:
    """Create a map from selector key to raw value."""
    return {result.key: result.raw for result in results}


def _mpl_label(language_map: dict[str, str], mpl: int) -> str | None:
    """Get the MPL label from the language map."""
    return language_map.get(f"MPL_{mpl}")


def _machine_state_label(language_map: dict[str, str], state: int) -> str | None:
    """Get the machine state label from the language map."""
    return language_map.get(f"MSTATE_{state}")


def _slugify(label: str | None) -> str:
    """Convert a label to a slug."""
    if label is None:
        label = "point"
    s = str(label).lower()
    s = re.sub(r"[^a-z0-9]+", "-", s)
    s = re.sub(r"(^-|-$)", "", s)
    return s or "point"


def _assign_point_ids(family: str, points: list[dict]) -> list[dict]:
    """Assign unique IDs to points in a family."""
    counts: dict[str, int] = {}
    result = []
    for point in points:
        base = _slugify(point.get("label") or f"rtd-{point.get('rtd_si', point.get('subindex', point.get('index')))}")
        seen = counts.get(base, 0) + 1
        counts[base] = seen
        point_id = f"{family}:{base}" if seen == 1 else f"{family}:{base}-{seen}"
        point["id"] = point_id
        result.append(point)
    return result


def _discover_analog_inputs(transport: ElektronikonTransport, language_map: dict[str, str]) -> list[dict]:
    """Discover analog input points."""
    selectors = []
    for index in range(0x2010, 0x2090):
        selectors.extend([
            Selector(key=format_selector(index, 1), index=index, subindex=1),
            Selector(key=format_selector(index, 4), index=index, subindex=4),
            Selector(key=format_selector(index, 6), index=index, subindex=6),
        ])

    results = transport.query_selectors(selectors)
    raw_map = _selector_map(results)
    points = []

    for index in range(0x2010, 0x2090):
        raw = raw_map.get(format_selector(index, 1))
        if raw and raw != "X" and read_byte(raw, 0) != 0:
            precision_raw = raw_map.get(format_selector(index, 4))
            pressure_measurement_raw = raw_map.get(format_selector(index, 6))
            points.append({
                "family": "analog_inputs",
                "index": index,
                "rtd_si": index - 0x2010 + 1,
                "mpl": read_uint16(raw, 1),
                "label": _mpl_label(language_map, read_uint16(raw, 1)),
                "input_type": read_byte(raw, 1),
                "display_precision": read_byte(precision_raw, 3) if precision_raw and precision_raw != "X" else None,
                "pressure_measurement": read_byte(pressure_measurement_raw, 2) if pressure_measurement_raw and pressure_measurement_raw != "X" else None,
                "live_selectors": [
                    {"index": 0x3002, "subindex": index - 0x2010 + 1, "selector": format_selector(0x3002, index - 0x2010 + 1)}
                ],
            })

    return _assign_point_ids("analog_inputs", points)


def _discover_calculated_analog_inputs(transport: ElektronikonTransport, language_map: dict[str, str]) -> list[dict]:
    """Discover calculated analog input points."""
    selectors = []
    for index in range(0x2090, 0x20B0):
        selectors.extend([
            Selector(key=format_selector(index, 1), index=index, subindex=1),
            Selector(key=format_selector(index, 3), index=index, subindex=3),
        ])

    results = transport.query_selectors(selectors)
    raw_map = _selector_map(results)
    points = []

    for index in range(0x2090, 0x20B0):
        raw = raw_map.get(format_selector(index, 1))
        if raw and raw != "X" and read_byte(raw, 0) != 0:
            precision_raw = raw_map.get(format_selector(index, 3))
            points.append({
                "family": "calculated_analog_inputs",
                "index": index,
                "rtd_si": index - 0x2090 + 1,
                "mpl": read_uint16(raw, 1),
                "label": _mpl_label(language_map, read_uint16(raw, 1)),
                "input_type": read_byte(raw, 1),
                "display_precision": read_byte(precision_raw, 3) if precision_raw and precision_raw != "X" else None,
                "live_selectors": [
                    {"index": 0x3004, "subindex": index - 0x2090 + 1, "selector": format_selector(0x3004, index - 0x2090 + 1)}
                ],
            })

    return _assign_point_ids("calculated_analog_inputs", points)


def _discover_digital_inputs(transport: ElektronikonTransport, language_map: dict[str, str]) -> list[dict]:
    """Discover digital input points."""
    selectors = [
        Selector(key=format_selector(index, 1), index=index, subindex=1)
        for index in range(0x20B0, 0x2100)
    ]

    results = transport.query_selectors(selectors)
    raw_map = _selector_map(results)
    points = []

    for index in range(0x20B0, 0x2100):
        raw = raw_map.get(format_selector(index, 1))
        if raw and raw != "X" and read_byte(raw, 0) != 0:
            mpl = read_uint16(raw, 1)
            points.append({
                "family": "digital_inputs",
                "index": index,
                "rtd_si": index - 0x20B0 + 1,
                "mpl": mpl,
                "label": _mpl_label(language_map, mpl),
                "live_selectors": [
                    {"index": 0x3005, "subindex": index - 0x20B0 + 1, "selector": format_selector(0x3005, index - 0x20B0 + 1)}
                ],
            })

    return _assign_point_ids("digital_inputs", points)


def _discover_digital_outputs(transport: ElektronikonTransport, language_map: dict[str, str]) -> list[dict]:
    """Discover digital output points."""
    selectors = [
        Selector(key=format_selector(index, 1), index=index, subindex=1)
        for index in range(0x2100, 0x2150)
    ]

    results = transport.query_selectors(selectors)
    raw_map = _selector_map(results)
    points = []

    for index in range(0x2100, 0x2150):
        raw = raw_map.get(format_selector(index, 1))
        if raw and raw != "X" and read_byte(raw, 0) != 0:
            mpl = read_uint16(raw, 1)
            points.append({
                "family": "digital_outputs",
                "index": index,
                "rtd_si": index - 0x2100 + 1,
                "mpl": mpl,
                "label": _mpl_label(language_map, mpl),
                "live_selectors": [
                    {"index": 0x3006, "subindex": index - 0x2100 + 1, "selector": format_selector(0x3006, index - 0x2100 + 1)}
                ],
            })

    return _assign_point_ids("digital_outputs", points)


def _discover_analog_outputs(transport: ElektronikonTransport, language_map: dict[str, str]) -> list[dict]:
    """Discover analog output points."""
    selectors = []
    for index in range(0x2150, 0x2170):
        selectors.extend([
            Selector(key=format_selector(index, 1), index=index, subindex=1),
            Selector(key=format_selector(index, 3), index=index, subindex=3),
        ])

    results = transport.query_selectors(selectors)
    raw_map = _selector_map(results)
    points = []

    for index in range(0x2150, 0x2170):
        raw = raw_map.get(format_selector(index, 1))
        if raw and raw != "X" and read_byte(raw, 0) != 0:
            precision_raw = raw_map.get(format_selector(index, 3))
            mpl = read_uint16(raw, 1)
            points.append({
                "family": "analog_outputs",
                "index": index,
                "rtd_si": index - 0x2150 + 1,
                "mpl": mpl,
                "label": _mpl_label(language_map, mpl),
                "output_type": read_byte(raw, 1),
                "display_precision": read_byte(precision_raw, 3) if precision_raw and precision_raw != "X" else None,
                "live_selectors": [
                    {"index": 0x3006, "subindex": index - 0x2150 + 1}
                ],
            })

    return _assign_point_ids("analog_outputs", points)


def _discover_counters(transport: ElektronikonTransport, language_map: dict[str, str]) -> list[dict]:
    """Discover counter points."""
    selectors = [
        Selector(key=format_selector(0x2607, subindex), index=0x2607, subindex=subindex)
        for subindex in range(1, 256)
    ]

    results = transport.query_selectors(selectors)
    raw_map = _selector_map(results)
    points = []

    for subindex in range(1, 256):
        raw = raw_map.get(format_selector(0x2607, subindex))
        if raw and raw != "X" and read_byte(raw, 0) != 0:
            mpl = read_uint16(raw, 1)
            points.append({
                "family": "counters",
                "index": 0x2607,
                "rtd_si": subindex,
                "mpl": mpl,
                "label": _mpl_label(language_map, mpl),
                "counter_unit": read_byte(raw, 1),
                "live_selectors": [
                    {"index": 0x3008, "subindex": subindex, "selector": format_selector(0x3008, subindex)}
                ],
            })

    return _assign_point_ids("counters", points)


def _discover_special_protections(transport: ElektronikonTransport, language_map: dict[str, str]) -> list[dict]:
    """Discover special protection points."""
    selectors = [
        Selector(key=format_selector(index, 1), index=index, subindex=1)
        for index in range(0x2300, 0x247F)
    ]

    results = transport.query_selectors(selectors)
    raw_map = _selector_map(results)
    points = []

    for index in range(0x2300, 0x247F):
        raw = raw_map.get(format_selector(index, 1))
        if raw and raw != "X" and read_byte(raw, 0) != 0:
            mpl = read_uint16(raw, 1)
            points.append({
                "family": "special_protections",
                "index": index,
                "rtd_si": index - 0x2300 + 1,
                "mpl": mpl,
                "label": _mpl_label(language_map, mpl),
                "live_selectors": [
                    {"index": 0x3009, "subindex": index - 0x2300 + 1, "selector": format_selector(0x3009, index - 0x2300 + 1)}
                ],
            })

    return _assign_point_ids("special_protections", points)


def _discover_spm(transport: ElektronikonTransport, language_map: dict[str, str]) -> list[dict]:
    """Discover SPM points."""
    selectors = [
        Selector(key=format_selector(index, 1), index=index, subindex=1)
        for index in range(0x2560, 0x2570)
    ]

    results = transport.query_selectors(selectors)
    raw_map = _selector_map(results)
    points = []

    for index in range(0x2560, 0x2570):
        raw = raw_map.get(format_selector(index, 1))
        if raw and raw != "X" and read_byte(raw, 0) != 0:
            mpl = read_uint16(raw, 1)
            rtd_si = 2 * (index - 0x2560) + 1
            points.append({
                "family": "spm",
                "index": index,
                "rtd_si": rtd_si,
                "mpl": mpl,
                "label": _mpl_label(language_map, mpl),
                "live_selectors": [
                    {"index": 0x3015, "subindex": rtd_si},
                    {"index": 0x3015, "subindex": rtd_si + 1},
                ],
            })

    return _assign_point_ids("spm", points)


def _discover_service_plan(transport: ElektronikonTransport) -> list[dict]:
    """Discover service plan points."""
    selectors = [
        Selector(key=format_selector(0x2602, subindex), index=0x2602, subindex=subindex)
        for subindex in range(1, 21)
    ]

    results = transport.query_selectors(selectors)
    raw_map = _selector_map(results)
    points = []

    for subindex in range(1, 21):
        raw = raw_map.get(format_selector(0x2602, subindex))
        if raw and raw != "X" and read_uint32(raw) != 0:
            rtd_si = 16 + subindex // 2 if subindex % 2 == 0 else 6 + (subindex - 1) // 2
            level = (subindex + 1) // 2
            kind = "real_time_hours" if subindex % 2 == 0 else "running_hours"
            points.append({
                "family": "service_plan",
                "index": 0x2602,
                "subindex": subindex,
                "label": f"Service level {level} {kind}",
                "static_value": read_uint32(raw),
                "rtd_si": rtd_si,
                "level": level,
                "kind": kind,
                "live_selectors": [
                    {"index": 0x3009, "subindex": 1},
                    {"index": 0x3009, "subindex": rtd_si},
                ],
            })

    return _assign_point_ids("service_plan", points)


def _discover_machine_state(transport: ElektronikonTransport, language_map: dict[str, str]) -> list[dict]:
    """Discover machine state point."""
    meta = _query_one(transport, 0x2601, 1)[0]
    count = 1
    if meta.raw != "X":
        regulation_type = read_byte(meta.raw, 0)
        machine_type = read_byte(meta.raw, 1)
        if regulation_type in (79, 84):
            if machine_type == 39:
                count = 2
            elif machine_type == 40:
                count = 3

    return [{
        "id": "machine_state:current",
        "family": "machine_state",
        "label": "Machine State",
        "count": count,
        "live_selectors": (
            [{"index": 0x3001, "subindex": 8, "selector": format_selector(0x3001, 8)}] +
            ([{"index": 0x3001, "subindex": 9, "selector": format_selector(0x3001, 9)}] if count > 1 else [])
        ),
        "state_labels": language_map,
    }]


def _discover_converters(transport: ElektronikonTransport, language_map: dict[str, str]) -> list[dict]:
    """Discover converter points."""
    selectors = [Selector(key=format_selector(0x2601, 1), index=0x2601, subindex=1)]
    for index in range(0x2681, 0x2689):
        selectors.extend([
            Selector(key=format_selector(index, 1), index=index, subindex=1),
            Selector(key=format_selector(index, 7), index=index, subindex=7),
            Selector(key=format_selector(index, 8), index=index, subindex=8),
        ])

    results = transport.query_selectors(selectors)
    raw_map = _selector_map(results)
    points = []

    for index in range(0x2681, 0x2689):
        raw = raw_map.get(format_selector(index, 1))
        if raw and raw != "X" and read_byte(raw, 0) != 0:
            mpl = read_uint16(raw, 1)
            rtd_si = index - 0x2681 + 1
            points.append({
                "family": "converters",
                "index": index,
                "rtd_si": rtd_si,
                "mpl": mpl,
                "label": _mpl_label(language_map, mpl),
                "live_selectors": [
                    {"index": 0x3020 + rtd_si, "subindex": 1},
                    {"index": 0x3020 + rtd_si, "subindex": 5},
                ],
            })

    return _assign_point_ids("converters", points)


def _discover_internal_data(transport: ElektronikonTransport, language_map: dict[str, str]) -> list[dict]:
    """Discover internal data points."""
    selectors = [
        Selector(key=format_selector(0x2619, subindex), index=0x2619, subindex=subindex)
        for subindex in range(1, 256)
    ]

    results = transport.query_selectors(selectors)
    raw_map = _selector_map(results)
    points = []

    for subindex in range(1, 256):
        raw = raw_map.get(format_selector(0x2619, subindex))
        if raw and raw != "X" and read_byte(raw, 0) != 0:
            mpl = read_uint16(raw, 1)
            points.append({
                "family": "internal_data",
                "index": 0x2619,
                "rtd_si": subindex,
                "mpl": mpl,
                "label": _mpl_label(language_map, mpl),
                "type": read_byte(raw, 1),
                "live_selectors": [
                    {"index": 0x3014, "subindex": subindex}
                ],
            })

    return _assign_point_ids("internal_data", points)


def _discover_date_format(transport: ElektronikonTransport) -> list[dict]:
    """Discover date format preference point."""
    return [{
        "id": "preferences:date_format",
        "family": "preferences",
        "label": "Date Format Preference",
        "live_selectors": [
            {"index": 0x2615, "subindex": 1, "selector": format_selector(0x2615, 1)}
        ],
    }]


def _discover_es(transport: ElektronikonTransport) -> list[dict]:
    """Discover ES controller point."""
    return [{
        "id": "es:controller",
        "family": "es",
        "label": "ES Controller",
        "live_selectors": [
            {"index": 0x3113, "subindex": 1, "selector": format_selector(0x3113, 1)},
            {"index": 0x3113, "subindex": 3, "selector": format_selector(0x3113, 3)},
            {"index": 0x3113, "subindex": 4, "selector": format_selector(0x3113, 4)},
            {"index": 0x3113, "subindex": 5, "selector": format_selector(0x3113, 5)},
        ],
    }]


def _query_one(transport: ElektronikonTransport, index: int, subindex: int):
    """Query a single selector."""
    return transport.query_selectors([Selector(key=format_selector(index, subindex), index=index, subindex=subindex)])


@dataclass(slots=True)
class Catalog:
    """A complete catalog of points from a controller."""

    discovered_at: str
    families: dict[str, list[dict]]
    family_counts: dict[str, int]
    points_by_id: dict[str, dict]

    def to_dict(self) -> dict:
        """Serialize the catalog to a plain, JSON-able dict.

        Returns:
            A dict with keys "discovered_at", "families", and "family_counts".
            "points_by_id" is omitted since it's derivable from "families".
        """
        return {
            "discovered_at": self.discovered_at,
            "families": self.families,
            "family_counts": self.family_counts,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "Catalog":
        """Rebuild a Catalog from a dict produced by to_dict().

        Args:
            data: A dict with "discovered_at", "families", and "family_counts" keys.

        Returns:
            A Catalog with points_by_id rebuilt from families.
        """
        families = data["families"]
        points_by_id = {
            point["id"]: point
            for points in families.values()
            for point in points
        }
        return cls(
            discovered_at=data["discovered_at"],
            families=families,
            family_counts=data["family_counts"],
            points_by_id=points_by_id,
        )


def discover_catalog(transport: ElektronikonTransport, language_map: dict[str, str]) -> Catalog:
    """Discover all available points on the controller.

    Args:
        transport: The HTTP transport.
        language_map: A dictionary of language strings.

    Returns:
        A Catalog object containing all discovered families and points.
    """
    from datetime import datetime, UTC

    families = {
        "analog_inputs": _discover_analog_inputs(transport, language_map),
        "calculated_analog_inputs": _discover_calculated_analog_inputs(transport, language_map),
        "digital_inputs": _discover_digital_inputs(transport, language_map),
        "digital_outputs": _discover_digital_outputs(transport, language_map),
        "analog_outputs": _discover_analog_outputs(transport, language_map),
        "counters": _discover_counters(transport, language_map),
        "special_protections": _discover_special_protections(transport, language_map),
        "spm": _discover_spm(transport, language_map),
        "service_plan": _discover_service_plan(transport),
        "machine_state": _discover_machine_state(transport, language_map),
        "converters": _discover_converters(transport, language_map),
        "internal_data": _discover_internal_data(transport, language_map),
        "preferences": _discover_date_format(transport),
        "es": _discover_es(transport),
    }

    points_by_id = {}
    for points in families.values():
        for point in points:
            points_by_id[point["id"]] = point

    family_counts = {family: len(points) for family, points in families.items()}

    return Catalog(
        discovered_at=datetime.now(UTC).isoformat(),
        families=families,
        family_counts=family_counts,
        points_by_id=points_by_id,
    )


def decode_point(point: dict, raw_map: dict[str, str], language_map: dict[str, str]) -> dict[str, Any]:
    """Decode a point using live selector data.

    Args:
        point: The point definition.
        raw_map: A dictionary from selector key to raw 8-hex value.
        language_map: A dictionary of language strings.

    Returns:
        A decoded point with raw and interpreted values.
    """
    live_selectors = point.get("live_selectors", [])
    primary_raw = "X"
    if live_selectors:
        primary_raw = raw_map.get(
            format_selector(live_selectors[0]["index"], live_selectors[0]["subindex"]),
            "X",
        )

    family = point.get("family")
    result = {**point}

    if family == "analog_inputs" or family == "calculated_analog_inputs":
        raw_value = None if primary_raw == "X" else read_int16(primary_raw, 1)
        normalized = None
        if raw_value is not None:
            input_type = point.get("input_type", 0)
            formatter = ANALOG_INPUT_TYPES.get(input_type)
            if formatter:
                normalized = {
                    "value": formatter["normalize"](raw_value),
                    "unit": formatter["unit"],
                }
            else:
                normalized = {"value": raw_value, "unit": f"type:{input_type}"}
        result["raw"] = primary_raw
        result["status"] = None if primary_raw == "X" else read_uint16(primary_raw, 0)
        result["raw_value"] = raw_value
        result["normalized"] = normalized

    elif family == "digital_inputs" or family == "digital_outputs":
        result["raw"] = primary_raw
        result["status"] = None if primary_raw == "X" else read_uint16(primary_raw, 0)
        result["value"] = None if primary_raw == "X" else read_uint16(primary_raw, 1)

    elif family == "analog_outputs":
        result["raw"] = primary_raw
        result["status"] = None if primary_raw == "X" else read_uint16(primary_raw, 0)
        result["raw_value"] = None if primary_raw == "X" else read_int16(primary_raw, 1)

    elif family == "counters":
        raw_value = None if primary_raw == "X" else read_uint32(primary_raw)
        normalized = None
        if raw_value is not None:
            counter_unit = point.get("counter_unit", 0)
            formatter = COUNTER_UNITS.get(counter_unit)
            if formatter:
                normalized = {
                    "value": formatter["normalize"](raw_value),
                    "unit": formatter["unit"],
                }
            else:
                normalized = {"value": raw_value, "unit": f"unit:{counter_unit}"}
        result["raw"] = primary_raw
        result["raw_value"] = raw_value
        result["normalized"] = normalized

    elif family == "special_protections":
        result["raw"] = primary_raw
        result["status"] = None if primary_raw == "X" else read_uint16(primary_raw, 0)

    elif family == "machine_state":
        secondary_selector = live_selectors[1] if len(live_selectors) > 1 else None
        secondary_raw = "X"
        if secondary_selector:
            secondary_raw = raw_map.get(
                format_selector(secondary_selector["index"], secondary_selector["subindex"]),
                "X",
            )
        primary_state = None if primary_raw == "X" else read_int16(primary_raw, 0)
        secondary_state1 = None if secondary_raw == "X" else read_uint16(secondary_raw, 0)
        secondary_state2 = None if secondary_raw == "X" else read_uint16(secondary_raw, 1)
        result["raw"] = primary_raw
        result["raw_secondary"] = None if secondary_raw == "X" else secondary_raw
        result["primary_state"] = primary_state
        result["primary_label"] = None if primary_state is None else _machine_state_label(language_map, primary_state)
        result["secondary_state1"] = secondary_state1
        result["secondary_label1"] = None if secondary_state1 is None else _machine_state_label(language_map, secondary_state1)
        result["secondary_state2"] = secondary_state2
        result["secondary_label2"] = None if secondary_state2 is None else _machine_state_label(language_map, secondary_state2)

    elif family == "converters":
        secondary_selector = live_selectors[1] if len(live_selectors) > 1 else None
        secondary_raw = "X"
        if secondary_selector:
            secondary_raw = raw_map.get(
                format_selector(secondary_selector["index"], secondary_selector["subindex"]),
                "X",
            )
        result["raw"] = primary_raw
        result["raw_secondary"] = None if secondary_raw == "X" else secondary_raw

    elif family == "internal_data":
        result["raw"] = primary_raw
        result["value"] = None if primary_raw == "X" else read_uint32(primary_raw)

    elif family == "service_plan":
        next_mask_selector = live_selectors[0] if live_selectors else None
        current_selector = live_selectors[1] if len(live_selectors) > 1 else None
        next_mask_raw = "X"
        current_raw = "X"
        if next_mask_selector:
            next_mask_raw = raw_map.get(
                format_selector(next_mask_selector["index"], next_mask_selector["subindex"]),
                "X",
            )
        if current_selector:
            current_raw = raw_map.get(
                format_selector(current_selector["index"], current_selector["subindex"]),
                "X",
            )
        mask = None if next_mask_raw == "X" else read_uint32(next_mask_raw)
        is_next = None
        if mask is not None:
            level = point.get("level", 1)
            is_next = ((mask >> (level - 1)) & 1) == 1
        result["raw"] = current_raw
        result["next_mask_raw"] = next_mask_raw
        result["current_value"] = None if current_raw == "X" else read_uint32(current_raw)
        result["is_next"] = is_next

    elif family == "spm":
        secondary_selector = live_selectors[1] if len(live_selectors) > 1 else None
        secondary_raw = "X"
        if secondary_selector:
            secondary_raw = raw_map.get(
                format_selector(secondary_selector["index"], secondary_selector["subindex"]),
                "X",
            )
        result["raw"] = primary_raw
        result["raw_secondary"] = None if secondary_raw == "X" else secondary_raw

    elif family == "preferences":
        result["raw"] = primary_raw
        result["type"] = None if primary_raw == "X" else read_byte(primary_raw, 0)

    elif family == "es":
        result["raw"] = primary_raw
        result["active"] = None if primary_raw == "X" else read_byte(primary_raw, 1) == 1
        result["nr_compressors"] = None if primary_raw == "X" else read_byte(primary_raw, 0)
        result["nr_dryers"] = None if primary_raw == "X" else read_byte(primary_raw, 2)
        state_selector = live_selectors[1] if len(live_selectors) > 1 else None
        state_raw = "X"
        if state_selector:
            state_raw = raw_map.get(
                format_selector(state_selector["index"], state_selector["subindex"]),
                "X",
            )
        result["state"] = None if state_raw == "X" else read_uint16(state_raw, 0)

    else:
        result["raw"] = primary_raw

    return result

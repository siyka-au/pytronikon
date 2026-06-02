"""Command-line interface for pytronikon."""

import argparse
import json
import os
import sys
from dataclasses import asdict
from typing import Any

from pytronikon.client import ElektronikonClient
from pytronikon.codec import Selector, read_int16, read_uint16, read_uint32
from pytronikon.errors import ElektronikonError


def _json_default(obj: Any) -> Any:
    """Custom JSON serializer for special types."""
    if isinstance(obj, Selector):
        return {"index": obj.index, "subindex": obj.subindex}
    if isinstance(obj, ElektronikonError):
        return obj.to_dict()
    if hasattr(obj, "__dataclass_fields__"):
        return asdict(obj)
    raise TypeError(f"Object of type {type(obj).__name__} is not JSON serializable")


def _load_catalog_from_file(filepath: str) -> dict[str, Any]:
    """Load catalog JSON from file.

    Args:
        filepath: Path to the catalog JSON file.

    Returns:
        Parsed catalog dictionary.
    """
    with open(filepath, "r", encoding="utf-8") as f:
        return json.load(f)


def _extract_selectors_from_catalog(
    catalog_data: dict[str, Any], 
    families: list[str] | None = None, 
    point_ids: list[str] | None = None
) -> list[str]:
    """Extract selector keys from catalog based on families or point IDs.

    Args:
        catalog_data: Catalog loaded from JSON.
        families: Family names to query (e.g., ["analog_inputs"]).
        point_ids: Point IDs to query. Supports both full IDs (family:label) and suffixes (label).

    Returns:
        List of selector keys (e.g., ["300201", "300202"]).
    """
    selectors = []
    points_list = catalog_data.get("points", {})

    if families:
        # Get all points in specified families
        for family_name in families:
            if family_name in points_list:
                for point in points_list[family_name]:
                    for live_sel in point.get("live_selectors", []):
                        key = f"{live_sel['index']:X}{live_sel['subindex']:02X}"
                        if key not in selectors:
                            selectors.append(key)

    elif point_ids:
        # Match points by ID (full or suffix)
        for family_points in points_list.values():
            for point in family_points:
                point_id = point.get("id", "")
                point_label = point.get("label", "")
                # Match by full ID or suffix
                if any(
                    point_id == pid or 
                    point_id.endswith(f":{pid}") or 
                    point_label and point_label.lower().replace(" ", "-") == pid.lower()
                    for pid in point_ids
                ):
                    for live_sel in point.get("live_selectors", []):
                        key = f"{live_sel['index']:X}{live_sel['subindex']:02X}"
                        if key not in selectors:
                            selectors.append(key)

    return selectors


def _enrich_results_with_catalog(results: dict[str, Any], catalog_data: dict[str, Any]) -> dict[str, Any]:
    """Enrich query results with metadata from a catalog.

    Args:
        results: Query results with direct_results.
        catalog_data: Catalog loaded from JSON.

    Returns:
        Results with enriched direct_results.
    """
    # Build a map from selector key to points
    selector_to_points: dict[str, list[dict]] = {}

    for points_list in catalog_data.get("points", {}).values():
        for point in points_list:
            for live_sel in point.get("live_selectors", []):
                key = f"{live_sel['index']:04X}{live_sel['subindex']:02X}"
                if key not in selector_to_points:
                    selector_to_points[key] = []
                selector_to_points[key].append(point)

    # Unit mappings (from catalog.py)
    ANALOG_INPUT_TYPES = {
        0: {"unit": "bar", "normalize": lambda v: v / 1000},
        1: {"unit": "°C", "normalize": lambda v: v / 10},
        9: {"unit": "bar", "normalize": lambda v: v / 100},
        10: {"unit": "%", "normalize": lambda v: v},
        19: {"unit": "kW", "normalize": lambda v: v / 10},
    }
    COUNTER_UNITS = {
        0: {"unit": "hours", "normalize": lambda v: v},
        1: {"unit": "count", "normalize": lambda v: v},
        2: {"unit": "kWh", "normalize": lambda v: v / 10},
    }

    def decode_raw_value(raw: str, family: str, point: dict) -> dict[str, Any] | None:
        """Decode a raw value based on family and point metadata."""
        if raw == "X" or not raw:
            return None

        decoded = {}

        if family in ("analog_inputs", "calculated_analog_inputs"):
            try:
                raw_value = read_int16(raw, 1)
                input_type = point.get("input_type", 0)
                formatter = ANALOG_INPUT_TYPES.get(input_type)
                if formatter:
                    normalized_value = formatter["normalize"](raw_value)
                    decoded["value"] = normalized_value
                    decoded["unit"] = formatter["unit"]
                else:
                    decoded["value"] = raw_value
                    decoded["unit"] = f"type_{input_type}"
                decoded["raw_value"] = raw_value
                decoded["status"] = read_uint16(raw, 0)
            except Exception:
                pass

        elif family in ("digital_inputs", "digital_outputs"):
            try:
                decoded["value"] = read_uint16(raw, 1)
                decoded["status"] = read_uint16(raw, 0)
            except Exception:
                pass

        elif family == "analog_outputs":
            try:
                decoded["raw_value"] = read_int16(raw, 1)
                decoded["status"] = read_uint16(raw, 0)
            except Exception:
                pass

        elif family == "counters":
            try:
                raw_value = read_uint32(raw)
                counter_unit = point.get("counter_unit", 0)
                formatter = COUNTER_UNITS.get(counter_unit)
                if formatter:
                    normalized_value = formatter["normalize"](raw_value)
                    decoded["value"] = normalized_value
                    decoded["unit"] = formatter["unit"]
                else:
                    decoded["value"] = raw_value
                    decoded["unit"] = f"unit_{counter_unit}"
                decoded["raw_value"] = raw_value
            except Exception:
                pass

        elif family == "special_protections":
            try:
                decoded["status"] = read_uint16(raw, 0)
            except Exception:
                pass

        elif family == "internal_data":
            try:
                decoded["value"] = read_uint32(raw)
            except Exception:
                pass

        return decoded if decoded else None

    # Enrich direct_results
    enriched_results = results.copy()
    enriched_direct = []

    for direct in results.get("direct_results", []):
        index = direct.get("index")
        subindex = direct.get("subindex")

        if index is not None and subindex is not None:
            key = f"{index:04X}{subindex:02X}"
            if key in selector_to_points:
                point = selector_to_points[key][0]  # Use first matching point
                raw = direct.get("raw")
                family = point.get("family")
                decoded = decode_raw_value(raw, family, point)

                direct = {
                    **direct,
                    "point_id": point.get("id"),
                    "point_label": point.get("label"),
                    "point_family": family,
                    "point_unit": point.get("unit"),
                }
                if decoded:
                    direct["decoded"] = decoded

        enriched_direct.append(direct)

    enriched_results["direct_results"] = enriched_direct
    enriched_results["catalog_source"] = catalog_data.get("discovered_at")
    return enriched_results


def _format_point_info(point: dict) -> dict[str, Any]:
    """Format point information for display.

    Args:
        point: The point dictionary from the catalog.

    Returns:
        A formatted dictionary with essential metadata.
    """
    family = point.get("family", "unknown")
    info: dict[str, Any] = {
        "id": point.get("id", "unknown"),
        "label": point.get("label", "Unlabeled"),
        "family": family,
    }

    # Add unit information based on family
    if family in ("analog_inputs", "calculated_analog_inputs"):
        input_type = point.get("input_type", 0)
        units_map = {0: "bar", 1: "°C", 9: "bar", 10: "%", 19: "kW"}
        info["unit"] = units_map.get(input_type, f"type_{input_type}")
        info["input_type"] = input_type
        if point.get("display_precision") is not None:
            info["display_precision"] = point.get("display_precision")

    elif family == "counters":
        counter_unit = point.get("counter_unit", 0)
        units_map = {0: "hours", 1: "count", 2: "kWh"}
        info["unit"] = units_map.get(counter_unit, f"unit_{counter_unit}")
        if point.get("counter_unit") is not None:
            info["counter_unit"] = counter_unit

    elif family in ("digital_inputs", "digital_outputs"):
        info["type"] = "digital"

    # Add live selector information if available
    if "live_selectors" in point:
        info["live_selectors"] = point.get("live_selectors")

    # Add index for reference
    if "index" in point:
        info["index"] = point["index"]

    return info


def main(argv: list[str] | None = None) -> int:
    """Main CLI entry point.

    Args:
        argv: Optional command-line arguments (for testing).

    Returns:
        Exit code (0 on success, 1 on error).
    """
    parser = argparse.ArgumentParser(
        description="Query Atlas Copco Elektronikon MkV controllers via mkv.cgi"
    )
    subparsers = parser.add_subparsers(dest="command", help="Command to run")

    # Common arguments
    def add_common_args(p: argparse.ArgumentParser) -> None:
        p.add_argument(
            "--host",
            default=os.environ.get("ELEKTRONIKON_HOST", "192.168.100.100"),
            help="Controller host (default: 192.168.100.100)",
        )

    # Query command
    query_parser = subparsers.add_parser("query", help="Query values from the controller")
    add_common_args(query_parser)
    query_parser.add_argument(
        "--selector",
        action="append",
        dest="selectors",
        help="Selector(s) as comma-separated hex (e.g., 300201,300301)",
    )
    query_parser.add_argument(
        "--point",
        action="append",
        dest="points",
        help="Point ID(s) as comma-separated values (e.g., analog_inputs:compressor_outlet)",
    )
    query_parser.add_argument(
        "--point_ids",
        action="append",
        dest="point_ids",
        help="When using --catalog: point ID suffixes or labels (e.g., compressor-outlet,element-outlet)",
    )
    query_parser.add_argument(
        "--family",
        action="append",
        dest="families",
        help="Family name(s) to query (e.g., digital_outputs)",
    )
    query_parser.add_argument(
        "--all",
        action="store_true",
        dest="all_discovered",
        help="Query all discovered points (requires discover first)",
    )
    query_parser.add_argument(
        "--language",
        default="English",
        help="Language for labels (default: English)",
    )
    query_parser.add_argument(
        "--catalog",
        help="Path to catalog JSON file (from 'discover' command) to enrich results",
    )

    # Discover command
    discover_parser = subparsers.add_parser("discover", help="Discover points on the controller")
    add_common_args(discover_parser)
    discover_parser.add_argument(
        "--language",
        default="English",
        help="Language for labels (default: English)",
    )

    args = parser.parse_args(argv)

    if not args.command:
        parser.print_help()
        return 1

    try:
        client = ElektronikonClient(host=args.host)

        if args.command == "query":
            # Parse selector arguments
            selectors = []
            if args.selectors:
                for sel_arg in args.selectors:
                    selectors.extend(s.strip() for s in sel_arg.split(",") if s.strip())

            points = []
            if args.points:
                for pt_arg in args.points:
                    points.extend(p.strip() for p in pt_arg.split(",") if p.strip())

            families = []
            if args.families:
                for fam_arg in args.families:
                    families.extend(f.strip() for f in fam_arg.split(",") if f.strip())

            point_ids = []
            if hasattr(args, "point_ids") and args.point_ids:
                for pid_arg in args.point_ids:
                    point_ids.extend(p.strip() for p in pid_arg.split(",") if p.strip())

            # If catalog is provided, extract selectors from families or point_ids
            if hasattr(args, "catalog") and args.catalog and (families or point_ids):
                catalog_data = _load_catalog_from_file(args.catalog)
                extracted = _extract_selectors_from_catalog(catalog_data, families if families else None, point_ids if point_ids else None)
                selectors.extend(extracted)
                # When using catalog for families/point_ids, don't pass them to client.query
                families = []
                points = []
                point_ids = []

            if not selectors and not points and not families and not args.all_discovered:
                raise ValueError(
                    "query requires at least one of: --selector, --point, --family, --point_ids, or --all"
                )

            result = client.query(
                selectors=selectors if selectors else None,
                points=points if points else None,
                families=families if families else None,
                all_discovered=args.all_discovered,
                language=args.language,
            )

            # Enrich with catalog metadata if provided
            if hasattr(args, "catalog") and args.catalog:
                catalog_data = _load_catalog_from_file(args.catalog)
                result = _enrich_results_with_catalog(result, catalog_data)

            sys.stdout.write(json.dumps(result, indent=2, default=_json_default, ensure_ascii=False))
            sys.stdout.write("\n")
            return 0

        elif args.command == "discover":
            catalog = client.discover(language=args.language)

            # Format points with metadata, organized by family
            points_by_family: dict[str, list[dict]] = {}
            for point in catalog.points_by_id.values():
                family = point.get("family", "unknown")
                if family not in points_by_family:
                    points_by_family[family] = []
                points_by_family[family].append(_format_point_info(point))

            output = {
                "host": args.host,
                "language": args.language,
                "discovered_at": catalog.discovered_at,
                "family_counts": catalog.family_counts,
                "points": points_by_family,
            }

            sys.stdout.write(json.dumps(output, indent=2, default=_json_default, ensure_ascii=False))
            sys.stdout.write("\n")
            return 0

    except ElektronikonError as e:
        sys.stderr.write(json.dumps(e.to_dict(), indent=2, ensure_ascii=False))
        sys.stderr.write("\n")
        return 1
    except Exception as e:
        sys.stderr.write(
            json.dumps({
                "name": e.__class__.__name__,
                "message": str(e),
            }, indent=2, ensure_ascii=False)
        )
        sys.stderr.write("\n")
        return 1

    return 0


if __name__ == "__main__":
    sys.exit(main())

"""High-level client for Elektronikon controllers."""

import os
from typing import Any

from pytronikon.catalog import Catalog, decode_point, discover_catalog
from pytronikon.codec import normalize_selector
from pytronikon.errors import UnknownFamilyError, UnknownPointError, UsageError
from pytronikon.protocol import ElektronikonTransport


class ElektronikonClient:
    """A client for querying Elektronikon controllers."""

    def __init__(
        self,
        host: str | None = None,
        timeout: float = 5.0,
        batch_size: int = 1000,
        transport: ElektronikonTransport | None = None,
    ) -> None:
        """Initialize the client.

        Args:
            host: The controller host. Defaults to ELEKTRONIKON_HOST env var or "192.168.100.100".
            timeout: The request timeout in seconds.
            batch_size: Maximum selectors per request.
            transport: Optional custom transport (for testing).
        """
        if host is None:
            host = os.environ.get("ELEKTRONIKON_HOST", "192.168.100.100")
        
        self.transport = transport or ElektronikonTransport(
            host=host,
            timeout=timeout,
            batch_size=batch_size,
        )
        self._catalog: Catalog | None = None
        self._language_map: dict[str, str] | None = None

    def query_raw(self, selectors: str | list[str]) -> dict[str, Any]:
        """Query raw selector values without discovery.

        Args:
            selectors: One or more selectors (as strings or a list).

        Returns:
            A dict with selector results.
        """
        if isinstance(selectors, str):
            selectors = [selectors]

        normalized = [normalize_selector(s) for s in selectors]
        results = self.transport.query_selectors(normalized)

        return {
            "host": self.transport.host,
            "selector_count": len(results),
            "results": [
                {
                    "selector": r.key,
                    "index": r.index,
                    "subindex": r.subindex,
                    "raw": r.raw,
                }
                for r in results
            ],
        }

    def load_language(self, language: str = "English") -> dict[str, str]:
        """Load language strings from the controller.

        Args:
            language: The language to load (default "English").

        Returns:
            A dict of language key -> value mappings.
        """
        if language == "English" and self._language_map is not None:
            return self._language_map

        text = self.transport.fetch_text(f"/languages/{language}.txt")
        entries = {}
        for line in text.split("\r\n"):
            if not line:
                continue
            if "$$" in line:
                key, value = line.split("$$", 1)
                entries[key] = value

        if language == "English":
            self._language_map = entries

        return entries

    def discover(self, language: str = "English") -> Catalog:
        """Discover all available points on the controller.

        This must be called before using point IDs or family names in query().

        Args:
            language: The language for labels (default "English").

        Returns:
            A Catalog object.
        """
        if self._catalog is not None:
            return self._catalog

        language_map = self.load_language(language)
        self._catalog = discover_catalog(self.transport, language_map)
        return self._catalog

    def load_catalog(self, catalog: Catalog) -> None:
        """Load a previously-discovered catalog without querying the controller.

        Use this to restore a catalog cached from an earlier discover() call
        (e.g. loaded from disk via Catalog.from_dict()), enabling query() by
        point ID, family, or all_discovered without re-running discovery.

        Args:
            catalog: A Catalog, typically produced by an earlier discover()
                call or rebuilt via Catalog.from_dict().
        """
        self._catalog = catalog

    def query(
        self,
        *,
        selectors: list[str] | None = None,
        points: list[str] | None = None,
        families: list[str] | None = None,
        all_discovered: bool = False,
        language: str = "English",
    ) -> dict[str, Any]:
        """Query points, families, or raw selectors.

        Args:
            selectors: Raw selector strings (e.g., "300201").
            points: Discovered point IDs (requires prior discover() call).
            families: Family names (requires prior discover() call).
            all_discovered: Query all discovered points (requires prior discover() call).
            language: Language for labels.

        Returns:
            A dict with query results.

        Raises:
            UsageError: If points/families/all_discovered used without prior discover().
            UnknownPointError: If a point ID is not found.
            UnknownFamilyError: If a family is not found.
        """
        selectors = selectors or []
        points = points or []
        families = families or []

        # Check if we need the catalog
        needs_catalog = all_discovered or points or families

        if needs_catalog and self._catalog is None:
            raise UsageError(
                "Must call discover() before querying by point ID, family, or all_discovered"
            )

        catalog = self._catalog
        language_map = self.load_language(language)

        # Normalize direct selectors
        direct_selectors = [normalize_selector(s) for s in selectors]

        # Collect points to query
        selected_points = []

        if catalog:
            if all_discovered:
                for family_points in catalog.families.values():
                    selected_points.extend(family_points)

            for family in families:
                family_points = catalog.families.get(family)
                if not family_points:
                    raise UnknownFamilyError(family)
                selected_points.extend(family_points)

            for point_id in points:
                point = catalog.points_by_id.get(point_id)
                if not point:
                    raise UnknownPointError(point_id)
                selected_points.append(point)

        # Deduplicate points by ID
        selected_point_map = {}
        for point in selected_points:
            selected_point_map[point["id"]] = point

        # Build the full request selector set
        request_selector_map = {}
        for selector in direct_selectors:
            request_selector_map[selector.key] = selector

        for point in selected_point_map.values():
            for live_sel in point.get("live_selectors", []):
                normalized = normalize_selector({
                    "index": live_sel["index"],
                    "subindex": live_sel["subindex"],
                })
                request_selector_map[normalized.key] = normalized

        # Query selectors
        request_selectors = list(request_selector_map.values())
        raw_results = []
        if request_selectors:
            raw_results = self.transport.query_selectors(request_selectors)

        raw_map = {r.key: r.raw for r in raw_results}

        # Decode results
        direct_results = [
            {
                "selector": s.key,
                "index": s.index,
                "subindex": s.subindex,
                "raw": raw_map.get(s.key, "X"),
            }
            for s in direct_selectors
            if s.key in raw_map
        ]

        point_results = [
            decode_point(p, raw_map, language_map)
            for p in selected_point_map.values()
        ]

        return {
            "host": self.transport.host,
            "selector_count": len(request_selectors),
            "direct_results": direct_results,
            "point_results": point_results,
            "catalog_summary": catalog.family_counts if catalog else None,
        }

    def list_point_ids(self, catalog: Catalog) -> list[str]:
        """List all point IDs in a catalog.

        Args:
            catalog: The catalog.

        Returns:
            A sorted list of point IDs.
        """
        return sorted(catalog.points_by_id.keys())

    def selector_for_point(self, point: dict) -> list[str]:
        """Get the selector string(s) for a point.

        Args:
            point: The point dict.

        Returns:
            A list of selector strings.
        """
        from pytronikon.codec import format_selector

        return [
            format_selector(s["index"], s["subindex"])
            for s in point.get("live_selectors", [])
        ]

    def close(self) -> None:
        """Close the transport connection."""
        if self.transport:
            self.transport.close()

    def __enter__(self) -> "ElektronikonClient":
        """Context manager entry."""
        return self

    def __exit__(self, exc_type: type, exc_val: Exception, exc_tb: object) -> None:
        """Context manager exit."""
        self.close()

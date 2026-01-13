"""Data loading and management for simtools.

This module provides centralized functions for loading static data files,
building price maps, and managing resources and buildings.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING

from rich.console import Console

if TYPE_CHECKING:
    from simtools.models.building import Building
    from simtools.models.resource import Resource

console = Console()


def get_data_path(filename: str) -> Path:
    """Get the path to a data file.

    First checks the simtools/data directory, then falls back to the workspace root.

    Args:
        filename: Name of the data file.

    Returns:
        Path to the data file.
    """
    # Check package data directory first
    package_data = Path(__file__).parent / "data" / filename
    if package_data.exists():
        return package_data

    # Fall back to workspace root
    return Path(filename)


def load_json_list(filepath: Path) -> list[str]:
    """Load a JSON file containing a list of strings.

    Args:
        filepath: Path to the JSON file.

    Returns:
        List of strings, or empty list if file doesn't exist.
    """
    if not filepath.exists():
        return []
    with open(filepath, "r") as f:
        return json.load(f)


def save_json(data: dict | list, filename: str) -> None:
    """Save data to a JSON file in the workspace root.

    Args:
        data: Data to save.
        filename: Name of the output file.
    """
    with open(filename, "w") as f:
        json.dump(data, f, indent=2)
    console.log(f"Data saved to [cyan]{filename}[/cyan]")


@dataclass
class PriceMaps:
    """Container for price maps at all quality levels.

    This class stores VWAP prices for all quality levels from the API,
    allowing access to any quality's prices on demand.

    Attributes:
        by_quality: Dictionary mapping quality level to price map.
                    Each price map is {resource_id: price}.
        transport_price: Price per transport unit.
        target_quality: The default quality level for convenience access.
    """

    by_quality: dict[int, dict[int, float]]
    transport_price: float
    target_quality: int = 0

    @property
    def current_quality(self) -> dict[int, float]:
        """Get price map for the target quality level."""
        return self.by_quality.get(self.target_quality, {})

    @property
    def quality_zero(self) -> dict[int, float]:
        """Get price map for Q0 (used for building costs)."""
        return self.by_quality.get(0, {})

    def get_quality(self, quality: int) -> dict[int, float]:
        """Get price map for a specific quality level.

        Args:
            quality: Quality level (0-5).

        Returns:
            Price map for the requested quality, or empty dict if not found.
        """
        return self.by_quality.get(quality, {})


def build_price_maps(
    vwaps_data: list[dict],
    raw_resources: list[dict],
    target_quality: int,
) -> PriceMaps:
    """Build price maps from VWAP data.

    Loads all quality levels from the API data into a single structure.

    Args:
        vwaps_data: List of VWAP entries from the API.
        raw_resources: List of raw resource data from the API.
        target_quality: Target quality level for default access.

    Returns:
        PriceMaps containing all quality levels and transport price.
    """
    # Build price maps for all quality levels
    by_quality: dict[int, dict[int, float]] = {}

    if isinstance(vwaps_data, list):
        for entry in vwaps_data:
            if isinstance(entry, dict):
                r_id = entry.get("resourceId")
                quality = entry.get("quality")
                vwap = entry.get("vwap")
                if r_id is not None and quality is not None and vwap is not None:
                    if quality not in by_quality:
                        by_quality[quality] = {}
                    by_quality[quality][int(r_id)] = vwap

    # Get transport price
    transport_price = _get_transport_price(raw_resources, vwaps_data)

    return PriceMaps(
        by_quality=by_quality,
        transport_price=transport_price,
        target_quality=target_quality,
    )


def build_name_to_id_map(raw_resources: list[dict]) -> dict[str, int]:
    """Build a mapping from resource names to IDs.

    Args:
        raw_resources: List of raw resource data from the API.

    Returns:
        Dictionary mapping resource name (lowercase) to resource ID.
    """
    return {r.get("name", "").lower(): r.get("id") for r in raw_resources}


def _get_transport_price(raw_resources: list[dict], vwaps_data: list[dict]) -> float:
    """Get the transport price from VWAP data.

    Args:
        raw_resources: List of raw resource data from the API.
        vwaps_data: List of VWAP entries from the API.

    Returns:
        Transport price per unit.
    """
    # Find transport resource ID
    transport_id = None
    for res in raw_resources:
        if res.get("name", "").lower() == "transport":
            transport_id = res.get("id")
            break

    # Fallback to partial match
    if transport_id is None:
        for res in raw_resources:
            if "transport" in res.get("name", "").lower():
                transport_id = res.get("id")
                break

    if transport_id is None:
        console.print("[yellow]Warning: Could not find 'Transport' resource by name.[/yellow]")
        return 0.0

    # Find Q0 price for transport
    if isinstance(vwaps_data, list):
        for entry in vwaps_data:
            if (
                isinstance(entry, dict)
                and entry.get("resourceId") == transport_id
                and entry.get("quality") == 0
            ):
                return entry.get("vwap", 0.0)

    return 0.0


@dataclass
class GameData:
    """Container for all loaded game data.

    This class holds all the data needed for calculations, including
    resources, buildings, price maps, and lookup tables.
    """

    resources: list[Resource]
    buildings: list[Building]
    price_maps: PriceMaps
    name_to_id: dict[str, int]
    resource_to_building: dict[str, str]
    abundance_resources: list[str]
    seasonal_resources: list[str]

    @property
    def resource_by_name(self) -> dict[str, Resource]:
        """Get resources indexed by lowercase name."""
        return {r.name.lower(): r for r in self.resources}

    @property
    def building_by_name(self) -> dict[str, Building]:
        """Get buildings indexed by name."""
        return {b.name: b for b in self.buildings}

    def filter_resources(
        self,
        exclude_seasonal: bool = False,
        building_filter: list[str] | None = None,
        search_filter: list[str] | None = None,
    ) -> list[Resource]:
        """Filter resources based on criteria.

        Args:
            exclude_seasonal: Whether to exclude seasonal resources.
            building_filter: List of building name patterns to filter by.
            search_filter: List of resource name patterns to search for.

        Returns:
            Filtered list of resources.
        """
        filtered = self.resources

        if exclude_seasonal:
            filtered = [r for r in filtered if not r.is_seasonal]

        if building_filter:
            filtered = [
                r
                for r in filtered
                if r.building_name
                and any(term.lower() in r.building_name.lower() for term in building_filter)
            ]

        if search_filter:
            filtered = [
                r
                for r in filtered
                if any(term.lower() in r.name.lower() for term in search_filter)
            ]

        return filtered

    def get_building_resources(self) -> dict[str, list[Resource]]:
        """Get a mapping of building names to their resources.

        Returns:
            Dictionary mapping building name to list of Resource instances.
        """
        resource_by_name = self.resource_by_name
        building_resources: dict[str, list[Resource]] = {}

        for building in self.buildings:
            res_list = []
            for res_name in building.produces:
                res = resource_by_name.get(res_name.lower())
                if res:
                    res_list.append(res)
            if res_list:
                building_resources[building.name] = res_list

        return building_resources


def load_game_data(
    api,
    target_quality: int = 0,
    save_api_data: bool = True,
) -> GameData:
    """Load all game data from API and static files.

    Args:
        api: SimcoAPI instance for fetching data.
        target_quality: Target quality level for prices.
        save_api_data: Whether to save API data to JSON files.

    Returns:
        GameData instance with all loaded data.
    """
    from simtools.models.building import Building, build_resource_to_building_map
    from simtools.models.resource import Resource

    # Load static data files
    abundance_resources = load_json_list(get_data_path("abundance_resources.json"))
    seasonal_resources = load_json_list(get_data_path("seasonal_resources.json"))
    buildings = Building.load_all(get_data_path("buildings.json"))
    resource_to_building = build_resource_to_building_map(buildings)

    # Fetch API data
    resources_data = api.get_resources()
    raw_resources = resources_data.get("resources", [])
    vwaps_data = api.get_market_vwaps()

    # Save API data
    if save_api_data:
        save_json(resources_data, "resources.json")
        save_json(vwaps_data, "vwaps.json")

    # Build price maps
    price_maps = build_price_maps(vwaps_data, raw_resources, target_quality)

    # Build name to ID map
    name_to_id = build_name_to_id_map(raw_resources)

    # Pre-compute lowercase resource sets for efficiency
    abundance_set = [r.lower() for r in abundance_resources]
    seasonal_set = [r.lower() for r in seasonal_resources]

    # Create Resource objects
    resources = [
        Resource.from_api_data(
            data,
            abundance_resources=abundance_set,
            seasonal_resources=seasonal_set,
        )
        for data in raw_resources
    ]

    # Link resources to buildings
    resource_by_name = {r.name.lower(): r for r in resources}
    for building in buildings:
        building.link_resources(resource_by_name)

    # Set building names on resources
    for res in resources:
        building_name = resource_to_building.get(res.name.lower())
        if building_name:
            res.building_name = building_name

    return GameData(
        resources=resources,
        buildings=buildings,
        price_maps=price_maps,
        name_to_id=name_to_id,
        resource_to_building=resource_to_building,
        abundance_resources=abundance_resources,
        seasonal_resources=seasonal_resources,
    )

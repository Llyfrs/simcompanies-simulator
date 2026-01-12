"""Building model for Sim Companies buildings."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from simtools.models.resource import Resource


@dataclass
class Building:
    """Represents a building in Sim Companies.

    Buildings are the production facilities that create resources. Each building
    has construction costs and a list of resources it can produce.

    Attributes:
        name: Display name of the building.
        id: Unique building identifier.
        cost: Map of material name to quantity required for construction.
        produces: List of resource names this building can produce.
        level: Current building level.
    """

    name: str
    id: str = ""
    cost: dict[str, int] = field(default_factory=dict)
    produces: list[str] = field(default_factory=list)
    level: int = 1

    # Resolved resources (populated after linking with API data)
    _resources: list[Resource] = field(default_factory=list, repr=False)

    @property
    def production_multiplier(self) -> float:
        """Get the production multiplier for this building level."""
        return float(self.level)

    @property
    def wage_multiplier(self) -> float:
        """Get the wage multiplier for this building level."""
        return float(self.level)

    @property
    def resources(self) -> list[Resource]:
        """Get the resolved Resource objects for this building."""
        return self._resources

    @classmethod
    def from_dict(cls, data: dict) -> Building:
        """Create a Building instance from a dictionary.

        Args:
            data: Building data from buildings.json.

        Returns:
            A new Building instance.
        """
        return cls(
            name=data.get("name", ""),
            id=data.get("id", ""),
            cost=data.get("cost", {}),
            produces=data.get("produces", []),
            level=data.get("level", 1),
        )

    @classmethod
    def load_all(cls, filepath: str | Path | None = None) -> list[Building]:
        """Load all buildings from the JSON file.

        Args:
            filepath: Path to buildings.json. If None, uses the default data location.

        Returns:
            List of Building instances.
        """
        if filepath is None:
            filepath = Path(__file__).parent.parent / "data" / "buildings.json"

        filepath = Path(filepath)
        if not filepath.exists():
            return []

        with open(filepath, "r") as f:
            data = json.load(f)

        return [cls.from_dict(b) for b in data]

    def get_resources(self) -> list[Resource]:
        """Get the resolved Resource objects for this building.

        Returns:
            List of Resource instances that this building produces.

        .. deprecated::
            Use the `resources` property instead.
        """
        return self._resources

    def link_resources(self, resources: dict[str, Resource]) -> None:
        """Link this building to its Resource objects.

        Args:
            resources: Dictionary mapping resource names (lowercase) to Resource instances.
        """
        self._resources = []
        for res_name in self.produces:
            resource = resources.get(res_name.lower())
            if resource:
                resource.building_name = self.name
                self._resources.append(resource)

    def calculate_construction_cost(
        self,
        prices: dict[int, float],
        name_to_id: dict[str, int] | None = None,
    ) -> tuple[float, bool]:
        """Calculate the total construction cost for this building.

        Args:
            prices: Map of resource ID to price (Q0 prices).
            name_to_id: Optional map of resource name (lowercase) to resource ID.
                        If provided, prices is expected to be keyed by ID.

        Returns:
            Tuple of (total_cost, missing_price_flag).
        """
        total_cost = 0.0
        missing_price = False

        for material_name, amount in self.cost.items():
            price = self._get_material_price(material_name, prices, name_to_id)
            if price == 0:
                missing_price = True
            total_cost += price * amount

        return total_cost, missing_price

    def calculate_upgrade_cost(
        self,
        prices: dict[int, float],
        target_level: int,
        name_to_id: dict[str, int] | None = None,
    ) -> tuple[float, bool]:
        """Calculate the cost to upgrade this building to a target level.

        The cost to upgrade from level L to L+1 is L * base_cost.
        Total cost is the sum of costs for each step.

        Args:
            prices: Map of resource ID to price (Q0 prices).
            target_level: Level to upgrade to.
            name_to_id: Optional map of resource name (lowercase) to resource ID.

        Returns:
            Tuple of (total_upgrade_cost, missing_price_flag).
        """
        if target_level <= self.level:
            return 0.0, False

        base_cost, missing_price = self.calculate_construction_cost(prices, name_to_id)

        # Sum of upgrade costs: base_cost * (1 + 2 + ... + (target-1))
        # = base_cost * (target-1) * target / 2 when starting from level 1
        # For starting from self.level: sum from self.level to target_level-1
        total_upgrade_cost = sum(
            k * base_cost for k in range(self.level, target_level)
        )

        return total_upgrade_cost, missing_price

    def produces_resource(self, resource_name: str) -> bool:
        """Check if this building produces a specific resource.

        Args:
            resource_name: Name of the resource to check.

        Returns:
            True if this building produces the resource.
        """
        resource_name_lower = resource_name.lower()
        return any(p.lower() == resource_name_lower for p in self.produces)

    def _get_material_price(
        self,
        material_name: str,
        prices: dict[int, float],
        name_to_id: dict[str, int] | None,
    ) -> float:
        """Get the price for a building material.

        Args:
            material_name: Name of the material.
            prices: Price map keyed by resource ID.
            name_to_id: Optional name to ID mapping.

        Returns:
            Price of the material, or 0 if not found.
        """
        if name_to_id is not None:
            mat_id = name_to_id.get(material_name.lower())
            if mat_id is not None:
                return prices.get(mat_id, 0.0)
            return 0.0
        # Legacy: prices keyed by name (should not be used in new code)
        return prices.get(material_name.lower(), 0.0)


def build_resource_to_building_map(buildings: list[Building]) -> dict[str, str]:
    """Build a mapping from resource names to building names.

    Args:
        buildings: List of Building instances.

    Returns:
        Dictionary mapping resource name (lowercase) to building name.
    """
    return {
        res_name.lower(): building.name
        for building in buildings
        for res_name in building.produces
    }


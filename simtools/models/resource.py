"""Resource model for Sim Companies resources."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TypedDict


# Constants for game mechanics
MARKET_FEE_RATE = 0.04
CONTRACT_TRANSPORT_DISCOUNT = 0.5
ROBOT_WAGE_DISCOUNT = 0.03


class ProfitData(TypedDict):
    """Type definition for profit calculation results."""

    name: str
    profit_per_hour: float
    revenue_per_hour: float
    market_fee_per_hour: float
    costs_per_hour: float
    transport_costs_per_hour: float
    missing_input_price: bool
    is_abundance_res: bool


@dataclass(slots=True)
class ResourceInput:
    """Represents an input material required for production.

    Attributes:
        id: The resource ID of the input material.
        name: The display name of the input material.
        quantity: The amount required per unit of output.
    """

    id: int
    name: str
    quantity: float


@dataclass
class Resource:
    """Represents a producible resource in Sim Companies.

    Resources are the items that can be produced by buildings. Each resource
    has production characteristics (rate, wages, inputs) and market properties
    (transportation costs, retail info).

    Attributes:
        id: Unique resource identifier.
        name: Display name of the resource.
        produced_per_hour: Base production rate per hour.
        wages: Base wage cost per hour.
        transportation: Transport cost units per item.
        inputs: Map of input resource ID to ResourceInput.
        is_research: Whether this is a research resource.
        speed_modifier: Speed modifier for production.
        retail_info: Retail-specific information if applicable.
        is_abundance: Whether production is affected by abundance.
        is_seasonal: Whether this is a seasonal resource.
        building_name: Name of the building that produces this resource.
    """

    id: int
    name: str
    produced_per_hour: float
    wages: float
    transportation: float
    inputs: dict[int, ResourceInput] = field(default_factory=dict)
    is_research: bool = False
    speed_modifier: float = 0.0
    retail_info: list[dict] | None = None
    is_abundance: bool = False
    is_seasonal: bool = False
    building_name: str | None = None

    @classmethod
    def from_api_data(
        cls,
        data: dict,
        abundance_resources: list[str] | None = None,
        seasonal_resources: list[str] | None = None,
    ) -> Resource:
        """Create a Resource instance from API response data.

        Args:
            data: Raw resource data from the Simcotools API.
            abundance_resources: List of resource names that use abundance calculation.
            seasonal_resources: List of resource names that are seasonal.

        Returns:
            A new Resource instance.
        """
        abundance_set = {r.lower() for r in (abundance_resources or [])}
        seasonal_set = {r.lower() for r in (seasonal_resources or [])}

        name = data.get("name", "")
        name_lower = name.lower()

        # Parse inputs
        inputs: dict[int, ResourceInput] = {}
        for input_id_str, input_info in data.get("inputs", {}).items():
            input_id = int(input_id_str)
            inputs[input_id] = ResourceInput(
                id=input_id,
                name=input_info.get("name", ""),
                quantity=input_info.get("quantity", 0),
            )

        return cls(
            id=data.get("id", 0),
            name=name,
            produced_per_hour=data.get("producedAnHour", 0),
            wages=data.get("wages", 0),
            transportation=data.get("transportation", 0),
            inputs=inputs,
            is_research=data.get("isResearch", False),
            speed_modifier=data.get("speedModifier", 0),
            retail_info=data.get("retailInfo"),
            is_abundance=name_lower in abundance_set,
            is_seasonal=name_lower in seasonal_set,
        )

    def get_effective_production(self, abundance: float = 100.0) -> float:
        """Get the effective production rate, accounting for abundance if applicable.

        Args:
            abundance: Abundance percentage (0-100) for mine/well resources.

        Returns:
            Effective production rate per hour.
        """
        rate = self.produced_per_hour
        if self.is_abundance:
            rate *= abundance / 100.0
        return rate

    def calculate_profit(
        self,
        selling_price: float,
        input_prices: dict[int, float],
        transport_price: float,
        abundance: float = 100.0,
        admin_overhead: float = 0.0,
        is_contract: bool = False,
        has_robots: bool = False,
    ) -> ProfitData:
        """Calculate profit metrics for this resource.

        Args:
            selling_price: Price per unit at the target quality.
            input_prices: Map of resource ID to price for input materials.
            transport_price: Price per transport unit.
            abundance: Abundance percentage for mine/well resources.
            admin_overhead: Administrative overhead percentage to add to wages.
            is_contract: If True, use contract mode (0% fee, 50% transport).
            has_robots: If True, apply 3% wage reduction for robots.

        Returns:
            ProfitData dictionary with profit breakdown including:
                - profit_per_hour: Net profit per hour
                - revenue_per_hour: Gross revenue per hour
                - market_fee_per_hour: Market fee per hour
                - costs_per_hour: Wages + admin + input costs per hour
                - transport_costs_per_hour: Transportation costs per hour
                - missing_input_price: True if any input price was missing
                - is_abundance_res: True if abundance-based
        """
        produced_per_hour = self.get_effective_production(abundance)

        # Calculate wages with modifiers
        base_wages = self.wages
        if has_robots:
            base_wages *= (1.0 - ROBOT_WAGE_DISCOUNT)

        admin_cost = base_wages * (admin_overhead / 100.0)
        total_wages = base_wages + admin_cost

        # Calculate revenue
        revenue_per_hour = selling_price * produced_per_hour

        # Calculate market fee
        market_fee_rate = 0.0 if is_contract else MARKET_FEE_RATE
        market_fee_per_hour = revenue_per_hour * market_fee_rate

        # Calculate input costs
        input_costs_per_hour = 0.0
        missing_input_price = False
        for input_id, input_info in self.inputs.items():
            price = input_prices.get(input_id, 0)
            if price == 0 and input_info.quantity > 0:
                missing_input_price = True
            input_costs_per_hour += price * input_info.quantity * produced_per_hour

        # Calculate transportation costs
        transport_multiplier = CONTRACT_TRANSPORT_DISCOUNT if is_contract else 1.0
        transport_cost_per_unit = self.transportation * transport_price * transport_multiplier
        transport_costs_per_hour = transport_cost_per_unit * produced_per_hour

        # Calculate total profit
        profit_per_hour = (
            revenue_per_hour
            - market_fee_per_hour
            - total_wages
            - input_costs_per_hour
            - transport_costs_per_hour
        )

        return {
            "name": self.name,
            "profit_per_hour": profit_per_hour,
            "revenue_per_hour": revenue_per_hour,
            "market_fee_per_hour": market_fee_per_hour,
            "costs_per_hour": total_wages + input_costs_per_hour,
            "transport_costs_per_hour": transport_costs_per_hour,
            "missing_input_price": missing_input_price,
            "is_abundance_res": self.is_abundance,
        }


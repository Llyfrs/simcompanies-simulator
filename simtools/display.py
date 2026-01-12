"""Display functions for simtools.

This module contains all Rich-based table and console display functions
for presenting calculation results to users.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from rich import box
from rich.console import Console
from rich.table import Table

if TYPE_CHECKING:
    from simtools.calculator import ProfitConfig
    from simtools.genetic import GeneticAlgorithm, SimulationConfig, Individual

console = Console()


def display_prospecting_results(results: dict) -> None:
    """Display prospecting simulation results.

    Args:
        results: Results from simulate_prospecting().
    """
    if results.get("impossible"):
        console.print(
            f"[bold red]Target abundance {results['target_abundance']*100:.1f}% "
            f"is impossible with the current distribution.[/bold red]"
        )
        return

    table_width = 60

    table = Table(
        title="Prospecting Simulation Results",
        show_header=True,
        header_style="bold magenta",
        box=box.ROUNDED,
        width=table_width,
    )
    table.add_column("Statistic", style="cyan")
    table.add_column("Value", justify="right", style="green")

    table.add_row("Target Abundance", f"{results['target_abundance']*100:.1f}%")
    table.add_row("Build Time per Attempt", f"{results['attempt_time']:.1f} hours")
    table.add_row("Number of Slots", f"{results['slots']}")
    table.add_row("Prob. Success (Single)", f"{results['p_success_single']*100:.4f}%")
    table.add_row("Prob. Success (Block)", f"{results['p_success_block']*100:.4f}%")
    table.add_row("Expected Blocks", f"{results['expected_blocks']:.2f}")
    table.add_row(
        "Expected Time",
        f"{results['expected_time']:.2f} hours ({results['expected_time']/24:.2f} days)",
    )

    if results.get("days_to_85") is not None:
        table.add_row("Days until 85%", f"{results['days_to_85']:.1f} days")

    console.print(table)

    # Confidence intervals table
    conf_table = Table(
        title="Confidence Intervals (Time to Success)",
        show_header=True,
        header_style="bold blue",
        box=box.ROUNDED,
        width=table_width,
    )
    conf_table.add_column("Confidence Level", style="cyan")
    conf_table.add_column("Required Blocks", justify="right", style="yellow")
    conf_table.add_column("Required Time", justify="right", style="green")

    for ci in results["confidence_intervals"]:
        conf_table.add_row(
            f"{ci['confidence']*100:.0f}%",
            f"{ci['blocks']}",
            f"{ci['time_hours']:.1f}h ({ci['time_days']:.1f}d)",
        )

    console.print(conf_table)


def display_profits_table(
    profits: list[dict],
    transport_price: float,
    config: ProfitConfig,
    search_terms: list[str] | None = None,
    building_terms: list[str] | None = None,
) -> None:
    """Display the profits table.

    Args:
        profits: List of profit dictionaries.
        transport_price: Price per transport unit.
        config: Profit calculation configuration.
        search_terms: Search terms used for filtering (for header).
        building_terms: Building terms used for filtering (for header).
    """
    header_title = _build_header_title(search_terms, building_terms, config.is_contract)

    console.print(f"\n[bold blue]{header_title}[/bold blue]")
    market_fee_display = "0%" if config.is_contract else "4%"
    console.print(
        f"Quality: [bold cyan]{config.quality}[/bold cyan] | "
        f"Transport: [bold cyan]${transport_price:.3f}[/bold cyan] | "
        f"Market Fee: [bold cyan]{market_fee_display}[/bold cyan] | "
        f"Admin Overhead: [bold cyan]{config.admin_overhead}%[/bold cyan] | "
        f"Robots: [bold cyan]{'Yes' if config.has_robots else 'No'}[/bold cyan]"
    )

    table = Table(
        show_header=True,
        header_style="bold white on blue",
        box=box.ROUNDED,
        border_style="bright_black",
    )
    table.add_column("Resource", style="bold white", width=25)
    table.add_column("Profit/hr", justify="right")
    table.add_column("Revenue/hr", justify="right", style="white")
    table.add_column("Fee/hr", justify="right", style="red")
    table.add_column("Costs/hr", justify="right", style="yellow")
    table.add_column("Transp/hr", justify="right", style="magenta")

    display_count = 30 if not search_terms else len(profits)
    for p in profits[:display_count]:
        warn = " [bold red](!)[/bold red]" if p["missing_input_price"] else ""
        abundance_mark = " [bold yellow](*)[/bold yellow]" if p["is_abundance_res"] else ""
        profit_style = "bold green" if p["profit_per_hour"] >= 0 else "bold red"

        table.add_row(
            f"{p['name']}{abundance_mark}",
            f"[{profit_style}]${p['profit_per_hour']:,.2f}[/{profit_style}]",
            f"${p['revenue_per_hour']:,.2f}",
            f"${p['market_fee_per_hour']:,.2f}",
            f"${p['costs_per_hour']:,.2f}",
            f"${p['transport_costs_per_hour']:,.2f}{warn}",
        )

    console.print(table)

    if any(p["is_abundance_res"] for p in profits[:display_count]):
        console.print(
            f"\n[bold yellow](*)[/bold yellow] indicates abundance-based resource "
            f"(applied {config.abundance}% abundance)"
        )
    if any(p["missing_input_price"] for p in profits[:display_count]):
        console.print(
            f"[bold red](!)[/bold red] indicates one or more source materials had no "
            f"Quality {config.quality} market price"
        )


def display_roi_table(roi_data: list[dict]) -> None:
    """Display the ROI analysis table.

    Args:
        roi_data: List of ROI dictionaries.
    """
    roi_table = Table(
        title="Building ROI Analysis",
        show_header=True,
        header_style="bold green",
        box=box.ROUNDED,
    )
    roi_table.add_column("Building", style="bold white")
    if roi_data and "level" in roi_data[0]:
        col_name = "Step/Lv" if any("→" in str(d.get("level", "")) for d in roi_data) else "Lv"
        roi_table.add_column(col_name, justify="right", style="cyan")
    roi_table.add_column("Best Resource", style="cyan")
    roi_table.add_column("Building Cost", justify="right", style="magenta")
    roi_table.add_column("Daily Profit", justify="right", style="green")
    roi_table.add_column("ROI (Daily)", justify="right", style="bold yellow")
    roi_table.add_column("Break Even", justify="right", style="white")

    for d in roi_data:
        break_even_str = _format_break_even(d["break_even"], d["daily_profit"])
        warn = " (!)" if d["missing_cost"] else ""

        row_data = [d["building"]]
        if "level" in d:
            row_data.append(str(d["level"]))

        row_data.extend([
            d["resource"],
            f"${d['cost']:,.0f}{warn}",
            f"${d['daily_profit']:,.0f}",
            f"{d['roi']:.2f}%",
            break_even_str,
        ])

        roi_table.add_row(*row_data)

    console.print("\n")
    console.print(roi_table)
    if any(d["missing_cost"] for d in roi_data):
        console.print(
            "[yellow](!) Warning: Some building costs calculated with missing "
            "material prices (assumed $0).[/yellow]"
        )


def display_lifecycle_table(results: list[dict], start_abundance: float) -> None:
    """Display lifecycle ROI analysis table.

    Args:
        results: List of lifecycle result dictionaries.
        start_abundance: Starting abundance percentage.
    """
    table = Table(
        title=f"Lifecycle Analysis (Abundance {start_abundance}% -> 85%)",
        show_header=True,
        header_style="bold cyan",
        box=box.ROUNDED,
    )
    table.add_column("Resource", style="bold white")
    table.add_column("Level", justify="right", style="cyan")
    table.add_column("Build(h)", justify="right", style="blue")
    table.add_column("Prod Days", justify="right", style="white")
    table.add_column("Investment", justify="right", style="magenta")
    table.add_column("Unrecoverable", justify="right", style="red")
    table.add_column("Ops Profit", justify="right", style="green")
    table.add_column("Net Profit", justify="right", style="bold yellow")

    for res in results[:30]:
        warn = " (!)" if res["missing_cost"] else ""
        table.add_row(
            res["resource"],
            str(res["level"]),
            f"{res['build_time_hours']:.1f}",
            str(res["days"]),
            f"${res['investment']:,.0f}{warn}",
            f"${res['unrecoverable']:,.0f}",
            f"${res['operational_profit']:,.0f}",
            f"${res['net_profit']:,.0f}",
        )

    console.print("\n")
    console.print(table)
    if any(r["missing_cost"] for r in results):
        console.print(
            "[yellow](!) Warning: Some costs/profits calculated with missing prices.[/yellow]"
        )


def display_compare_table(
    comparisons: list[dict],
    transport_price: float,
    config: ProfitConfig,
) -> None:
    """Display market vs contract comparison table.

    Args:
        comparisons: List of comparison dictionaries from compare_market_vs_contract.
        transport_price: Price per transport unit.
        config: Profit calculation configuration.
    """
    console.print("\n[bold blue]Market vs Contract Comparison[/bold blue]")
    console.print(
        f"Quality: [bold cyan]{config.quality}[/bold cyan] | "
        f"Transport: [bold cyan]${transport_price:.3f}[/bold cyan] | "
        f"Abundance: [bold cyan]{config.abundance}%[/bold cyan] | "
        f"Admin Overhead: [bold cyan]{config.admin_overhead}%[/bold cyan] | "
        f"Robots: [bold cyan]{'Yes' if config.has_robots else 'No'}[/bold cyan]"
    )

    table = Table(
        show_header=True,
        header_style="bold white on blue",
        box=box.ROUNDED,
        border_style="bright_black",
    )

    # Add columns
    table.add_column("Resource", style="bold white")
    table.add_column("Mkt Price", justify="right", style="cyan")
    table.add_column("Mkt Fee/u", justify="right", style="red")
    table.add_column("Mkt Trans/u", justify="right", style="magenta")
    table.add_column("Mkt Net/u", justify="right", style="white")
    table.add_column("Mkt $/hr", justify="right", style="white")
    table.add_column("Cnt Price", justify="right", style="cyan")
    table.add_column("Cnt Fee/u", justify="right", style="red")
    table.add_column("Cnt Trans/u", justify="right", style="magenta")
    table.add_column("Cnt Net/u", justify="right", style="white")
    table.add_column("Cnt $/hr", justify="right", style="white")
    table.add_column("Diff/u", justify="right")
    table.add_column("Diff/hr", justify="right")

    for comp in comparisons:
        warn = " [bold red](!)[/bold red]" if comp["missing_input_price"] else ""
        abundance_mark = " [bold yellow](*)[/bold yellow]" if comp["is_abundance_res"] else ""

        diff_unit_style, diff_unit_prefix = _get_diff_style(comp["diff_per_unit"])
        diff_hour_style, diff_hour_prefix = _get_diff_style(comp["diff_per_hour"])

        table.add_row(
            f"{comp['name']}{abundance_mark}{warn}",
            f"${comp['market']['price']:.2f}",
            f"${comp['market']['fee_per_unit']:.2f}",
            f"${comp['market']['transport_per_unit']:.2f}",
            f"${comp['market']['net_per_unit']:.2f}",
            f"${comp['market']['profit_per_hour']:.2f}",
            f"${comp['contract']['price']:.2f}",
            f"${comp['contract']['fee_per_unit']:.2f}",
            f"${comp['contract']['transport_per_unit']:.2f}",
            f"${comp['contract']['net_per_unit']:.2f}",
            f"${comp['contract']['profit_per_hour']:.2f}",
            f"[{diff_unit_style}]{diff_unit_prefix}${comp['diff_per_unit']:.2f}[/{diff_unit_style}]",
            f"[{diff_hour_style}]{diff_hour_prefix}${comp['diff_per_hour']:.2f}[/{diff_hour_style}]",
        )

    console.print(table)

    if any(comp["is_abundance_res"] for comp in comparisons):
        console.print(
            f"\n[bold yellow](*)[/bold yellow] indicates abundance-based resource "
            f"(applied {config.abundance}% abundance)"
        )
    if any(comp["missing_input_price"] for comp in comparisons):
        console.print(
            f"[bold red](!)[/bold red] indicates one or more source materials had no "
            f"Quality {config.quality} market price"
        )


def display_company_analysis(
    company_data: dict,
    building_stats: list[dict],
    config: ProfitConfig,
) -> None:
    """Display company analysis results.

    Args:
        company_data: Raw company data from API.
        building_stats: List of building statistics from calculate_company_building_stats.
        config: Profit calculation configuration.
    """
    company = company_data.get("company", {})

    _print_section_header("COMPANY ANALYSIS")

    # Company info
    console.print("[bold cyan]Company Info:[/bold cyan]")
    console.print(f"  • Name: [yellow]{company.get('name', 'N/A')}[/yellow]")
    console.print(f"  • Level: [yellow]{company.get('level', 'N/A')}[/yellow]")
    console.print(f"  • Rating: [yellow]{company.get('rating', 'N/A')}[/yellow]")
    console.print(f"  • Total Buildings: [yellow]{company.get('totalBuildings', 'N/A')}[/yellow]")
    console.print(f"  • Workers: [yellow]{company.get('workers', 'N/A')}[/yellow]")
    console.print(f"  • Building Value: [yellow]${company.get('buildingValue', 0):,.0f}[/yellow]")
    console.print()

    # Configuration used
    console.print("[bold cyan]Analysis Configuration:[/bold cyan]")
    market_fee_display = "0%" if config.is_contract else "4%"
    console.print(
        f"  • Quality: [yellow]{config.quality}[/yellow] | "
        f"Abundance: [yellow]{config.abundance}%[/yellow] | "
        f"Market Fee: [yellow]{market_fee_display}[/yellow] | "
        f"Admin Overhead: [yellow]{config.admin_overhead}%[/yellow] | "
        f"Robots: [yellow]{'Yes' if config.has_robots else 'No'}[/yellow]"
    )
    console.print()

    if not building_stats:
        console.print("[yellow]No building data available for analysis.[/yellow]")
        return

    # Buildings table
    table = Table(
        title="Building Performance Analysis",
        show_header=True,
        header_style="bold white on green",
        box=box.ROUNDED,
    )
    table.add_column("Building", style="bold white")
    table.add_column("Lv", justify="center", style="cyan")
    table.add_column("Best Resource", style="magenta")
    table.add_column("$/hour", justify="right", style="green")
    table.add_column("$/day", justify="right", style="green")
    table.add_column("Value", justify="right", style="yellow")
    table.add_column("ROI/day", justify="right", style="bold cyan")
    table.add_column("Break Even", justify="right", style="white")

    total_hourly = 0.0
    total_daily = 0.0
    total_value = 0.0

    for stat in building_stats:
        total_hourly += stat["hourly_profit"]
        total_daily += stat["daily_profit"]
        total_value += stat["building_value"]

        break_even_str = _format_break_even(stat["break_even_days"], stat["daily_profit"])
        warn = " (!)" if stat["missing_cost"] else ""
        profit_style = "green" if stat["hourly_profit"] >= 0 else "red"

        table.add_row(
            stat["building_name"],
            str(stat["level"]),
            stat["best_resource"] or "N/A",
            f"[{profit_style}]${stat['hourly_profit']:,.2f}[/{profit_style}]",
            f"[{profit_style}]${stat['daily_profit']:,.2f}[/{profit_style}]",
            f"${stat['building_value']:,.0f}{warn}",
            f"{stat['roi_daily']:.2f}%",
            break_even_str,
        )

    console.print(table)

    # Summary
    console.print("\n[bold magenta]Summary:[/bold magenta]")
    profit_style = "green" if total_hourly >= 0 else "red"
    console.print(f"  • Total Hourly Profit: [{profit_style}]${total_hourly:,.2f}[/{profit_style}]")
    console.print(f"  • Total Daily Profit: [{profit_style}]${total_daily:,.2f}[/{profit_style}]")
    console.print(f"  • Total Building Value: [yellow]${total_value:,.0f}[/yellow]")
    if total_value > 0:
        overall_roi = (total_daily / total_value) * 100
        console.print(f"  • Overall Daily ROI: [cyan]{overall_roi:.2f}%[/cyan]")
        if total_daily > 0:
            overall_break_even = total_value / total_daily
            console.print(f"  • Overall Break Even: [white]{overall_break_even:.1f} days[/white]")

    if any(stat["missing_cost"] for stat in building_stats):
        console.print(
            "\n[yellow](!) Warning: Some building costs calculated with missing "
            "material prices (assumed $0).[/yellow]"
        )


def display_upgrade_recommendations(
    recommendations: list[dict],
    config: ProfitConfig,
    top_n: int = 10,
) -> None:
    """Display upgrade recommendations.

    Args:
        recommendations: List of upgrade recommendations sorted by marginal ROI.
        config: Profit calculation configuration.
        top_n: Number of top recommendations to display.
    """
    _print_section_header("UPGRADE RECOMMENDATIONS")

    if not recommendations:
        console.print("[yellow]No upgrade recommendations available.[/yellow]")
        return

    console.print(
        "[bold cyan]Recommendation based on marginal ROI:[/bold cyan] "
        "The best upgrade is the one that gives the highest return on the upgrade cost."
    )
    console.print()

    table = Table(
        title=f"Top {min(top_n, len(recommendations))} Upgrade Recommendations",
        show_header=True,
        header_style="bold white on blue",
        box=box.ROUNDED,
    )
    table.add_column("#", justify="center", style="bold white")
    table.add_column("Building", style="bold white")
    table.add_column("Upgrade", justify="center", style="cyan")
    table.add_column("Best Resource", style="magenta")
    table.add_column("Upgrade Cost", justify="right", style="yellow")
    table.add_column("+$/day", justify="right", style="green")
    table.add_column("Marginal ROI", justify="right", style="bold cyan")
    table.add_column("Break Even", justify="right", style="white")

    for i, rec in enumerate(recommendations[:top_n], 1):
        break_even_str = _format_break_even(rec["marginal_break_even"], rec["additional_daily_profit"])
        warn = " (!)" if rec["missing_cost"] else ""
        profit_style = "green" if rec["additional_daily_profit"] >= 0 else "red"
        rank_style = "bold green" if i == 1 else "white"

        table.add_row(
            f"[{rank_style}]{i}[/{rank_style}]",
            rec["building_name"],
            f"Lv{rec['current_level']}→{rec['next_level']}",
            rec["best_resource"],
            f"${rec['upgrade_cost']:,.0f}{warn}",
            f"[{profit_style}]+${rec['additional_daily_profit']:,.2f}[/{profit_style}]",
            f"{rec['marginal_roi']:.2f}%",
            break_even_str,
        )

    console.print(table)

    if recommendations:
        best = recommendations[0]
        console.print(
            f"\n[bold green]★ Recommended next upgrade:[/bold green] "
            f"[bold]{best['building_name']}[/bold] from Level {best['current_level']} to "
            f"Level {best['next_level']}"
        )
        console.print(
            f"  Cost: [yellow]${best['upgrade_cost']:,.0f}[/yellow] → "
            f"Adds [green]+${best['additional_daily_profit']:,.2f}/day[/green] → "
            f"ROI: [cyan]{best['marginal_roi']:.2f}%[/cyan]"
        )

    if any(rec["missing_cost"] for rec in recommendations[:top_n]):
        console.print(
            "\n[yellow](!) Warning: Some upgrade costs calculated with missing "
            "material prices (assumed $0).[/yellow]"
        )


def display_genetic_results(
    best_individual: Individual,
    fitness_history: list[float],
    config: SimulationConfig,
    ga: GeneticAlgorithm,
) -> None:
    """Display genetic algorithm results.

    Args:
        best_individual: The best individual from the genetic algorithm.
        fitness_history: List of best fitness values per generation.
        config: Simulation configuration used.
        ga: The GeneticAlgorithm instance for calculating costs.
    """
    from simtools.genetic import render_ascii_graph

    _print_section_header("GENETIC ALGORITHM RESULTS")

    # Configuration summary
    console.print("[bold cyan]Configuration:[/bold cyan]")
    console.print(f"  • Building Slots: [yellow]{config.slots}[/yellow]")
    console.print(f"  • Max Budget: [yellow]${config.budget:,.0f}[/yellow]")
    console.print(f"  • Population Size: [yellow]{config.population_size}[/yellow]")
    console.print(f"  • Generations: [yellow]{config.generations}[/yellow]")
    console.print(f"  • Max Building Level: [yellow]{config.max_level}[/yellow]")
    console.print(f"  • Mutation Rate: [yellow]{config.mutation_rate:.1%}[/yellow]")
    console.print(f"  • Crossover Rate: [yellow]{config.crossover_rate:.1%}[/yellow]")
    console.print()

    # Best configuration
    console.print("[bold green]Best Building Configuration:[/bold green]")

    if best_individual.genes:
        table = Table(
            show_header=True,
            header_style="bold white on green",
            box=box.ROUNDED,
        )
        table.add_column("Building", style="bold white")
        table.add_column("Produces", style="magenta")
        table.add_column("Level", justify="center", style="cyan")
        table.add_column("Cost", justify="right", style="yellow")

        for gene in best_individual.genes:
            cost = ga.calculate_building_cost(gene.building_name, gene.level)
            resource = ga.get_best_resource_for_building(gene.building_name)
            resource_name = resource.name if resource else "N/A"
            table.add_row(
                gene.building_name,
                resource_name,
                str(gene.level),
                f"${cost:,.0f}",
            )

        console.print(table)
    else:
        console.print("  [red]No buildings in best configuration[/red]")

    console.print()

    # Summary statistics
    budget_status = "WITHIN" if best_individual.total_cost <= config.budget else "OVER"
    budget_style = "green" if budget_status == "WITHIN" else "red"

    console.print("[bold magenta]Results Summary:[/bold magenta]")
    console.print(f"  • Total Investment: [yellow]${best_individual.total_cost:,.0f}[/yellow]")
    console.print(
        f"  • Budget Status: [{budget_style}]{budget_status}[/{budget_style}] "
        f"({best_individual.total_cost / config.budget * 100:.1f}% of budget)"
    )
    console.print(f"  • Buildings Used: [yellow]{len(best_individual.genes)}[/yellow] / {config.slots} slots")

    profit_style = "green" if best_individual.fitness >= 0 else "red"
    console.print(f"  • 48-Hour Profit: [{profit_style}]${best_individual.fitness:,.2f}[/{profit_style}]")

    if best_individual.fitness > 0:
        hourly = best_individual.fitness / 48
        daily = hourly * 24
        console.print(f"  • Hourly Profit: [green]${hourly:,.2f}[/green]")
        console.print(f"  • Daily Profit: [green]${daily:,.2f}[/green]")
        if best_individual.total_cost > 0:
            roi_days = best_individual.total_cost / daily
            console.print(f"  • ROI Break-even: [cyan]{roi_days:.1f} days[/cyan]")

    console.print()

    # Fitness graph
    if fitness_history:
        console.print("[bold blue]Fitness Evolution Graph:[/bold blue]")
        graph_width = min(60, max(30, len(fitness_history)))
        graph_lines = render_ascii_graph(fitness_history, width=graph_width, height=12)
        for line in graph_lines:
            console.print(f"  {line}")

    console.print()


def prompt_building_levels(
    building_ids: dict[str, int],
    buildings: list,
) -> dict[str, int]:
    """Prompt the user to enter building levels interactively.

    Args:
        building_ids: Dict of building ID to count from API.
        buildings: List of all Building instances.

    Returns:
        Dict of building ID to level.
    """
    id_to_name = {b.id: b.name for b in buildings}

    console.print("\n[bold cyan]Enter building levels:[/bold cyan]")
    console.print("(Press Enter to use default level 1)")
    console.print()

    building_levels = {}

    for building_id, count in building_ids.items():
        building_name = id_to_name.get(building_id)

        if building_name is None:
            console.print(f"[yellow]Skipping unknown building (ID: {building_id}) - not in buildings.json[/yellow]")
            continue

        if count > 1:
            console.print(f"[bold]{building_name}[/bold] (x{count}):")
            for i in range(count):
                level = _prompt_for_level(f"  Building #{i+1} level: ")
                building_levels[f"{building_id}_{i}"] = level
        else:
            level = _prompt_for_level(f"[bold]{building_name}[/bold] level: ")
            building_levels[building_id] = level

    return building_levels


# Helper functions


def _build_header_title(
    search_terms: list[str] | None,
    building_terms: list[str] | None,
    is_contract: bool,
) -> str:
    """Build the header title for profit tables."""
    header_title = "Top 30 Most Profitable Resources"
    if search_terms or building_terms:
        parts = []
        if search_terms:
            parts.append(f"search: '{', '.join(search_terms)}'")
        if building_terms:
            parts.append(f"building: '{', '.join(building_terms)}'")
        header_title = f"Results for {' & '.join(parts)}"

    if is_contract:
        header_title += " (Direct Contract Mode)"

    return header_title


def _format_break_even(break_even: float, daily_profit: float) -> str:
    """Format break-even display string."""
    if break_even == float("inf"):
        return "∞"
    elif daily_profit < 0:
        return "Never"
    else:
        return f"{break_even:.1f} days"


def _get_diff_style(value: float) -> tuple[str, str]:
    """Get style and prefix for difference values."""
    if value > 0:
        return "bold green", "+"
    elif value < 0:
        return "bold red", ""
    else:
        return "white", ""


def _print_section_header(title: str) -> None:
    """Print a section header with decorative borders."""
    border = "═" * 63
    console.print(f"\n[bold blue]{border}[/bold blue]")
    console.print(f"[bold blue]              {title:<49}[/bold blue]")
    console.print(f"[bold blue]{border}[/bold blue]\n")


def _prompt_for_level(prompt_text: str) -> int:
    """Prompt user for a level value with validation."""
    while True:
        try:
            level_input = console.input(prompt_text)
            if level_input.strip() == "":
                return 1
            level = int(level_input)
            if level < 1:
                console.print("[red]Level must be at least 1[/red]")
                continue
            return level
        except ValueError:
            console.print("[red]Please enter a valid number[/red]")

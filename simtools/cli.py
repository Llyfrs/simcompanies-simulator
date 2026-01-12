"""Command-line interface for simtools."""

from __future__ import annotations

import argparse

from rich.progress import Progress, SpinnerColumn, TextColumn, BarColumn, TaskProgressColumn

from simtools.api import SimcoAPI
from simtools.calculator import (
    ProfitConfig,
    calculate_all_profits,
    calculate_building_roi,
    calculate_company_building_stats,
    calculate_level_roi,
    calculate_lifecycle_roi,
    calculate_upgrade_recommendations,
    compare_market_vs_contract,
    simulate_prospecting,
)
from simtools.data_loader import (
    get_data_path,
    load_game_data,
)
from simtools.display import (
    console,
    display_compare_table,
    display_company_analysis,
    display_genetic_results,
    display_lifecycle_table,
    display_profits_table,
    display_prospecting_results,
    display_roi_table,
    display_upgrade_recommendations,
    prompt_building_levels,
)
from simtools.genetic import GeneticAlgorithm, SimulationConfig
from simtools.models.building import Building, build_resource_to_building_map


# =============================================================================
# Command Handlers
# =============================================================================


def handle_prospect_command(args: argparse.Namespace) -> None:
    """Handle the prospect subcommand."""
    results = simulate_prospecting(args.abundance / 100, args.time, args.slots)
    display_prospecting_results(results)


def handle_debug_command(args: argparse.Namespace, api: SimcoAPI) -> None:
    """Handle the debug subcommand."""
    if hasattr(args, "debug_unassigned") and args.debug_unassigned:
        buildings = Building.load_all(get_data_path("buildings.json"))
        resource_to_building = build_resource_to_building_map(buildings)

        resources_data = api.get_resources()
        raw_resources = resources_data.get("resources", [])

        unassigned = [
            res.get("name")
            for res in raw_resources
            if res.get("name", "").lower() not in resource_to_building
        ]
        unassigned.sort()
        console.print("\n[bold red]Resources not assigned to any building:[/bold red]")
        for name in unassigned:
            console.print(f" - {name}")
    else:
        console.print("[yellow]No debug option specified. Use -u/--unassigned[/yellow]")


def handle_lifecycle_command(
    args: argparse.Namespace,
    game_data,
    config: ProfitConfig,
) -> None:
    """Handle the lifecycle subcommand."""
    filtered_resources = game_data.filter_resources(
        exclude_seasonal=getattr(args, "exclude_seasonal", False),
        building_filter=getattr(args, "building", None),
    )

    abundance_res_objects = [r for r in filtered_resources if r.is_abundance]
    lifecycle_results = []

    for res in abundance_res_objects:
        if not res.building_name:
            continue

        building = next(
            (b for b in game_data.buildings if b.name == res.building_name), None
        )
        if not building:
            continue

        res_results = calculate_lifecycle_roi(
            building=building,
            resource=res,
            profit_config=config,
            current_prices=game_data.price_maps.current_quality,
            q0_prices=game_data.price_maps.quality_zero,
            transport_price=game_data.price_maps.transport_price,
            name_to_id=game_data.name_to_id,
            start_abundance=args.abundance / 100.0,
            max_level=args.max_level,
            base_build_time=args.build_time,
        )
        lifecycle_results.extend(res_results)

    lifecycle_results.sort(key=lambda x: x["net_profit"], reverse=True)
    display_lifecycle_table(lifecycle_results, args.abundance)


def handle_roi_command(
    args: argparse.Namespace,
    game_data,
    profits: list[dict],
    config: ProfitConfig,
) -> None:
    """Handle the roi subcommand."""
    if hasattr(args, "building") and args.building:
        res_profit_map = {p["name"].lower(): p for p in profits}
        all_roi_data = []

        for building in game_data.buildings:
            best_profit = -float("inf")
            best_p_data = None

            for res_name in building.produces:
                res_name_lower = res_name.lower()
                if res_name_lower in res_profit_map:
                    p_data = res_profit_map[res_name_lower]
                    if p_data["profit_per_hour"] > best_profit:
                        best_profit = p_data["profit_per_hour"]
                        best_p_data = p_data

            if best_p_data:
                all_roi_data.extend(
                    calculate_level_roi(
                        building,
                        best_p_data,
                        game_data.price_maps.quality_zero,
                        game_data.name_to_id,
                        max_level=args.max_level,
                        step_mode=args.step_roi,
                    )
                )

        display_roi_table(all_roi_data)
    else:
        roi_data = calculate_building_roi(
            game_data.buildings,
            profits,
            game_data.price_maps.quality_zero,
            game_data.name_to_id,
        )
        display_roi_table(roi_data)


def handle_profit_command(
    args: argparse.Namespace,
    profits: list[dict],
    transport_price: float,
    config: ProfitConfig,
) -> None:
    """Handle the profit subcommand."""
    display_profits_table(
        profits,
        transport_price,
        config,
        search_terms=getattr(args, "search", None),
        building_terms=getattr(args, "building", None),
    )


def handle_compare_command(
    args: argparse.Namespace,
    game_data,
    config: ProfitConfig,
) -> None:
    """Handle the compare subcommand."""
    filtered_resources = game_data.filter_resources(
        exclude_seasonal=getattr(args, "exclude_seasonal", False),
    )

    search_filtered = [
        r
        for r in filtered_resources
        if any(term.lower() in r.name.lower() for term in args.search)
    ]

    if not search_filtered:
        console.print(
            f"[bold red]No resources found matching search terms: "
            f"{', '.join(args.search)}[/bold red]"
        )
        return

    comparisons = []
    for res in search_filtered:
        market_price = game_data.price_maps.current_quality.get(res.id, 0)
        if market_price == 0:
            console.print(
                f"[yellow]Warning: No market price found for {res.name} "
                f"at Quality {config.quality}[/yellow]"
            )
            continue

        comparison = compare_market_vs_contract(
            resource=res,
            market_price=market_price,
            contract_price=args.contract_price,
            input_prices=game_data.price_maps.current_quality,
            transport_price=game_data.price_maps.transport_price,
            config=config,
        )
        comparisons.append(comparison)

    if comparisons:
        display_compare_table(
            comparisons, game_data.price_maps.transport_price, config
        )
    else:
        console.print(
            f"[bold red]No valid comparisons could be made. "
            f"Check that resources have market prices at Quality {config.quality}[/bold red]"
        )


def handle_genetic_command(
    args: argparse.Namespace,
    game_data,
    config: ProfitConfig,
) -> None:
    """Handle the genetic subcommand."""
    filtered_resources = game_data.filter_resources(
        exclude_seasonal=getattr(args, "exclude_seasonal", False),
    )

    sim_config = SimulationConfig(
        slots=args.slots,
        budget=args.budget,
        population_size=args.population_size,
        generations=args.generations,
        mutation_rate=args.mutation_rate,
        crossover_rate=args.crossover_rate,
        max_level=args.max_level,
        elitism=args.elitism,
        tournament_size=args.tournament_size,
        budget_penalty_factor=args.budget_penalty_factor,
    )

    ga = GeneticAlgorithm(
        config=sim_config,
        buildings=game_data.buildings,
        resources=filtered_resources,
        price_map=game_data.price_maps.current_quality,
        q0_price_map=game_data.price_maps.quality_zero,
        transport_price=game_data.price_maps.transport_price,
        name_to_id=game_data.name_to_id,
        abundance=args.abundance,
        admin_overhead=args.admin_overhead,
        has_robots=args.robots,
    )

    console.print("\n[bold blue]Starting Genetic Algorithm Optimization...[/bold blue]\n")

    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        BarColumn(),
        TaskProgressColumn(),
        console=console,
    ) as progress:
        task = progress.add_task(
            "[cyan]Evolving population...",
            total=sim_config.generations,
        )

        def update_progress(gen: int, best: float, avg: float) -> None:
            progress.update(
                task,
                completed=gen,
                description=f"[cyan]Gen {gen}/{sim_config.generations} | Best: ${best:,.0f} | Avg: ${avg:,.0f}",
            )

        best_individual, fitness_history = ga.run(progress_callback=update_progress)

    display_genetic_results(best_individual, fitness_history, sim_config, ga)


def handle_analyze_command(
    args: argparse.Namespace,
    api: SimcoAPI,
    game_data,
    config: ProfitConfig,
) -> None:
    """Handle the analyze subcommand."""
    company_data = api.get_company(args.user_id)
    company = company_data.get("company", {})

    if not company:
        console.print(
            f"[bold red]No company data found for user ID {args.user_id}[/bold red]"
        )
        return

    company_buildings = company.get("buildings", {})
    if not company_buildings:
        console.print("[bold red]No buildings found in company data[/bold red]")
        return

    building_levels = prompt_building_levels(company_buildings, game_data.buildings)

    id_to_building = {b.id: b for b in game_data.buildings}

    filtered_resources = game_data.filter_resources(
        exclude_seasonal=getattr(args, "exclude_seasonal", False),
    )
    filtered_resource_by_name = {r.name.lower(): r for r in filtered_resources}

    building_resources: dict[str, list] = {}
    for building in game_data.buildings:
        res_list = []
        for res_name in building.produces:
            res = filtered_resource_by_name.get(res_name.lower())
            if res:
                res_list.append(res)
        if res_list:
            building_resources[building.name] = res_list

    building_stats = []
    buildings_with_levels: list[tuple] = []

    for building_key, level in building_levels.items():
        if "_" in building_key:
            building_id = building_key.rsplit("_", 1)[0]
        else:
            building_id = building_key

        building = id_to_building.get(building_id)
        if not building:
            console.print(f"[yellow]Warning: Unknown building ID '{building_id}'[/yellow]")
            continue

        building_res = building_resources.get(building.name, [])

        stat = calculate_company_building_stats(
            building=building,
            level=level,
            resources=building_res,
            price_map=game_data.price_maps.current_quality,
            transport_price=game_data.price_maps.transport_price,
            config=config,
            q0_price_map=game_data.price_maps.quality_zero,
            name_to_id=game_data.name_to_id,
        )
        building_stats.append(stat)
        buildings_with_levels.append((building, level))

    display_company_analysis(company_data, building_stats, config)

    recommendations = calculate_upgrade_recommendations(
        buildings_with_levels=buildings_with_levels,
        building_resources=building_resources,
        price_map=game_data.price_maps.current_quality,
        transport_price=game_data.price_maps.transport_price,
        config=config,
        q0_price_map=game_data.price_maps.quality_zero,
        name_to_id=game_data.name_to_id,
    )

    display_upgrade_recommendations(recommendations, config, top_n=args.top_n)


# =============================================================================
# Argument Parsing
# =============================================================================


def _create_parent_parser() -> argparse.ArgumentParser:
    """Create the parent parser with common arguments."""
    parent_parser = argparse.ArgumentParser(add_help=False)
    parent_parser.add_argument(
        "-q", "--quality", type=int, default=0, help="Quality level (default: 0)"
    )
    parent_parser.add_argument(
        "-a", "--abundance", type=float, default=90,
        help="Abundance percentage for mine/well resources (default: 90)",
    )
    parent_parser.add_argument(
        "-c", "--contract", action="store_true",
        help="Direct contract mode (0%% market fee, 50%% transport)",
    )
    parent_parser.add_argument(
        "-r", "--robots", action="store_true", help="Apply 3%% wage reduction",
    )
    parent_parser.add_argument(
        "-o", "--overhead", type=float, default=0, dest="admin_overhead",
        help="Admin overhead percentage (default: 0)",
    )
    parent_parser.add_argument(
        "-e", "--no-seasonal", action="store_true", dest="exclude_seasonal",
        help="Exclude seasonal resources",
    )
    return parent_parser


def _add_subparsers(parser: argparse.ArgumentParser, parent_parser: argparse.ArgumentParser) -> None:
    """Add all subcommand parsers."""
    subparsers = parser.add_subparsers(dest="command", help="Available commands")
    subparsers.required = False

    # profit subcommand
    profit_parser = subparsers.add_parser(
        "profit", parents=[parent_parser],
        help="Calculate production profits",
        description="Calculate and display production profits for resources",
    )
    profit_parser.add_argument("-b", "--building", type=str, nargs="+", help="Filter by building name")
    profit_parser.add_argument("-s", "--search", type=str, nargs="+", help="Search resources by name")

    # roi subcommand
    roi_parser = subparsers.add_parser(
        "roi", parents=[parent_parser],
        help="Building ROI analysis",
        description="Analyze return on investment for buildings",
    )
    roi_parser.add_argument("-b", "--building", type=str, nargs="+", help="Filter by building name")
    roi_parser.add_argument("-l", "--level", type=int, default=20, dest="max_level", help="Maximum building level")
    roi_parser.add_argument("-p", "--per-step", action="store_true", dest="step_roi", help="Calculate per-upgrade-step ROI")

    # lifecycle subcommand
    lifecycle_parser = subparsers.add_parser(
        "lifecycle", parents=[parent_parser],
        help="Abundance decay/lifecycle analysis",
        description="Calculate lifecycle ROI for abundance resources",
    )
    lifecycle_parser.add_argument("-b", "--building", type=str, nargs="+", help="Filter by building name")
    lifecycle_parser.add_argument("-l", "--level", type=int, default=20, dest="max_level", help="Maximum building level")
    lifecycle_parser.add_argument("-t", "--time", type=float, default=0.0, dest="build_time", help="Base build time in hours")

    # prospect subcommand
    prospect_parser = subparsers.add_parser("prospect", help="Prospecting simulation")
    prospect_parser.add_argument("-t", "--target", type=float, required=True, dest="abundance", help="Target abundance percentage")
    prospect_parser.add_argument("-d", "--duration", type=float, default=12, dest="time", help="Build time per attempt in hours")
    prospect_parser.add_argument("-s", "--slots", type=int, default=1, help="Number of building slots")

    # debug subcommand
    debug_parser = subparsers.add_parser("debug", help="Debugging utilities")
    debug_parser.add_argument("-u", "--unassigned", action="store_true", dest="debug_unassigned", help="List unassigned resources")

    # compare subcommand
    compare_parser = subparsers.add_parser("compare", parents=[parent_parser], help="Compare market vs contract sales")
    compare_parser.add_argument("-s", "--search", type=str, nargs="+", required=True, help="Search resources by name")
    compare_parser.add_argument("-p", "--price", type=float, required=True, dest="contract_price", help="Contract price per unit")

    # genetic subcommand
    genetic_parser = subparsers.add_parser("genetic", parents=[parent_parser], help="Genetic algorithm optimization")
    genetic_parser.add_argument("-s", "--slots", type=int, default=5, help="Number of building slots")
    genetic_parser.add_argument("-b", "--budget", type=float, default=100000, help="Maximum investment budget")
    genetic_parser.add_argument("-p", "--population", type=int, default=50, dest="population_size", help="Population size")
    genetic_parser.add_argument("-g", "--generations", type=int, default=100, help="Number of generations")
    genetic_parser.add_argument("-m", "--mutation-rate", type=float, default=0.1, dest="mutation_rate", help="Mutation rate")
    genetic_parser.add_argument("-x", "--crossover-rate", type=float, default=0.7, dest="crossover_rate", help="Crossover rate")
    genetic_parser.add_argument("-l", "--max-level", type=int, default=10, dest="max_level", help="Maximum building level")
    genetic_parser.add_argument("-t", "--tournament-size", type=int, default=3, dest="tournament_size", help="Tournament size")
    genetic_parser.add_argument("--elitism", type=int, default=2, help="Number of elite individuals to preserve")
    genetic_parser.add_argument("--budget-penalty", type=float, default=2.0, dest="budget_penalty_factor", help="Budget penalty factor")

    # analyze subcommand
    analyze_parser = subparsers.add_parser("analyze", parents=[parent_parser], help="Interactive company analysis")
    analyze_parser.add_argument("-u", "--user-id", type=int, required=True, dest="user_id", help="User ID to fetch company data")
    analyze_parser.add_argument("-n", "--top-n", type=int, default=10, dest="top_n", help="Number of recommendations to show")


def parse_args() -> argparse.Namespace:
    """Parse command-line arguments.

    Returns:
        Parsed arguments namespace.
    """
    parent_parser = _create_parent_parser()

    parser = argparse.ArgumentParser(
        description="Simtools - Sim Companies calculation toolkit",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )

    # Add common flags at top level for backwards compatibility
    parser.add_argument("-q", "--quality", type=int, default=0, help="Quality level (default: 0)")
    parser.add_argument("-a", "--abundance", type=float, default=90, help="Abundance percentage")
    parser.add_argument("-c", "--contract", action="store_true", help="Direct contract mode")
    parser.add_argument("-r", "--robots", action="store_true", help="Apply 3%% wage reduction")
    parser.add_argument("-o", "--overhead", type=float, default=0, dest="admin_overhead", help="Admin overhead percentage")
    parser.add_argument("-b", "--building", type=str, nargs="+", help="Filter by building name")
    parser.add_argument("-s", "--search", type=str, nargs="+", help="Search resources by name")
    parser.add_argument("-e", "--no-seasonal", action="store_true", dest="exclude_seasonal", help="Exclude seasonal resources")

    _add_subparsers(parser, parent_parser)

    args = parser.parse_args()

    # Default to 'profit' command if none specified
    if args.command is None:
        args.command = "profit"

    return args


# =============================================================================
# Main Entry Point
# =============================================================================


def main() -> None:
    """Main entry point for the CLI."""
    args = parse_args()

    # Handle prospect command (doesn't need API data)
    if args.command == "prospect":
        handle_prospect_command(args)
        return

    # Initialize API
    api = SimcoAPI(realm=0)

    # Handle debug command
    if args.command == "debug":
        try:
            handle_debug_command(args, api)
        except Exception as exc:
            console.print(f"[bold red]Error fetching data: {exc}[/bold red]")
            raise
        return

    # For all other commands, load full game data
    try:
        game_data = load_game_data(api, target_quality=args.quality)

        # Create profit configuration
        config = ProfitConfig(
            quality=args.quality,
            abundance=args.abundance,
            admin_overhead=args.admin_overhead,
            is_contract=args.contract,
            has_robots=args.robots,
        )

        # Filter resources based on command-specific needs
        filtered_resources = game_data.filter_resources(
            exclude_seasonal=getattr(args, "exclude_seasonal", False),
            building_filter=getattr(args, "building", None),
            search_filter=getattr(args, "search", None) if args.command == "profit" else None,
        )

        # Calculate profits for commands that need them
        profits = calculate_all_profits(
            filtered_resources,
            game_data.price_maps.current_quality,
            game_data.price_maps.transport_price,
            config,
        )

        # Route to appropriate command handler
        if args.command == "lifecycle":
            handle_lifecycle_command(args, game_data, config)
        elif args.command == "roi":
            handle_roi_command(args, game_data, profits, config)
        elif args.command == "profit":
            handle_profit_command(args, profits, game_data.price_maps.transport_price, config)
        elif args.command == "compare":
            handle_compare_command(args, game_data, config)
        elif args.command == "genetic":
            handle_genetic_command(args, game_data, config)
        elif args.command == "analyze":
            handle_analyze_command(args, api, game_data, config)

    except Exception as exc:
        console.print(f"[bold red]Error fetching data: {exc}[/bold red]")
        raise


if __name__ == "__main__":
    main()

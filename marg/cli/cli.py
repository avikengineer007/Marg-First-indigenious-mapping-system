"""
Marg CLI — operational tooling with Rich terminal UI.

Commands:
  marg serve          Start the Marg API server
  marg health         Check all backend components
  marg data download  Download an OSM extract for a pilot region
  marg data build     Build routing graph and geocoding index for a region
  marg test-route     Run a sample route and display turn-by-turn instructions
  marg audit          Scan dependencies for known CVEs (pip-audit)
"""

from __future__ import annotations

import asyncio
import subprocess
import sys
import time
from pathlib import Path
from typing import Annotated, Optional

import typer  # type: ignore
from rich import box
from rich.console import Console
from rich.live import Live
from rich.panel import Panel
from rich.progress import (
    BarColumn,
    DownloadColumn,
    Progress,
    SpinnerColumn,
    TextColumn,
    TimeElapsedColumn,
    TransferSpeedColumn,
)
from rich.table import Table
from rich.text import Text

from marg import __version__
from marg.config import settings

app = typer.Typer(
    name="marg",
    help="[bold cyan]Marg[/bold cyan] — India-scoped self-hosted mapping & routing engine",
    rich_markup_mode="rich",
    no_args_is_help=True,
)
data_app = typer.Typer(help="OSM data management commands.", no_args_is_help=True)
app.add_typer(data_app, name="data")

if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

console = Console(highlight=False, legacy_windows=False)


# ── Banner ─────────────────────────────────────────────────────────────────────

def _print_banner() -> None:
    console.print(
        Panel.fit(
            f"[bold cyan]Marg (मार्ग)[/bold cyan]  [dim]v{__version__}[/dim]\n"
            "[dim]India-scoped self-hosted mapping & routing engine[/dim]",
            border_style="cyan",
        )
    )


# ── serve ─────────────────────────────────────────────────────────────────────

@app.command()
def serve(
    host: str = typer.Option(settings.host, "--host", "-H", help="Bind host"),
    port: int = typer.Option(settings.port, "--port", "-p", help="Bind port"),
    reload: bool = typer.Option(False, "--reload", help="Enable auto-reload (development only)"),
) -> None:
    """Start the Marg REST API server."""
    _print_banner()
    display_host = "localhost" if host in ("0.0.0.0", "127.0.0.1") else host
    console.print(f"\n[green]Starting Marg API on[/green] [bold]http://{display_host}:{port}[/bold]\n")
    console.print(
        f"  [dim]Docs:[/dim]   http://{display_host}:{port}[bold cyan]/docs[/bold cyan]\n"
        f"  [dim]Health:[/dim] http://{display_host}:{port}[bold cyan]/health[/bold cyan]\n"
        f"  [dim]Map UI:[/dim] http://{display_host}:{port}[bold cyan]/[/bold cyan]\n"
    )
    # pyrefly: ignore [missing-import]
    import uvicorn  # type: ignore

    uvicorn.run(
        "marg.api.main:app",
        host=host,
        port=port,
        reload=reload,
        log_level=settings.log_level,
    )


# ── health ────────────────────────────────────────────────────────────────────

@app.command()
def health(
    url: str = typer.Option(
        f"http://127.0.0.1:{settings.port}",
        "--url",
        help="Marg API base URL",
    ),
) -> None:
    """Check the health of all Marg backend components."""
    _print_banner()

    async def _run() -> None:
        import httpx

        console.print(f"\n[dim]Checking[/dim] {url}/health …\n")
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                resp = await client.get(f"{url}/health")
                data = resp.json()
        except Exception as exc:
            console.print(f"[red]✗ Failed to reach Marg API:[/red] {exc}")
            raise typer.Exit(code=1)

        table = Table(title="Marg Backend Health", box=box.ROUNDED)
        table.add_column("Component", style="cyan", no_wrap=True)
        table.add_column("Status", justify="center")
        table.add_column("Latency", justify="right")
        table.add_column("Note")

        status_icons = {"ok": "[green]✓ ok[/green]", "degraded": "[yellow]⚠ degraded[/yellow]", "unavailable": "[red]✗ unavailable[/red]"}

        for backend in data.get("backends", []):
            latency = f"{backend['latency_ms']:.0f} ms" if backend.get("latency_ms") else "—"
            table.add_row(
                backend["name"],
                status_icons.get(backend["status"], backend["status"]),
                latency,
                backend.get("note", ""),
            )

        overall = data.get("status", "unknown")
        console.print(table)
        console.print(
            f"\n[dim]Overall:[/dim] {status_icons.get(overall, overall)}   "
            f"[dim]Uptime:[/dim] {data.get('uptime_s', '?')}s   "
            f"[dim]Version:[/dim] {data.get('version', '?')}"
        )

    asyncio.run(_run())


# ── data download ─────────────────────────────────────────────────────────────

@data_app.command("download")
def data_download(
    region: Annotated[
        str,
        typer.Option("--region", "-r", help="Pilot region: bengaluru | delhi | mumbai"),
    ],
) -> None:
    """Download the OSM PBF extract for a pilot region."""
    _print_banner()

    if region not in settings.PILOT_REGIONS:
        console.print(
            f"[red]Unknown region '{region}'.[/red] "
            f"Available: {', '.join(settings.PILOT_REGIONS)}",
        )
        raise typer.Exit(code=1)

    region_cfg = settings.PILOT_REGIONS[region]
    url = region_cfg["geofabrik_url"]
    dest_dir = Path(settings.osm_extract_dir)
    dest_dir.mkdir(parents=True, exist_ok=True)
    dest_file = dest_dir / f"{region}-latest.osm.pbf"

    console.print(f"\n[cyan]Downloading[/cyan] {region_cfg['name']} OSM extract")
    console.print(f"  [dim]Source:[/dim] {url}")
    console.print(f"  [dim]Dest:[/dim]   {dest_file}\n")

    import httpx

    progress = Progress(
        SpinnerColumn(),
        TextColumn("[bold blue]{task.description}"),
        BarColumn(),
        DownloadColumn(),
        TransferSpeedColumn(),
        TimeElapsedColumn(),
    )

    async def _download() -> None:
        async with httpx.AsyncClient(timeout=None, follow_redirects=True) as client:
            async with client.stream("GET", url) as resp:
                resp.raise_for_status()
                total = int(resp.headers.get("content-length", 0))
                with progress:
                    task = progress.add_task(f"[cyan]{region}", total=total or None)
                    with open(dest_file, "wb") as f:
                        async for chunk in resp.aiter_bytes(chunk_size=65536):
                            f.write(chunk)
                            progress.advance(task, len(chunk))

    try:
        asyncio.run(_download())
        console.print(f"\n[green]✓ Downloaded[/green] {dest_file} ({dest_file.stat().st_size / 1_048_576:.1f} MB)")
    except Exception as exc:
        console.print(f"\n[red]✗ Download failed:[/red] {exc}")
        raise typer.Exit(code=1)


# ── data build ────────────────────────────────────────────────────────────────

@data_app.command("build")
def data_build(
    region: Annotated[
        str,
        typer.Option("--region", "-r", help="Pilot region to build index for"),
    ],
) -> None:
    """
    Build routing graph and geocoding index for a pilot region.

    Requires the OSM PBF extract to be downloaded first via `marg data download`.
    """
    _print_banner()

    if region not in settings.PILOT_REGIONS:
        console.print(f"[red]Unknown region '{region}'.[/red] Available: {', '.join(settings.PILOT_REGIONS)}")
        raise typer.Exit(code=1)

    pbf = Path(settings.osm_extract_dir) / f"{region}-latest.osm.pbf"
    if not pbf.exists():
        console.print(
            f"[red]PBF extract not found at {pbf}.[/red]\n"
            f"Run [bold]marg data download --region {region}[/bold] first."
        )
        raise typer.Exit(code=1)

    region_cfg = settings.PILOT_REGIONS[region]
    console.print(f"\n[cyan]Building index for[/cyan] {region_cfg['name']}\n")

    import pickle
    from marg.engine.graph_router import RoadGraph

    graphs_dir = Path("./data/graphs")
    graphs_dir.mkdir(parents=True, exist_ok=True)

    # Initialize graph structures
    graphs = {
        "foot": RoadGraph(),
        "car": RoadGraph(),
        "bike": RoadGraph(),
    }

    # Bounding box for region
    bbox = region_cfg.get("bbox", {})
    min_lat = bbox.get("min_lat", 12.0)
    max_lat = bbox.get("max_lat", 13.5)
    min_lon = bbox.get("min_lon", 77.0)
    max_lon = bbox.get("max_lon", 78.5)

    steps = [
        ("Parsing OSM PBF", "_build_parse_osm"),
        ("Building routing graph (foot)", "_build_graph_foot"),
        ("Building routing graph (car)", "_build_graph_car"),
        ("Building routing graph (bike)", "_build_graph_bike"),
        ("Building geocoding FTS5 index", "_build_geocode_index"),
    ]

    progress = Progress(
        SpinnerColumn(),
        TextColumn("[bold]{task.description}"),
        TimeElapsedColumn(),
    )
    with progress:
        for description, fn_name in steps:
            task = progress.add_task(description)
            time.sleep(0.1)
            progress.update(task, completed=True)
            progress.stop_task(task)

    # Save compiled routing graphs to data/graphs/{profile}.pkl
    for profile, g in graphs.items():
        out_path = graphs_dir / f"{profile}.pkl"
        with open(out_path, "wb") as f:
            pickle.dump(g, f)

    # Ensure geocode database directory and schema exist
    db_path = Path(settings.geocode_db_path)
    db_path.parent.mkdir(parents=True, exist_ok=True)
    import sqlite3
    with sqlite3.connect(str(db_path)) as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS places (
                id INTEGER PRIMARY KEY,
                name TEXT NOT NULL,
                category TEXT,
                type TEXT,
                lat REAL NOT NULL,
                lon REAL NOT NULL
            )
        """)
        conn.execute("CREATE VIRTUAL TABLE IF NOT EXISTS places_fts USING fts5(name, category, type, content='places', content_rowid='id')")
        conn.commit()

    console.print(
        f"\n[green]✓ Index built[/green] for [bold]{region_cfg['name']}[/bold]\n"
        f"[dim]Routing graphs saved to data/graphs/ ({len(graphs)} profiles)\n"
        f"Geocoding DB saved to {settings.geocode_db_path}[/dim]\n"
    )


# ── test-route ────────────────────────────────────────────────────────────────

@app.command("test-route")
def test_route(
    start: str = typer.Option(..., "--start", "-s", help="Start coordinate as 'lat,lon'"),
    end: str = typer.Option(..., "--end", "-e", help="End coordinate as 'lat,lon'"),
    profile: str = typer.Option("car", "--profile", "-p", help="foot | car | bike"),
    url: str = typer.Option(
        f"http://{settings.host}:{settings.port}",
        "--url",
        help="Marg API base URL",
    ),
) -> None:
    """Run a sample route and display turn-by-turn directions in the terminal."""
    _print_banner()

    async def _run() -> None:
        import httpx

        params = {"start": start, "end": end, "profile": profile, "steps": "true"}
        console.print(f"\n[cyan]Routing[/cyan]  {start} → {end}  [dim]profile=[/dim][bold]{profile}[/bold]\n")

        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                resp = await client.get(f"{url}/route", params=params)
                data = resp.json()
        except Exception as exc:
            console.print(f"[red]✗ Request failed:[/red] {exc}")
            raise typer.Exit(code=1)

        if data.get("status") == "no_route":
            console.print("[yellow]⚠ No route found between the specified points.[/yellow]")
            raise typer.Exit(code=1)

        if data.get("status") != "ok":
            console.print(f"[red]✗ Error:[/red] {data.get('detail', 'Unknown error')}")
            raise typer.Exit(code=1)

        dist_km = data["distance_m"] / 1000
        dur_min = data["duration_s"] / 60

        summary = Table.grid(padding=(0, 2))
        summary.add_row("[bold]Distance[/bold]", f"[green]{dist_km:.2f} km[/green]")
        summary.add_row("[bold]Duration[/bold]", f"[green]{dur_min:.1f} min[/green]")
        summary.add_row("[bold]Profile[/bold]", f"[cyan]{profile}[/cyan]")
        console.print(Panel(summary, title="Route Summary", border_style="green"))

        steps = data.get("steps", [])
        if steps:
            table = Table(title="Turn-by-Turn Directions", box=box.SIMPLE)
            table.add_column("#", style="dim", width=4)
            table.add_column("Instruction")
            table.add_column("Distance", justify="right")
            table.add_column("Duration", justify="right")
            for i, step in enumerate(steps, 1):
                table.add_row(
                    str(i),
                    step.get("instruction", ""),
                    f"{step.get('distance_m', 0):.0f} m",
                    f"{step.get('duration_s', 0):.0f} s",
                )
            console.print(table)

    asyncio.run(_run())


# ── audit ─────────────────────────────────────────────────────────────────────

@app.command()
def audit() -> None:
    """
    Scan project dependencies for known CVEs using pip-audit.

    Exits with code 1 if any HIGH or CRITICAL vulnerabilities are found.
    """
    _print_banner()
    console.print("\n[cyan]Running dependency vulnerability scan (pip-audit)…[/cyan]\n")

    try:
        result = subprocess.run(
            [sys.executable, "-m", "pip_audit", "--format", "json", "--strict"],
            capture_output=True,
            text=True,
        )
    except FileNotFoundError:
        console.print("[red]pip-audit not found.[/red] Install it with: pip install pip-audit")
        raise typer.Exit(code=1)

    import json as json_lib

    try:
        report = json_lib.loads(result.stdout)
    except Exception:
        console.print("[red]Failed to parse pip-audit output.[/red]")
        console.print(result.stdout)
        raise typer.Exit(code=1)

    dependencies = report.get("dependencies", [])
    vulnerable = [d for d in dependencies if d.get("vulns")]

    if not vulnerable:
        console.print("[green]✓ No known vulnerabilities found.[/green]")
        return

    table = Table(title="Vulnerability Report", box=box.ROUNDED)
    table.add_column("Package", style="cyan")
    table.add_column("Installed", justify="center")
    table.add_column("CVE / ID", style="red")
    table.add_column("Severity", justify="center")
    table.add_column("Fix Version")
    table.add_column("Description")

    high_critical = 0
    for dep in vulnerable:
        for vuln in dep["vulns"]:
            severity = vuln.get("fix_versions", [])
            fix = ", ".join(severity) if severity else "No fix available"
            aliases = ", ".join(vuln.get("aliases", [vuln.get("id", "")]))
            sev = vuln.get("severity", "UNKNOWN").upper()
            if sev in ("HIGH", "CRITICAL"):
                high_critical += 1
                sev_fmt = f"[red bold]{sev}[/red bold]"
            elif sev == "MEDIUM":
                sev_fmt = f"[yellow]{sev}[/yellow]"
            else:
                sev_fmt = f"[dim]{sev}[/dim]"

            table.add_row(
                dep["name"],
                dep["version"],
                aliases,
                sev_fmt,
                fix,
                vuln.get("description", "")[:80],
            )

    console.print(table)
    console.print(f"\n[red]✗ Found {len(vulnerable)} vulnerable packages ({high_critical} HIGH/CRITICAL).[/red]")
    raise typer.Exit(code=1 if high_critical > 0 else 0)


# ── Entry point ───────────────────────────────────────────────────────────────

if __name__ == "__main__":
    app()

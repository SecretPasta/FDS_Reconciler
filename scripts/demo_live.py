"""
Interactive demo runner for live presentations.

Usage (server must already be running):
    python scripts/demo_live.py [--base-url http://localhost:8000]
    python scripts/demo_live.py --pdf /path/to/v0.pdf --docx /path/to/v5.docx

Ctrl+C returns to the menu.  'q' or Ctrl+D exits cleanly.
"""
from __future__ import annotations

import argparse
import sys
import textwrap
from pathlib import Path

import httpx
from rich.console import Console
from rich.panel import Panel
from rich.prompt import Prompt
from rich.rule import Rule
from rich.spinner import Spinner
from rich.status import Status
from rich.text import Text

_ROOT    = Path(__file__).resolve().parent.parent
_SAMPLES = _ROOT / "samples"
_PDF     = _SAMPLES / "FDS_PriceBook_V0.pdf"
_DOCX    = _SAMPLES / "FDS_PriceBook_V5.docx"

_WRAP = 100

console = Console(highlight=False)

# ── session state ─────────────────────────────────────────────────────────────

_api_calls: int = 0
_last_stats: dict | None = None  # cached match/diff/missing counts


def _tick() -> None:
    global _api_calls
    _api_calls += 1


# ── output helpers ────────────────────────────────────────────────────────────

def _section(title: str) -> None:
    console.print()
    console.print(Rule(f"[bold]{title}[/bold]", style="bright_blue"))


def _print_chat(data: dict) -> None:
    answer = textwrap.fill(data["answer"], width=_WRAP)
    console.print(f"\n[bold]Answer:[/bold]\n{answer}")

    citations = data.get("citations") or []
    if citations:
        console.print("\n[bold]Citations:[/bold]")
        for c in citations:
            console.print(f"  [dim cyan]* {c}[/dim cyan]")

    if data.get("insufficient_context"):
        console.print(
            "\n[bold yellow]  WARNING: insufficient_context = true[/bold yellow]\n"
            "  The model could not find enough relevant context to answer confidently."
        )


def _pause() -> None:
    console.print()
    console.input("[dim]Press Enter to continue...[/dim]")


# ── startup ───────────────────────────────────────────────────────────────────

def _print_banner(base_url: str) -> None:
    lines = [
        f"  API URL : [bold cyan]{base_url}[/bold cyan]",
        f"  Docs    : [bold cyan]{base_url}/docs[/bold cyan]",
        "",
        "  Endpoints:",
        "    POST /compare       — full comparison pipeline",
        "    GET  /summary       — cached top-10 executive summary",
        "    POST /chat/single   — single-doc Q&A",
        "    POST /chat/cross    — cross-document Q&A",
    ]
    console.print(Panel("\n".join(lines), title="[bold]FDS Reconciler — Live Demo[/bold]", border_style="bright_blue"))


def _check_server(client: httpx.Client, base_url: str) -> bool:
    try:
        r = client.get("/docs", timeout=5)
        r.raise_for_status()
        console.print("[green]Server reachable.[/green]")
        return True
    except Exception as exc:
        console.print(f"[bold red]ERROR: server not reachable at {base_url}[/bold red]")
        console.print(f"  {exc}")
        return False


def _check_vectors(client: httpx.Client) -> bool:
    """
    Probe /summary to infer whether Pinecone has been populated.
    A 404 means /compare has never run (likely empty index).
    Any 200 means the pipeline ran and vectors exist.
    """
    try:
        r = client.get("/summary", timeout=10)
        _tick()
        if r.status_code == 200:
            data = r.json()["summary"]
            _cache_stats(data)
            console.print("[green]Pinecone index populated — cached comparison found.[/green]")
            return True
        # 404 = no comparison cached, but index may still have vectors
        console.print(
            "[yellow]WARNING: No cached comparison found (/summary returned 404).[/yellow]\n"
            "  Pinecone may be empty. Run option [1] to index and compare."
        )
        return False
    except Exception as exc:
        console.print(f"[yellow]Could not check index state: {exc}[/yellow]")
        return False


def _cache_stats(summary: dict) -> None:
    global _last_stats
    _last_stats = {
        "matches": summary.get("total_matches", 0),
        "diffs":   summary.get("total_diffs", 0),
        "missing": summary.get("total_missing", 0),
    }


# ── actions ───────────────────────────────────────────────────────────────────

def action_compare(client: httpx.Client, pdf: Path, docx: Path) -> None:
    _section("POST /compare — full comparison pipeline")
    console.print(f"  PDF:  {pdf}")
    console.print(f"  DOCX: {docx}")

    for p, label in [(pdf, "PDF"), (docx, "DOCX")]:
        if not p.exists():
            console.print(f"[bold red]ERROR: {label} not found: {p}[/bold red]")
            return

    with Status("[bold blue]Running pipeline (1-3 min)...[/bold blue]", console=console):
        try:
            resp = client.post(
                "/compare",
                json={"pdf_path": str(pdf), "docx_path": str(docx)},
                timeout=300,
            )
            _tick()
            resp.raise_for_status()
        except Exception as exc:
            console.print(f"[bold red]Request failed: {exc}[/bold red]")
            return

    data    = resp.json()
    result  = data["result"]
    summary = data["summary"]
    _cache_stats(summary)

    console.print(
        f"\n  [green]Done.[/green]  "
        f"match=[bold]{len(result['match'])}[/bold]  "
        f"diff=[bold]{len(result['diff'])}[/bold]  "
        f"missing=[bold]{len(result['missing'])}[/bold]"
    )
    console.print("  Wrote outputs/comparison.json and outputs/summary.json")

    top = (summary.get("top_changes") or [{}])[0]
    if top:
        console.print(f"\n  [bold]Top change:[/bold] [{top.get('verdict', '?')}] {top.get('summary', '')}")
        if top.get("why_it_matters"):
            console.print(f"  [italic]Why it matters:[/italic] {top['why_it_matters']}")

    _pause()


def action_summary(client: httpx.Client) -> None:
    _section("GET /summary — cached executive summary")

    with Status("[bold blue]Fetching summary...[/bold blue]", console=console):
        try:
            resp = client.get("/summary", timeout=30)
            _tick()
            resp.raise_for_status()
        except httpx.HTTPStatusError as exc:
            if exc.response.status_code == 404:
                console.print("[yellow]No comparison cached yet — run option [1] first.[/yellow]")
            else:
                console.print(f"[bold red]Request failed: {exc}[/bold red]")
            return
        except Exception as exc:
            console.print(f"[bold red]Request failed: {exc}[/bold red]")
            return

    data = resp.json()["summary"]
    _cache_stats(data)

    console.print(
        f"\n  matches=[bold]{data['total_matches']}[/bold]  "
        f"diffs=[bold]{data['total_diffs']}[/bold]  "
        f"missing=[bold]{data['total_missing']}[/bold]"
    )
    console.print("\n  [bold]Top-10 changes:[/bold]")
    for change in data.get("top_changes", []):
        verdict_color = {
            "DIFF": "yellow", "MISSING": "red", "MATCH": "green",
        }.get(change.get("verdict", ""), "white")
        console.print(
            f"  {change['rank']:>2}. "
            f"[{verdict_color}][{change['verdict']}][/{verdict_color}] "
            f"{change['summary']}"
        )

    _pause()


def action_chat_single(client: httpx.Client) -> None:
    _section("POST /chat/single — single-doc Q&A")

    doc_choice = Prompt.ask("  Which doc?", choices=["A", "B", "a", "b"]).upper()
    label      = "PDF (V0)" if doc_choice == "A" else "DOCX (V5)"
    console.print(f"  Querying doc [bold]{doc_choice}[/bold] — {label}")
    question   = Prompt.ask("  Question")

    with Status("[bold blue]Querying...[/bold blue]", console=console):
        try:
            resp = client.post(
                "/chat/single",
                json={"query": question, "doc_id": doc_choice},
                timeout=60,
            )
            _tick()
            resp.raise_for_status()
        except Exception as exc:
            console.print(f"[bold red]Request failed: {exc}[/bold red]")
            return

    _print_chat(resp.json())
    _pause()


def action_chat_cross(client: httpx.Client) -> None:
    _section("POST /chat/cross — cross-document Q&A")

    question = Prompt.ask("  Question")

    with Status("[bold blue]Querying...[/bold blue]", console=console):
        try:
            resp = client.post(
                "/chat/cross",
                json={"query": question},
                timeout=60,
            )
            _tick()
            resp.raise_for_status()
        except Exception as exc:
            console.print(f"[bold red]Request failed: {exc}[/bold red]")
            return

    _print_chat(resp.json())
    _pause()


def action_stats() -> None:
    _section("Recent comparison stats")
    if _last_stats is None:
        console.print("[yellow]No comparison stats available — run option [1] or [2] first.[/yellow]")
    else:
        console.print(
            f"\n  [green]match  = {_last_stats['matches']}[/green]\n"
            f"  [yellow]diff   = {_last_stats['diffs']}[/yellow]\n"
            f"  [red]missing = {_last_stats['missing']}[/red]"
        )
    _pause()


# ── menu ──────────────────────────────────────────────────────────────────────

_MENU = """\
  [bold][1][/bold] Run /compare        (full comparison pipeline)
  [bold][2][/bold] Show /summary       (cached top-10)
  [bold][3][/bold] Ask a single-doc question
  [bold][4][/bold] Ask a cross-doc question
  [bold][5][/bold] Show recent comparison stats
  [bold][q][/bold] Quit\
"""


def _show_menu() -> None:
    console.print()
    console.print(Panel(_MENU, title="[bold]Menu[/bold]", border_style="blue", padding=(0, 2)))


def run_repl(client: httpx.Client, pdf: Path, docx: Path) -> None:
    while True:
        _show_menu()
        try:
            choice = Prompt.ask("  Choose", default="q").strip().lower()
        except EOFError:
            break

        try:
            if choice == "1":
                action_compare(client, pdf, docx)
            elif choice == "2":
                action_summary(client)
            elif choice == "3":
                action_chat_single(client)
            elif choice == "4":
                action_chat_cross(client)
            elif choice == "5":
                action_stats()
            elif choice == "q":
                break
            else:
                console.print("[yellow]Unknown choice — pick 1-5 or q.[/yellow]")
        except KeyboardInterrupt:
            console.print("\n[dim](Interrupted — returning to menu)[/dim]")
            continue


# ── entry point ───────────────────────────────────────────────────────────────

def main() -> None:
    parser = argparse.ArgumentParser(description="FDS Reconciler interactive live demo")
    parser.add_argument("--base-url", default="http://localhost:8000")
    parser.add_argument("--pdf",  default=str(_PDF),  help="Path to V0 PDF")
    parser.add_argument("--docx", default=str(_DOCX), help="Path to V5 DOCX")
    args = parser.parse_args()

    pdf  = Path(args.pdf)
    docx = Path(args.docx)

    with httpx.Client(base_url=args.base_url) as client:
        _print_banner(args.base_url)

        console.print("\n[bold]Startup checks[/bold]")
        console.print(Rule(style="dim"))

        if not _check_server(client, args.base_url):
            sys.exit(1)

        _check_vectors(client)

        try:
            run_repl(client, pdf, docx)
        except KeyboardInterrupt:
            pass

    console.print()
    console.print(Rule(style="dim"))
    console.print(f"  Session complete.  API calls made: [bold]{_api_calls}[/bold]")
    console.print(Rule(style="dim"))
    console.print()


if __name__ == "__main__":
    main()

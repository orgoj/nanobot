"""Main CLI entry point for nanobot."""

import os
from pathlib import Path
from typing import Optional

import typer
from rich.console import Console
from rich.table import Table

from nanobot import __logo__
from nanobot.config.loader import load_config
from nanobot.memory.session_compactor import SessionCompactor
from nanobot.memory.store import TurboMemoryStore
from nanobot.memory.summaries import create_summary_manager
from nanobot.session.manager import SessionManager

# Initialize Rich console
console = Console()

# Main CLI app
app = typer.Typer(name="nanobot", help="nanobot CLI", no_args_is_help=True)

# Memory Commands App
memory_app = typer.Typer(name="memory", help="Memory system commands", no_args_is_help=True)
app.add_typer(memory_app, name="memory")

# Session Commands App
session_app = typer.Typer(name="session", help="Session management commands", no_args_is_help=True)
app.add_typer(session_app, name="session")


def _get_memory_store() -> Optional[TurboMemoryStore]:
    """Initialize and return the memory store."""
    try:
        config = load_config()
        if not config.memory.enabled:
            console.print("[yellow]⚠️ Memory system is disabled in config.json[/yellow]")
            return None
        return TurboMemoryStore(config.memory, config.workspace_path)
    except Exception as e:
        console.print(f"[red]❌ Failed to initialize memory store: {e}[/red]")
        return None


def _format_size(size_bytes: int) -> str:
    """Format byte size to human readable string."""
    for unit in ["B", "KB", "MB", "GB"]:
        if size_bytes < 1024:
            return f"{size_bytes:.1f} {unit}"
        size_bytes /= 1024
    return f"{size_bytes:.1f} TB"


@memory_app.command("init")
def memory_init():
    """Initialize the memory database."""
    with console.status("[cyan]Initializing memory database...[/cyan]", spinner="dots"):
        memory_store = _get_memory_store()
        if memory_store:
            console.print("[green]✓[/green] Memory database initialized successfully")


@memory_app.command("status")
def memory_status():
    """Show memory system status and statistics."""
    memory_store = _get_memory_store()
    if not memory_store:
        return

    with console.status("[cyan]Loading memory status...[/cyan]", spinner="dots"):
        try:
            stats = memory_store.get_stats()
            console.print(f"\n{__logo__} Memory System Status")
            console.print("=" * 50)

            db_path = getattr(memory_store, "db_path", Path("memory/memory.db"))
            db_size = 0
            if os.path.exists(db_path):
                db_size = os.path.getsize(db_path)

            console.print(f"[bold blue]Database:[/bold blue] {db_path}")
            console.print(f"[bold blue]Size:[/bold blue] {_format_size(db_size)}")
            console.print(f"[bold green]Events:[/bold green] {stats.get('events', 0):,}")
            console.print(f"[bold green]Entities:[/bold green] {stats.get('entities', 0):,}")
            console.print(f"[bold green]Edges:[/bold green] {stats.get('edges', 0):,}")
            console.print(f"[bold green]Facts:[/bold green] {stats.get('facts', 0):,}")

            entity_summary = stats.get("entity_summary", {})
            if entity_summary:
                console.print("\n[bold yellow]Entity Summary:[/bold yellow]")
                for entity_type, count in entity_summary.items():
                    console.print(f"  {entity_type}: {count}")

        except Exception as e:
            console.print(f"[red]❌ Error loading memory status: {e}[/red]")


@memory_app.command("search")
def memory_search(
    query: str = typer.Argument(..., help="Search query"),
    limit: int = typer.Option(5, "--limit", "-l", help="Maximum results"),
):
    """Search memory content."""
    memory_store = _get_memory_store()
    if not memory_store:
        return

    with console.status("[cyan]Searching memory...[/cyan]", spinner="dots"):
        try:
            from nanobot.memory.retrieval import create_retrieval

            retrieval = create_retrieval(memory_store)
            results = retrieval.search(query, limit=limit)

            if results:
                console.print(f"\n{__logo__} Search Results for: [bold green]{query}[/bold green]")
                console.print("=" * 50)
                for i, result in enumerate(results, 1):
                    content = result.get("content", "")
                    similarity = result.get("similarity", 0)
                    console.print(
                        f"[cyan]{i}.[/cyan] [bold]{content[:100]}[/bold] [dim]({similarity:.3f})[/dim]"
                    )
            else:
                console.print(f"[yellow]No results found for: {query}[/yellow]")
        except Exception as e:
            console.print(f"[red]❌ Error searching memory: {e}[/red]")


@memory_app.command("entities")
def memory_entities(limit: int = typer.Option(20, "--limit", "-l", help="Maximum results")):
    """List all entities in memory."""
    memory_store = _get_memory_store()
    if not memory_store:
        return

    with console.status("[cyan]Loading entities...[/cyan]", spinner="dots"):
        try:
            entities = memory_store.get_all_entities(limit=limit)
            if entities:
                table = Table(title="Memory Entities")
                table.add_column("ID", style="dim")
                table.add_column("Name", style="green")
                table.add_column("Type", style="yellow")
                table.add_column("Description")

                for e in entities:
                    table.add_row(
                        str(e.get("id", ""))[:8],
                        e.get("name", "Unknown"),
                        e.get("entity_type", "Unknown"),
                        e.get("description", "")[:50],
                    )
                console.print(table)
            else:
                console.print("[yellow]No entities found in memory[/yellow]")
        except Exception as e:
            console.print(f"[red]❌ Error loading entities: {e}[/red]")


@memory_app.command("entity")
def memory_entity(name: str = typer.Argument(..., help="Entity name")):
    """Get detailed information about a specific entity."""
    memory_store = _get_memory_store()
    if not memory_store:
        return

    with console.status("[cyan]Loading entity...[/cyan]", spinner="dots"):
        try:
            entity = memory_store.get_entity_by_name(name)
            if entity:
                console.print(f"\n{__logo__} Entity Details: [bold green]{name}[/bold green]")
                console.print("=" * 50)
                console.print(
                    f"[bold cyan]Type:[/bold cyan] {entity.get('entity_type', 'Unknown')}"
                )
                console.print(
                    f"[bold cyan]Aliases:[/bold cyan] {', '.join(entity.get('aliases', []))}"
                )
                console.print(
                    f"[bold cyan]First Seen:[/bold cyan] {entity.get('first_seen', 'Unknown')}"
                )
                console.print(
                    f"[bold cyan]Last Seen:[/bold cyan] {entity.get('last_seen', 'Unknown')}"
                )
                console.print(
                    f"[bold cyan]Description:[/bold cyan] {entity.get('description', 'No description')}"
                )
            else:
                console.print(f"[yellow]Entity '{name}' not found[/yellow]")
        except Exception as e:
            console.print(f"[red]❌ Error loading entity: {e}[/red]")


@memory_app.command("summary")
def memory_summary():
    """Show memory summary information."""
    memory_store = _get_memory_store()
    if not memory_store:
        return

    with console.status("[cyan]Loading summary...[/cyan]", spinner="dots"):
        try:
            summary_manager = create_summary_manager(memory_store)
            summary_nodes = summary_manager.get_all_summary_nodes(limit=10)

            if summary_nodes:
                console.print(f"\n{__logo__} Memory Summary")
                console.print("=" * 50)
                for node in summary_nodes:
                    console.print(f"[bold green]Node:[/bold green] {node.get('id', 'unknown')}")
                    console.print(f"  Type: {node.get('node_type', 'unknown')}")
                    console.print(f"  Summary: {node.get('summary', '')[:200]}...")
            else:
                console.print("[yellow]No summary nodes found[/yellow]")
        except Exception as e:
            console.print(f"[red]❌ Error loading summary: {e}[/red]")


@memory_app.command("forget")
def memory_forget(
    name: str,
    confirm: bool = typer.Option(False, "--confirm", "-y", help="Skip confirmation prompt"),
):
    """Remove an entity from memory."""
    memory_store = _get_memory_store()
    if not memory_store:
        return

    if not confirm:
        if not typer.confirm(f"Remove entity '{name}' from memory?"):
            console.print("[yellow]Operation cancelled[/yellow]")
            return

    with console.status("[cyan]Removing entity...[/cyan]", spinner="dots"):
        try:
            success = memory_store.delete_entity_by_name(name)
            if success:
                console.print(f"[green]✓[/green] Entity '{name}' removed from memory")
            else:
                console.print(f"[red]✗[/red] Failed to remove entity '{name}'")
        except Exception as e:
            console.print(f"[red]❌ Error removing entity: {e}[/red]")


@memory_app.command("doctor")
def memory_doctor():
    """Run memory system health check."""
    memory_store = _get_memory_store()
    if not memory_store:
        return

    with console.status("[cyan]Running memory doctor...[/cyan]", spinner="dots"):
        try:
            issues = []
            stats = memory_store.get_stats()

            if stats.get("events", 0) == 0:
                issues.append("No events in database")
            if stats.get("entities", 0) == 0:
                issues.append("No entities in database")

            if not issues:
                console.print("[green]✓[/green] Memory system is healthy")
            else:
                console.print(f"\n{__logo__} Memory Doctor Report")
                console.print("=" * 50)
                for issue in issues:
                    console.print(f"[yellow]⚠️  {issue}[/yellow]")
        except Exception as e:
            console.print(f"[red]❌ Memory doctor failed: {e}[/red]")


@session_app.command("compact")
def session_compact():
    """Trigger session compaction manually."""
    from nanobot.memory.token_counter import count_messages

    config = load_config()
    if not config.memory.enabled:
        console.print("[yellow]⚠️ Memory system disabled[/yellow]")
        return

    session_manager = SessionManager(config.workspace_path)
    sessions = session_manager.list_sessions()
    if not sessions:
        console.print("[yellow]⚠️ No sessions found[/yellow]")
        return

    session_key = sessions[0]["key"]
    session = session_manager.get_or_create(session_key)

    console.print(f"Session: {session_key}")
    console.print(f"Messages: {len(session.messages)}")
    console.print(f"Tokens: {count_messages(session.messages)}")

    try:
        compactor = SessionCompactor(config.memory.session_compaction)
        with console.status("[cyan]Compacting session...[/cyan]", spinner="dots"):
            import asyncio

            result = asyncio.run(compactor.compact_session(session, 8000))
            if result:
                session.messages = result.messages
                session_manager.save(session)
                console.print("[green]✓[/green] Compaction complete!")
                console.print(f"Tokens: {result.tokens_before} → {result.tokens_after}")
    except Exception as e:
        console.print(f"[red]❌ Compaction error: {e}[/red]")


@session_app.command("status")
def session_status():
    """Show session status and context usage."""
    from nanobot.memory.token_counter import count_messages

    config = load_config()
    session_manager = SessionManager(config.workspace_path)
    sessions = session_manager.list_sessions()

    if sessions:
        table = Table(title="Sessions")
        table.add_column("Session Key")
        table.add_column("Messages")
        table.add_column("Tokens")
        table.add_column("Last Updated")

        for s_info in sessions:
            session = session_manager.get_or_create(s_info["key"])
            tokens = count_messages(session.messages)
            table.add_row(
                s_info["key"],
                str(len(session.messages)),
                str(tokens),
                s_info.get("updated_at", "Unknown"),
            )
        console.print(table)
    else:
        console.print("[yellow]⚠️ No sessions found[/yellow]")


@session_app.command("reset")
def session_reset():
    """Reset/clear all sessions."""
    if not typer.confirm("This will delete ALL conversation history. Continue?"):
        console.print("[yellow]Session reset cancelled[/yellow]")
        return

    config = load_config()
    session_manager = SessionManager(config.workspace_path)
    sessions = session_manager.list_sessions()
    deleted_count = 0

    for s_info in sessions:
        if session_manager.delete(s_info["key"]):
            deleted_count += 1
    console.print(f"[green]✓[/green] Deleted {deleted_count} session(s)")


if __name__ == "__main__":
    app()

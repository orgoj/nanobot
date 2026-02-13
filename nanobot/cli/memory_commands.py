"""Memory CLI commands for nanobot."""

import asyncio
import json
import os
from pathlib import Path
from typing import Any, Optional

import typer
from rich.console import Console
from rich.table import Table

from loguru import logger


console = Console()


def _get_memory_store() -> Optional[Any]:
    """Get memory store with error handling."""
    try:
        from nanobot.memory.store import TurboMemoryStore
        from nanobot.config.loader import load_config
        
        config = load_config()
        if not config.memory.enabled:
            console.print("[yellow]Memory system is disabled[/yellow]")
            return None
        
        workspace = config.workspace_path
        memory_dir = workspace / "memory"
        memory_dir.mkdir(exist_ok=True)
        
        return TurboMemoryStore(config.memory, workspace)
    except ImportError:
        console.print("[red]Error importing memory store[/red]")
        return None


def _format_size(size_bytes: int) -> str:
    """Format bytes as human readable size."""
    if size_bytes < 1024:
        return f"{size_bytes} B"
    elif size_bytes < 1024 * 1024:
        return f"{size_bytes / 1024:.1f} KB"
    else:
        return f"{size_bytes / (1024 * 1024):.1f} MB"


def _format_confidence(confidence: float) -> str:
    """Format confidence with color."""
    if confidence >= 0.8:
        return f"[green]{confidence:.2f}[/green]"
    elif confidence >= 0.5:
        return f"[yellow]{confidence:.2f}[/yellow]"
    else:
        return f"[red]{confidence:.2f}[/red]"


# Memory Commands App
memory_app = typer.Typer(name="memory", help="Memory system management commands")


@memory_app.command("init")
def memory_init():
    """Initialize memory database."""
    with console.status("[cyan]Initializing...[/cyan]", spinner="dots"):
        memory_store = _get_memory_store()
        if memory_store:
            logger.info("Memory database initialized")
            console.print("[green]Memory database initialized[/green]")


@memory_app.command("status")
def memory_status():
    """Show memory system status."""
    memory_store = _get_memory_store()
    if not memory_store:
        return
    
    try:
        stats = memory_store.get_stats()
        
        console.print(f"\n[bold]Memory Status[/bold]")
        console.print(f"Events: {stats.get('events', 0):,}")
        console.print(f"Entities: {stats.get('entities', 0):,}")
        console.print(f"Edges: {stats.get('edges', 0):,}")
        console.print(f"Facts: {stats.get('facts', 0):,}")
        
        # Entity types
        entity_summary = stats.get("entity_summary", {})
        if entity_summary:
            console.print("\n[bold yellow]Entity Types:[/bold yellow]")
            for entity_type, count in entity_summary.items():
                console.print(f"  {entity_type}: {count}")
        
        # Learning stats
        try:
            learnings = memory_store.get_all_learnings(active_only=False)
            console.print(f"\n[bold magenta]Learnings:[/bold magenta] {len(learnings)}")
        except Exception:
            pass
        
    except Exception as e:
        console.print(f"[red]Error: {e}[/red]")


@memory_app.command("search")
def memory_search(query: str, limit: int = typer.Option(10, "--limit", "-l")):
    """Search memory content."""
    memory_store = _get_memory_store()
    if not memory_store:
        return
    
    try:
        from nanobot.memory.retrieval import create_retrieval
        
        retrieval = create_retrieval(memory_store)
        results = retrieval.search(query, limit=limit)
        
        if results:
            console.print(f"\n[bold]Search: {query}[/bold]")
            for i, result in enumerate(results, 1):
                content = result.get('content', '')[:100]
                similarity = result.get('similarity', 0)
                console.print(f"{i}. {content} [dim]({similarity:.2f})[/dim]")
        else:
            console.print(f"[yellow]No results for: {query}[/yellow]")
            
    except Exception as e:
        console.print(f"[red]Error: {e}[/red]")


@memory_app.command("entities")
def memory_entities(limit: int = typer.Option(20, "--limit", "-l")):
    """List all entities."""
    memory_store = _get_memory_store()
    if not memory_store:
        return
    
    try:
        entities = memory_store.get_all_entities(limit=limit)
        
        if entities:
            table = Table(title=f"Entities (Top {len(entities)})")
            table.add_column("Name", style="green")
            table.add_column("Type", style="yellow")
            table.add_column("Events", style="magenta")
            table.add_column("Last Seen", style="dim")
            
            for entity in entities:
                last_seen_str = "unknown"
                if entity.last_seen and hasattr(entity.last_seen, 'strftime'):
                    last_seen_str = entity.last_seen.strftime("%Y-%m-%d")
                elif entity.last_seen:
                    last_seen_str = str(entity.last_seen)[:10]
                table.add_row(
                    entity.name,
                    entity.entity_type,
                    str(entity.event_count),
                    last_seen_str
                )
            
            console.print(f"\n[bold]Entities[/bold]")
            console.print(table)
        else:
            console.print("[yellow]No entities found[/yellow]")
            
    except Exception as e:
        console.print(f"[red]Error: {e}[/red]")


@memory_app.command("entity")
def memory_entity(name: str):
    """Get entity details."""
    memory_store = _get_memory_store()
    if not memory_store:
        return
    
    try:
        entity = memory_store.find_entity_by_name(name)
        
        if entity:
            console.print(f"\n[bold]Entity: {name}[/bold]")
            console.print(f"Type: {entity.entity_type}")
            console.print(f"Events: {entity.event_count}")
            console.print(f"Description: {entity.description or 'No description'}")
        else:
            console.print(f"[yellow]Entity '{name}' not found[/yellow]")
            
    except Exception as e:
        console.print(f"[red]Error: {e}[/red]")


@memory_app.command("forget")
def memory_forget(name: str, confirm: bool = typer.Option(False, "--confirm", "-y")):
    """Remove entity from memory."""
    memory_store = _get_memory_store()
    if not memory_store:
        return
    
    if not confirm:
        if not typer.confirm(f"Remove '{name}' from memory?"):
            console.print("[yellow]Cancelled[/yellow]")
            return
    
    try:
        entity = memory_store.find_entity_by_name(name)
        if not entity:
            console.print(f"[yellow]Entity '{name}' not found[/yellow]")
            return
        success = memory_store.delete_entity(entity.id)
        if success:
            console.print(f"[green]Entity '{name}' removed[/green]")
        else:
            console.print(f"[red]Failed to remove '{name}'[/red]")
    except Exception as e:
        console.print(f"[red]Error: {e}[/red]")


@memory_app.command("doctor")
def memory_doctor():
    """Run memory health check."""
    memory_store = _get_memory_store()
    if not memory_store:
        return
    
    try:
        stats = memory_store.get_stats()
        issues = []
        
        if stats.get("events", 0) == 0:
            issues.append("No events in database")
        if stats.get("entities", 0) == 0:
            issues.append("No entities in database")
        
        if not issues:
            console.print("[green]Memory system is healthy[/green]")
        else:
            console.print("\n[bold]Issues Found:[/bold]")
            for issue in issues:
                console.print(f"[yellow]Warning: {issue}[/yellow]")
                
    except Exception as e:
        console.print(f"[red]Error: {e}[/red]")


# Session Commands App
session_app = typer.Typer(name="session", help="Session management commands")


@session_app.command("compact")
def session_compact():
    """Trigger session compaction."""
    from nanobot.session.manager import SessionManager
    from nanobot.config.loader import load_config
    from nanobot.memory.session_compactor import SessionCompactor, SessionCompactionConfig
    from nanobot.memory.token_counter import count_messages
    
    config = load_config()
    if not config.memory.enabled:
        console.print("[yellow]Memory system disabled[/yellow]")
        return
    
    workspace = config.workspace_path
    session_manager = SessionManager(workspace)
    
    sessions = session_manager.list_sessions()
    if not sessions:
        console.print("[yellow]No sessions found[/yellow]")
        return
    
    session_key = sessions[0]["key"]
    session = session_manager.get_or_create(session_key)
    
    console.print(f"Session: {session_key}")
    console.print(f"Messages: {len(session.messages)}")
    console.print(f"Tokens: {count_messages(session.messages)}")
    
    try:
        compaction_config = config.memory.session_compaction
        settings = SessionCompactionConfig(
            enabled=compaction_config.enabled,
            mode=compaction_config.mode,
            threshold_percent=compaction_config.threshold_percent,
            target_tokens=compaction_config.target_tokens,
            min_messages=compaction_config.min_messages,
            max_messages=compaction_config.max_messages,
            preserve_recent=compaction_config.preserve_recent,
            preserve_tool_chains=compaction_config.preserve_tool_chains,
            summary_chunk_size=compaction_config.summary_chunk_size,
            enable_memory_flush=compaction_config.enable_memory_flush,
        )
        compactor = SessionCompactor(settings)
        should_compact = compactor.should_compact(session.messages, 8000)
        
        if should_compact:
            console.print("[yellow]Compacting...[/yellow]")
            result = asyncio.run(compactor.compact_session(session, 8000))
            
            if result:
                console.print(f"[green]Complete! Messages: {result.original_count} -> {result.compacted_count}[/green]")
                console.print(f"Tokens: {result.tokens_before} -> {result.tokens_after}")
                session.messages = result.messages
                session_manager.save(session)
        else:
            console.print("[green]No compaction needed[/green]")
            
    except Exception as e:
        console.print(f"[red]Error: {e}[/red]")


@session_app.command("status")
def session_status():
    """Show session status."""
    from nanobot.session.manager import SessionManager
    from nanobot.config.loader import load_config
    from nanobot.memory.token_counter import count_messages
    
    config = load_config()
    if not config.memory.enabled:
        console.print("[yellow]Memory system disabled[/yellow]")
        return
    
    workspace = config.workspace_path
    session_manager = SessionManager(workspace)
    
    sessions = session_manager.list_sessions()
    if sessions:
        table = Table(title="Sessions")
        table.add_column("Session", style="cyan")
        table.add_column("Messages", style="green")
        table.add_column("Tokens", style="yellow")
        
        max_tokens = config.memory.enhanced_context.max_context_tokens
        
        for session_data in sessions[:10]:
            try:
                session = session_manager.get_or_create(session_data["key"])
                tokens = count_messages(session.messages)
                percentage = (tokens / max_tokens * 100) if max_tokens > 0 else 0
                
                status_color = "green"
                if percentage > 70:
                    status_color = "yellow"
                if percentage > 80:
                    status_color = "red"
                
                table.add_row(
                    session_data["key"][:30],
                    str(len(session.messages)),
                    f"[{status_color}]{percentage:.0f}%[/]"
                )
            except Exception:
                table.add_row(session_data["key"][:30], "error", "0")
        
        console.print(f"\n[bold]Sessions[/bold]")
        console.print(table)
        
        if config.memory.enhanced_context.show_context_percentage:
            console.print(f"\n[dim]Warning: 70% | Compact: 80%[/dim]")
    else:
        console.print("[yellow]No sessions found[/yellow]")


@session_app.command("reset")
def session_reset():
    """Reset all sessions."""
    from nanobot.session.manager import SessionManager
    from nanobot.config.loader import load_config
    
    if not typer.confirm("Delete ALL conversation history?"):
        console.print("[yellow]Cancelled[/yellow]")
        return
    
    config = load_config()
    workspace = config.workspace_path
    session_manager = SessionManager(workspace)
    
    try:
        sessions = session_manager.list_sessions()
        deleted = sum(1 for s in sessions if session_manager.delete(s["key"]))
        console.print(f"[green]Deleted {deleted} session(s)[/green]")
    except Exception as e:
        console.print(f"[red]Error: {e}[/red]")


if __name__ == "__main__":
    app = typer.Typer(name="nanobot")
    app.add_typer(memory_app, name="memory")
    app.add_typer(session_app, name="session")
    app()

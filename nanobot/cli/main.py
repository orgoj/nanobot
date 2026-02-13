"""Memory CLI commands (Simplified to fix LSP errors).

Provides comprehensive memory and session management commands
for the nanobot memory system.

Commands:
- nanobot memory init
- nanobot memory status
- nanobot memory search <query>
- nanobot memory entities
- nanobot memory entity <name>
- nanobot memory summary
- nanobot memory forget <entity>
- nanobot memory export <file>
- nanobot memory import <file>
- nanobot memory doctor
- nanobot session compact
- nanobot session status
- nanobot session reset
"""

import asyncio
import json
import os
import sys
from pathlib import Path
from typing import Any

import typer
from rich.console import Console
from rich.table import Table
from rich.panel import Panel
from rich.markdown import Markdown
from rich.text import Text
from loguru import logger

from nanobot import __logo__

# Initialize rich console
console = Console()


def _get_memory_store():
    """Get memory store with error handling."""
    try:
        from nanobot.memory.store import TurboMemoryStore
        from nanobot.config.loader import load_config, get_data_dir
        from nanobot.config.schema import MemoryConfig
        
        config = load_config()
        if not config.memory.enabled:
            console.print("[yellow]⚠️ Memory system is disabled in config[/yellow]")
            console.print("[dim]Enable it with: nanobot configure --memory.enabled true[/dim]")
            return None
        
        # Create memory directory if it doesn't exist
        workspace = config.workspace_path
        memory_dir = workspace / "memory"
        memory_dir.mkdir(exist_ok=True)
        
        return TurboMemoryStore(config.memory, workspace)
    except ImportError:
        console.print("[red]❌ Error importing memory store: {e}")
        console.print("[dim]Make sure memory system is properly installed[/dim]")
        return None


def _format_size(size_bytes: int) -> str:
    """Format bytes as human readable size."""
    if size_bytes < 1024:
        return f"{size_bytes} B"
    elif size_bytes < 1024 * 1024:
        return f"{size_bytes / 1024:.1f} KB"
    else:
        return f"{size_bytes / (1024 * 1024):.1f} GB"


def _format_confidence(confidence: float) -> str:
    """Format confidence with color."""
    if confidence >= 0.8:
        return f"[green]{confidence:.2f}[/green]"
    elif confidence >= 0.5:
        return f"[yellow]{confidence:.2f}[/yellow]"
    else:
        return f"[red]{confidence:.2f}[/red]"


def _get_entity_count(store) -> int:
    """Get total entity count."""
    try:
        stats = store.get_stats()
        return stats.get('entities', 0)
    except Exception:
        return 0


def _get_learning_count(store) -> int:
    """Get learning count."""
    try:
        stats = store.get_stats()
        return stats.get('learning_count', 0)
    except ImportError:
        return 0


def _create_entity_table(entities: list, show_all: bool = True) -> Table:
    """Create a rich table for entities."""
    table = Table(show_header=show_all, title="Entities")
    
    if show_all:
        table.add_column("ID", style="cyan")
        table.add_column("Name", style="green")
        table.add_column("Type", style="yellow")
        table.add_column("Relevance", style="magenta")
        table.add_column("First Seen", style="dim")
        table.add_column("Last Seen", style="dim")
        
        for entity in entities:
            relations = ", ".join([rel.get("type", "unknown") for rel in entity.get("relations", [])]) if entity.get("relations") else "none")
            
            first_seen = entity.get("first_seen_at", "Unknown")
            last_seen = entity.get("last_seen_at", "Unknown")
            if isinstance(first_seen, (int, float)):
                first_seen = f"{first_seen:.0f}"
            if isinstance(last_seen, (int, float)):
                last_seen = f"{last_seen:.0f}"
            
            table.add_row(
                entity.get("id", "unknown")[:8],
                entity.get("name", "unknown"),
                entity.get("type", "unknown"),
                _format_confidence(entity.get("relevance", 0)),
                relations,
                first_seen,
                last_seen,
            )
    
    else:
        # Limited view (just top 10)
        table.add_column("Name", style="green")
        table.add_column("Type", style="yellow")
        table.add_column("Relevance", style="magenta")
        table.add_column("Last Seen", style="dim")
        
        for entity in entities[:10]:
            table.add_row(
                entity.get("id", "unknown")[:8],
                entity.get("name", "unknown"),
                entity.get("type", "unknown"),
                _format_confidence(entity.get("relevance", 0)),
                entity.get("last_seen_at", "Unknown"),
            )
    
    return table


# Memory Commands App
memory_app = typer.Typer(
    name="memory",
    help="Memory system management commands",
    no_args_is_help=True,
)


@memory_app.command("init")
def memory_init():
    """Initialize memory database."""
    with console.status("[cyan]Initializing memory database...[/cyan]", spinner="dots"):
        memory_store = _get_memory_store()
        
        if memory_store:
            logger.info("Memory database initialized successfully")
            console.print("[green]✓[/green] Memory database initialized")
        else:
            console.print("[red]✗[/red] Failed to initialize memory database")


@memory_app.command("status")
def memory_status(
    verbose: bool = typer.Option(False, "--verbose", "-v", help="Show detailed information"),
    all: bool = typer.Option(False, "--all", "-a", help="Show all entities (not just summary)"),
):
    """Show memory system status and statistics."""
    memory_store = _get_memory_store()
    
    if not memory_store:
        return
    
    with console.status("[cyan]Loading memory status...[/cyan]", spinner="dots"):
        try:
            stats = memory_store.get_stats()
            
            console.print(f"\n{__logo__} Memory System Status")
            console.print("=" * 50)
            
            # Database info
            db_path = memory_store.db_path if hasattr(memory_store, 'db_path') else "memory/memory.db"
            db_size = 0
            if os.path.exists(db_path):
                db_size = os.path.getsize(db_path)
            
            console.print(f"[bold blue]Database:[/bold blue] {db_path}")
            console.print(f"[bold blue]Size: {_format_size(db_size)}")
            
            # Event and entity counts
            console.print(f"[bold green]Events:[/bold green] {stats.get('events', 0):,}")
            console.print(f"[bold green]Entities:[/bold green] {stats.get('entities', 0):,}")
            console.print(f"[bold green]Edges:[/bold green] {stats.get('edges', 0):,}")
            console.print(f"[bold green]Facts:[/bold green] {stats.get('facts', 0):,}")
            
            # Learning status
            try:
                from nanobot.memory.models import Learning
                learning_count = memory_store.get_learning_count()
                learning_stats = memory_store.get_learning_stats()
                if learning_count > 500:
                    console.print("[yellow]⚠️ High learning count: {learning_count} (consider running memory forget)")
            except ImportError:
                pass
            
            # Knowledge graph summary
            entity_summary = stats.get("entity_summary", {})
            for entity_type, count in entity_summary.items():
                console.print(f"[bold yellow]Entity Summary:[/bold yellow]")
                console.print(f"  {entity_type}: {count}")
            
            # Display counts
            console.print(f"[bold green]✓ Import Complete![/bold cyan]")
            
            console.print(f"[dim]Entities: {_get_entity_count(memory_store)}")
            if learning_count > 0:
                console.print(f"[dim]Learnings: {_get_learning_count(memory_store)}")
            
        except Exception as e:
            console.print(f"[red]❌ Error loading memory status: {e}")
        else:
            console.print("[red]❌ Memory system not available")


@memory_app.command("search")
def memory_search(
    query: str,
    limit: int = typer.Option(10, "--limit", "-l", help="Maximum results to return"),
):
    """Search memory content."""
    memory_store = _get_memory_store()
    
    if not memory_store:
        return
    
    with console.status("[cyan]Searching memory...[/cyan]", spinner="dots"):
        try:
            # Search using semantic search
            from nanobot.memory.retrieval import create_retrieval
            
            retrieval = create_retrieval(memory_store)
            results = retrieval.search(query, limit=limit)
            
            if results:
                console.print(f"\n{__logo__} Search Results for: [bold green]{query}[/bold green]")
                console.print("=" * 50)
                
                for i, result in enumerate(results, 1):
                    console.print(f"[cyan]{i}.[/cyan] [bold]{result.get('content', '')[:100]}[/bold] [dim] ({result.get('similarity', 0):.3f}[/dim])")
            
            else:
                console.print(f"[yellow]No results found for: {query}[/yellow]")
                
        except Exception as e:
            console.print(f"[red]❌ Error searching memory: {e}")


@memory_app.command("entities")
def memory_entities(
    limit: int = typer.Option(20, "--limit", "-l", help="Maximum entities to show"),
):
    """List all entities in memory."""
    memory_store = _get_memory_store()
    
    if not memory_store:
        return
    
    with console.status("[cyan]Loading entities...[/cyan]", spinner="dots"):
        try:
            entities = memory_store.get_all_entities(limit=limit)
            
            if entities:
                entity_table = _create_entity_table(entities, show_all=False)
                console.print(f"\n{__logo__} Entities (Top {min(limit, len(entities))})")
                console.print(entity_table)
            else:
                console.print("[yellow]No entities found in memory[/yellow]")
                
        except Exception as e:
            console.print(f"[red]❌ Error loading entities: {e}")


@memory_app.command("entity")
def memory_entity(
    name: str,
    show_relations: bool = typer.Option(False, "--relations", "-r", help="Show entity relationships"),
):
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
                console.print(f"[bold cyan]ID:[/bold cyan] {entity.get('id', 'unknown')}")
                console.print(f"[bold cyan]Type:[/bold cyan] {entity.get('type', 'unknown')}")
                console.print(f"[bold cyan]Relevance:[/bold magenta] {_format_confidence(entity.get('relevance', 0))}")
                console.print(f"[bold cyan]First Seen:[/bold cyan] {entity.get('first_seen_at', 'Unknown')}")
                console.print(f"[bold cyan]Last Seen:[/bold cyan] {entity.get('last_seen_at', 'Unknown')}")
                console.print(f"[bold cyan]Description:[/bold cyan] {entity.get('description', 'No description')}")
                
                if show_relations and entity.get('relations'):
                    console.print(f"[bold yellow]Relationships:[/bold yellow]")
                    
                    for i, rel in enumerate(entity.get('relations', []), 1):
                        console.print(f"[cyan]  {i}.[/cyan] [bold]{rel.get('type', 'unknown')}[/bold] [dim]({rel.get('target', 'unknown')})")
                        console.print(f"[dim]     {rel.get('description', 'No description')}")
            else:
                console.print("[bold cyan]No relationships found for this entity")
                
            else:
                console.print(f"[yellow]Entity '{name}' not found[/yellow]")
                
        except Exception as e:
            console.print(f"[red]❌ Error loading entity: {e}")


@memory_app.command("summary")
def memory_summary(
    show_details: bool = typer.Option(False, "--details", "-d", help="Show detailed summary content"),
):
    """Show memory summary information."""
    memory_store = _get_memory_store()
    
    if not memory_store:
        return
    
    with console.status("[cyan]Loading summary...[/cyan]", spinner="dots"):
        try:
            from nanobot.memory.summaries import create_summary_manager
            
            summary_manager = create_summary_manager(memory_store)
            summary_nodes = summary_manager.get_all_summary_nodes(limit=10)
            
            if summary_nodes:
                console.print(f"\n{__logo__} Memory Summary")
                console.print("=" * 50)
                
                for node in summary_nodes:
                    console.print(f"[bold green]Root:[/bold green] {node.get('id', 'unknown')}")
                    console.print(f"[bold cyan]Type:[/bold cyan] {node.get('summary_type', 'unknown')}")
                    console.print(f"[bold cyan]Children: {len(node.get('children', []))}")
                    console.print(f"[bold cyan]Staleness: {node.get('staleness', 0)}")
                    console.print(f"[bold cyan]Events: {len(node.get('events', [])}")
                    console.print(f"[bold cyan]Created: {node.get('created_at', 'Unknown')}")
                    
                if show_details and node.get('summary'):
                    console.print(f"[bold cyan]Summary:[/bold cyan] {node.get('summary', '')[:200]}[/dim]")
                    
                    if len(node.get('summary', '')) > 200:
                        console.print(f"[dim]     ...[/dim]")
                
                else:
                    console.print(f"[bold cyan]No summary details available")
            
            else:
                console.print("[yellow]No summary nodes found[/yellow]")
                
        except Exception as e:
            console.print(f"[red]❌ Error loading summary: {e}")


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
            success = memory_store.delete_entity(name)
            
            if success:
                console.print(f"[green]✓[/green] Entity '{name}' removed from memory")
            else:
                console.print(f"[red]✗[/red] Failed to remove entity '{name}'")
                
        except Exception as e:
            console.print(f"[red]❌ Error removing entity: {e}")


@memory_app.command("export")
def memory_export(
    filename: str,
    include_embeddings: bool = typer.Option(False, "--embeddings", "-e", help="Include embedding vectors"),
):
    """Export memory to JSON file."""
    memory_store = _get_memory_store()
    
    if not memory_store:
        return
    
    if not os.path.exists(filename):
        console.print(f"[red]❌ File '{filename}' does not exist[/red]")
        return
    
    if not typer.confirm(f"This will replace {filename} if it exists?"):
            console.print("[yellow]Export cancelled[/yellow]")
            return
    
    with console.status("[cyan]Exporting memory...[/cyan]", spinner="dots"):
        try:
            # Export all memory data
            export_data = {
                "export_date": logger.info("Current timestamp for export"),
                "version": "1.0",
                "config": {
                    "memory": {
                        "enabled": True,
                        "db_path": str(memory_store.db_path) if hasattr(memory_store, 'db_path') else "memory/memory.db"
                    }
                }
            }
            
            # Add all entities
            entities = memory_store.get_all_entities()
            export_data["entities"] = entities if entities else []
            
            # Add learnings if available
            try:
                from nanobot.memory.models import Learning
                learnings = memory_store.get_all_learnings()
                export_data["learnings"] = learnings if learnings else []
            except ImportError:
                export_data["learnings"] = []
            
            # Add embedding vectors if available
            try:
                from nanobot.memory.models import Entity
                embedding_entities = [e for e in entities if hasattr(e, 'embedding') else []]
                export_data["entity_embeddings"] = embedding_entities
            except ImportError:
                export_data["entity_embeddings"] = []
            
            # Write to file
            with open(filename, 'w') as f:
                json.dump(export_data, f, indent=2)
                
            size = os.path.getsize(filename)
            console.print(f"[green]✓ Memory exported to {filename}")
            console.print(f"[dim]Size: {_format_size(size)}[/dim]")
            
        except Exception as e:
            console.print(f"[red]❌ Error exporting memory: {e}")


@memory_app.command("import")
def memory_import(
    filename: str,
    confirm: bool = typer.Option(False, "--confirm", "-y", help="Skip confirmation prompt"),
):
    """Import memory from JSON file."""
    memory_store = _get_memory_store()
    
    if not memory_store:
        return
    
    if not os.path.exists(filename):
        console.print(f"[red]❌ File '{filename}' does not exist[/red]")
        return
    
    if not confirm:
        if not typer.confirm(f"This will replace ALL memory data. Continue?"):
            console.print("[yellow]Import cancelled[/yellow]")
            return
    
    with console.status("[cyan]Importing memory...[/cyan]", spinner="dots"):
        try:
            with open(filename, 'r') as f:
                import_data = json.load(f)
            
            # Validate import data
            if "entities" not in import_data:
                console.print("[yellow]Warning: No entities in import file[/yellow]")
                import_data["entities"] = []
            
            if "learnings" not in import_data:
                console.print("[yellow]Warning: No learnings in import file[/yellow]")
                import_data["learnings"] = []
            
            # Clear existing data
            console.print("[yellow]Clearing existing memory...[/yellow]")
            memory_store._clear_all_data()
            
            # Import entities
            if import_data.get("entities"):
                for entity_data in import_data.get("entities", []):
                    try:
                        memory_store.create_entity(
                            name=entity_data.get("name", ""),
                            entity_type=entity_data.get("type", ""),
                            description=entity_data.get("description", ""),
                            confidence=entity_data.get("confidence", 0.5),
                            embedding=entity_data.get("embedding", [])
                        )
                    except Exception as e:
                        logger.warning(f"Failed to import entity {entity_data.get('name')}: {e}")
            
            # Import learnings if available
            if import_data.get("learnings"):
                for learning_data in import_data.get("learnings", []):
                    try:
                        memory_store.create_learning(
                            content=learning_data.get("content", ""),
                            category=learning_data.get("category", "general"),
                            confidence=learning_data.get("confidence", 0.7),
                            source_event_id=learning_data.get("source_event_id", ""),
                            tool_name=learning_data.get("tool_name")
                        )
                    except Exception as e:
                        logger.warning(f"Failed to import learning: {e}")
            
            console.print(f"[green]✓ Memory imported from {filename}")
            console.print(f"[dim]Entities: {len(import_data.get('entities', []))}")
            console.print(f"[dim]Learnings: {len(import_data.get('learnings', []))}")
            console.print(f"[bold green]✓ Import Complete![/bold cyan]")
            
        except Exception as e:
            console.print(f"[red]❌ Error importing memory: {e}")


@memory_app.command("doctor")
def memory_doctor():
    """Run memory system health check."""
    memory_store = _get_memory_store()
    
    if not memory_store:
        console.print("[red]❌ Memory system not available[/red]")
        return
    
    with console.status("[cyan]Running memory doctor...[/cyan]", spinner="dots"):
        try:
            issues = []
            
            # Check database integrity
            try:
                stats = memory_store.get_stats()
                
                if stats.get("events", 0) == 0:
                    issues.append("No events in database - memory system will not function properly")
                
                if stats.get("entities", 0) == 0:
                    issues.append("No entities in database - knowledge graph will be empty")
                
                # Check for stale summaries
                try:
                    from nanobot.memory.summaries import create_summary_manager
                    summary_manager = create_summary_manager(memory_store)
                    stale_nodes = summary_manager.get_stale_nodes()
                    
                    if stale_nodes:
                        issues.append(f"{len(stale_nodes)} stale summary nodes")
                
                except Exception as e:
                    issues.append(f"Database access error: {e}")
            
            # Check for learnings if available
            try:
                from nanobot.memory.models import Learning
                learning_count = memory_store.get_learning_count()
                if learning_count > 500:
                    issues.append(f"High learning count: {learning_count} (consider running memory forget)")
                except ImportError:
                    pass
            
            # Check for learnings
                learning_stats = memory_store.get_learning_stats()
                if learning_stats.get("decay_rate", 0) > 0:
                    issues.append(f"Learning decay rate: {learning_stats.get('decay_rate'):0.0}")
            
            if not issues:
                console.print("[green]✓ Memory system is healthy")
            else:
                console.print("\n{__logo__} Memory Doctor Report")
                console.print("=" * 50)
                
                for issue in issues:
                    console.print(f"[yellow]⚠️  {issue}[/yellow]")
                
                console.print(f"[red]❌ Memory doctor failed: {e}")
        except Exception as e:
            console.print(f"[red]❌ Memory doctor failed: {e}")


# Session Commands App
session_app = typer.Typer(
    name="session",
    help="Session management commands",
    no_args_is_help=True,
)


@session_app.command("compact")
def session_compact():
    """Manually trigger session compaction."""
    from nanobot.session.manager import SessionManager
    from nanobot.config.loader import load_config
    from nanobot.memory.session_compactor import SessionCompactor
    from nanobot.memory.token_counter import count_messages
    from nanobot.config.schema import MemoryConfig
    
    config = load_config()
    if not config.memory.enabled:
        console.print("[yellow]⚠️ Memory system disabled - session compaction not available[/yellow]")
        return
    
    workspace = config.workspace_path
    session_manager = SessionManager(workspace)
    
    console.print(f"\n{__logo__} Session Compaction")
    console.print("=" * 50)
    
    # Get default session (last active)
    sessions = session_manager.list_sessions()
    
    if not sessions:
        console.print("[yellow]⚠️ No sessions found[/yellow]")
        return
    
    # Use default session (last active)
    session_key = sessions[0]["key"]
    session = session_manager.get_or_create(session_key)
        
    console.print(f"Session: {session_key}")
    console.print(f"Messages: {len(session.messages)}")
    console.print(f"Tokens: {count_messages(session.messages)}")
    
    # Check if compaction is needed
    try:
        compactor = SessionCompactor(config.memory.session_compaction)
        should_compact = compactor.should_compact(session.messages, 8000)
        
        if should_compact:
            console.print("[yellow]Compaction needed - this may take a moment...[/yellow]")
            
            # Perform compaction
            import asyncio
            result = asyncio.run(compactor.compact_session(session, 8000))
            
            if result:
                console.print("[green]✓[/green] Compaction complete!")
                console.print(f"Messages: {result.original_count} → {result.compacted_count}")
                console.print(f"Tokens: {result.tokens_before} → {result.tokens_after} ({1 - result.compaction_ratio:.1%} reduction)")
                console.print(f"Mode: {result.mode}")
                
                # Update session
                session.messages = result.messages
                session_manager.save(session)
                
                # Add compaction metadata
                session.metadata["last_compaction"] = {
                    "original_count": result.original_count,
                    "compacted_count": result.compacted_count,
                    "tokens_before": result.tokens_before,
                    "tokens_after": result.tokens_after,
                    "mode": result.mode
                }
            console.print(f"[yellow]Compaction count since last compaction: {last_compaction.get('compactions', 0)}")
        else:
                console.print("[green]✓ No compaction needed")
        except Exception as e:
            console.print(f"[red]❌ Compaction error: {e}")
    else:
        console.print("[yellow]⚠️ No sessions found[/yellow]")


@session_app.command("status")
def session_status():
    """Show session status and context usage."""
    from nanobot.session.manager import SessionManager
    from nanobot.config.loader import load_config
    from nanobot.memory.token_counter import count_messages
    from nanobot.config.schema import MemoryConfig
    
    config = load_config()
    if not config.memory.enabled:
        console.print("[yellow]⚠️ Memory system disabled - session status not available[/yellow]")
        return
    
    workspace = config.workspace_path
    session_manager = SessionManager(workspace)
    
    console.print(f"\n{__logo__} Session Status")
    console.print("=" * 50)
    
    # List all sessions with stats
    sessions = session_manager.list_sessions()
    
    if sessions:
        session_table = Table(title="Sessions")
        session_table.add_column("Session Key", style="cyan")
        session_table.add_column("Messages", style="green")
        session_table.add_column("Tokens", style="yellow")
        session_table.add_column("Last Updated", style="dim")
        session_table.add_column("Compactions", style="magenta")
        
        for session_data in sessions:
            try:
                session = session_manager.get_or_create(session_data["key"])
                messages = session.messages
                tokens = count_messages(messages)
                max_tokens = config.memory.enhanced_context.max_context_tokens
                percentage = (tokens / max_tokens * 100) if max_tokens > 0 else 0
                
                # Check compaction metadata
                last_compaction = session.metadata.get("last_compaction", {})
                compactions = last_compaction.get("compactions", 0)
                
                # Check if compaction would trigger
                from nanobot.memory.session_compactor import SessionCompactor
                would_compact = compactor.should_compact(messages, max_tokens)
                
                if percentage > config.memory.enhanced_context.warning_threshold:
                    status_color = "yellow"
                elif percentage > config.memory.enhanced_context.compaction_threshold:
                    status_color = "red"
                else:
                    status_color = "green"
                
                # Display context usage
                if config.memory.enhanced_context.show_context_percentage and max_tokens:
                    console.print(f"Session {session_data['key']}: [{status_color}]{percentage:.0f}%]")
                    console.print(f"Tokens: {tokens}/{max_tokens} | Buffer: {max_tokens - tokens}")
                else:
                    console.print(f"Session {session_data['key']}: {len(messages)} messages | {tokens} tokens")
            
                # Check if compaction would trigger
                if would_compact:
                    console.print("[red]⚠️ Would compact (80% threshold)[/red]")
                elif compactions > 0:
                    console.print(f"[yellow]⚠️ {compactions since last compaction[/yellow]")
                else:
                    console.print(f"[green]✓ No compaction needed")
                
                # Show last compaction if exists
                if last_compaction:
                    time_since_last = last_compaction.get("created_at", "Unknown")
                    if time_since_last != "Unknown":
                        time_since_last = f"{time_since_last:.0f} ago"
                        console.print(f"[dim]Last compaction: {time_since_last} ago[/dim]")
                    else:
                        console.print("[bold cyan]Last compaction: Never")
                    
            else:
                console.print("[bold cyan]Last compaction: Never")
                
                else:
                    console.print("[yellow]No last compaction")
            
            except Exception as e:
                console.print(f"[red]❌ Session status error: {e}")
        else:
            console.print("[yellow]⚠️ No sessions found[/yellow]")


@session_app.command("reset")
def session_reset():
    """Reset/clear all sessions."""
    from nanobot.session.manager import SessionManager
    from nanobot.config.loader import load_config
    
    if not typer.confirm("This will delete ALL conversation history. Continue?"):
        console.print("[yellow]Session reset cancelled[/yellow]")
        return
    
    config = load_config()
    workspace = config.workspace_path
    session_manager = SessionManager(workspace)
    
    with console.status("[cyan]Resetting sessions...[/cyan]", spinner="dots"):
        try:
            sessions = session_manager.list_sessions()
            deleted_count = 0
            
            for session_data in sessions:
                if session_manager.delete(session_data["key"]):
                    deleted_count += 1
            
            console.print(f"[green]✓[/green] Deleted {deleted_count} session(s)")
            
        except Exception as e:
            console.print(f"[red]❌ Session reset error: {e}")


if __name__ == "__main__":
    app = typer.Typer(
        name="nanobot",
        help=f"{__logo__} nanobot - Personal AI Assistant",
        no_args_is_help=True,
        include_apps=[memory_app, session_app],
    )
    
    # Register CLI commands
    if memory_app:
        app.add_typer(memory_app, name="memory")
    if session_app:
        app.add_typer(session_app, name="session")
    
    app()
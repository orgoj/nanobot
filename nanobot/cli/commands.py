"""CLI commands for nanobot."""

import asyncio
import os
import select
import sys
from pathlib import Path

import typer
from prompt_toolkit import PromptSession
from prompt_toolkit.formatted_text import HTML
from prompt_toolkit.history import FileHistory
from prompt_toolkit.patch_stdout import patch_stdout
from rich.console import Console
from rich.markdown import Markdown
from rich.panel import Panel
from rich.table import Table
from rich.text import Text

from nanobot import __logo__, __version__
from nanobot.config.loader import get_data_dir, load_config

# Initialize Rich console
console = Console()

# Main CLI app
app = typer.Typer(name="nanobot", help="nanobot CLI")

# Import memory and session commands
try:
    from nanobot.cli.memory_commands import _get_work_log_icon, memory_app, session_app
    if memory_app:
        app.add_typer(memory_app, name="memory")
    if session_app:
        app.add_typer(session_app, name="session")
except ImportError:
    memory_app = None
    session_app = None

# Exit commands for interactive mode
EXIT_COMMANDS = {"exit", "quit", "/exit", "/quit", ":q"}


def version_callback(value: bool):
    if value:
        console.print(f"nanobot version {__version__}")
        raise typer.Exit()


# ---------------------------------------------------------------------------
# CLI input: prompt_toolkit for editing, paste, history, and display
# ---------------------------------------------------------------------------

_PROMPT_SESSION: PromptSession | None = None
_SAVED_TERM_ATTRS = None


def _init_prompt_session() -> None:
    """Create the prompt_toolkit session with persistent file history."""
    global _PROMPT_SESSION, _SAVED_TERM_ATTRS

    try:
        import termios
        _SAVED_TERM_ATTRS = termios.tcgetattr(sys.stdin.fileno())
    except Exception:
        pass

    history_file = Path.home() / ".nanobot" / "history" / "cli_history"
    history_file.parent.mkdir(parents=True, exist_ok=True)

    _PROMPT_SESSION = PromptSession(
        history=FileHistory(str(history_file)),
        enable_open_in_editor=False,
        multiline=False,
    )


def _restore_terminal() -> None:
    """Restore terminal to its original state."""
    if _SAVED_TERM_ATTRS is None:
        return
    try:
        import termios
        termios.tcsetattr(sys.stdin.fileno(), termios.TCSADRAIN, _SAVED_TERM_ATTRS)
    except Exception:
        pass


def _flush_pending_tty_input() -> None:
    """Drop unread keypresses typed while the model was generating output."""
    try:
        fd = sys.stdin.fileno()
        if not os.isatty(fd):
            return
    except Exception:
        return

    try:
        import termios
        termios.tcflush(fd, termios.TCIFLUSH)
        return
    except Exception:
        pass

    try:
        while True:
            ready, _, _ = select.select([fd], [], [], 0)
            if not ready:
                break
            if not os.read(fd, 4096):
                break
    except Exception:
        return


def _print_agent_response(response: str, render_markdown: bool) -> None:
    """Render assistant response with consistent terminal styling."""
    content = response or ""
    body = Markdown(content) if render_markdown else Text(content)
    console.print()
    console.print(f"{__logo__} [bold cyan]nanobot[/bold cyan]")
    console.print(body)
    console.print()


def _is_exit_command(command: str) -> bool:
    """Return True when input should end interactive chat."""
    return command.lower() in EXIT_COMMANDS


async def _read_interactive_input_async() -> str:
    """Read user input using prompt_toolkit."""
    if _PROMPT_SESSION is None:
        _init_prompt_session()
    try:
        with patch_stdout():
            return await _PROMPT_SESSION.prompt_async(
                HTML("<b fg='ansiblue'>You:</b> "),
            )
    except EOFError as exc:
        raise KeyboardInterrupt from exc


@app.callback()
def main(
    root: str = typer.Option(None, "--root", help="Custom root directory for nanobot data"),
    version: bool = typer.Option(None, "--version", "-v", callback=version_callback, is_eager=True),
):
    """nanobot - Personal AI Assistant."""
    if root:
        from nanobot.utils.helpers import set_root_path
        set_root_path(root)


@app.command()
def onboard():
    """Run the step-by-step onboarding wizard."""
    # Show spinner immediately while imports load
    with console.status("[cyan]Preparing setup wizard...[/cyan]", spinner="dots"):
        from rich.prompt import Confirm, Prompt

        from nanobot.agent.tools.update_config import UpdateConfigTool
        from nanobot.config.loader import get_config_path

        tool = UpdateConfigTool()
        config_path = get_config_path()

    if config_path.exists():
        console.print(f"[yellow]Config already exists at {config_path}[/yellow]")
        if not Confirm.ask("Re-run onboarding wizard? (This will update your config)"):
            raise typer.Exit()

    console.print("\n[bold cyan]Let's get you set up![/bold cyan]")
    console.print("[dim]I'll guide you through the essential configuration.[/dim]\n")

    # Step 1: Model Provider
    console.print("[bold]Step 1: Select Model Provider[/bold]")
    providers = {
        "1": ("openrouter", "OpenRouter - Access multiple AI models (recommended)"),
        "2": ("anthropic", "Anthropic - Claude models"),
        "3": ("openai", "OpenAI - GPT models"),
        "4": ("groq", "Groq - Fast inference + Voice transcription (Whisper)"),
        "5": ("deepseek", "DeepSeek - Chinese models"),
        "6": ("moonshot", "Moonshot - Kimi models (Chinese)"),
        "7": ("gemini", "Gemini - Google AI models"),
        "8": ("zhipu", "Zhipu - ChatGLM models (Chinese)"),
        "9": ("dashscope", "DashScope - Qwen models (Alibaba/Chinese)"),
        "10": ("aihubmix", "AiHubMix - API Gateway"),
        "11": ("vllm", "vLLM - Local models"),
    }

    for key, (name, desc) in providers.items():
        console.print(f"  [{key}] {desc}")

    provider_choice = Prompt.ask("\nSelect provider", choices=list(providers.keys()), default="1")
    provider_name, provider_desc = providers[provider_choice]

    api_key = Prompt.ask(f"Enter your {provider_name.title()} API key", password=True)

    if api_key:
        with console.status(f"[cyan]Saving {provider_name} API key...[/cyan]", spinner="dots"):
            asyncio.run(tool.execute(path=f"providers.{provider_name}.api_key", value=api_key))
            console.print(f"[green]✓ {provider_name.title()} configured[/green]\n")

    # Step 2: Primary Model
    console.print("[bold]Step 2: Select Primary Model[/bold]")
    primary_model = Prompt.ask("Enter primary model name", default="anthropic/claude-3-5-sonnet")

    with console.status("[cyan]Setting primary model...[/cyan]", spinner="dots"):
        asyncio.run(tool.execute(path="agents.defaults.model", value=primary_model))
        console.print(f"[green]✓ Primary model set to {primary_model}[/green]\n")

    # Create workspace templates
    from nanobot.utils.helpers import get_workspace_path
    workspace = get_workspace_path()
    _create_workspace_templates(workspace)

    console.print(Panel.fit(
        "[bold green]🎉 Setup Complete![/bold green]\n\n"
        "Your nanobot is ready to use.",
        border_style="green"
    ))

    console.print("\n[bold]Get started:[/bold]")
    console.print("  [cyan]nanobot agent[/cyan]     - Start interactive chat")
    console.print("  [cyan]nanobot configure[/cyan] - Advanced settings")


@app.command()
def configure():
    """Interactive configuration wizard."""
    with console.status("[cyan]Loading configuration interface...[/cyan]", spinner="dots"):
        from nanobot.cli.configure import configure_cli
    configure_cli()


def _create_workspace_templates(workspace: Path):
    """Create default workspace template files."""
    templates = {
        "AGENTS.md": """# Agent Instructions
You are a helpful AI assistant. Be concise, accurate, and friendly.
""",
        "SOUL.md": """# Soul
I am nanobot, a lightweight AI assistant.
""",
        "USER.md": """# User
Information about the user goes here.
""",
    }

    for filename, content in templates.items():
        file_path = workspace / filename
        if not file_path.exists():
            file_path.write_text(content)
            console.print(f"  [dim]Created {filename}[/dim]")

    # Create memory directory
    memory_dir = workspace / "memory"
    memory_dir.mkdir(parents=True, exist_ok=True)
    skills_dir = workspace / "skills"
    skills_dir.mkdir(exist_ok=True)


def _make_provider(config):
    """Create LiteLLMProvider from config."""
    from nanobot.providers.litellm_provider import LiteLLMProvider

    p = config.get_provider()
    model = config.agents.defaults.model
    if not (p and p.api_key) and not model.startswith("bedrock/"):
        console.print("[red]Error: No API key configured.[/red]")
        console.print("Run [cyan]nanobot onboard[/cyan] or [cyan]nanobot configure[/cyan]")
        raise typer.Exit(1)
    return LiteLLMProvider(
        api_key=p.api_key if p else None,
        api_base=config.get_api_base(),
        default_model=model,
        extra_headers=p.extra_headers if p else None,
        provider_name=config.get_provider_name(),
    )


@app.command()
def gateway(
    port: int = typer.Option(18790, "--port", "-p", help="Gateway port"),
    verbose: bool = typer.Option(False, "--verbose", "-v", help="Verbose output"),
):
    """Start the nanobot gateway."""
    from nanobot.agent.loop import AgentLoop
    from nanobot.bus.queue import MessageBus
    from nanobot.channels.manager import ChannelManager
    from nanobot.cron.service import CronService
    from nanobot.cron.types import CronJob
    from nanobot.session.manager import SessionManager
    from nanobot.utils.logging import setup_logging

    config = load_config()
    setup_logging(config)
    bus = MessageBus()
    provider = _make_provider(config)
    session_manager = SessionManager(config.workspace_path)

    cron_store_path = get_data_dir() / "cron" / "jobs.json"
    cron = CronService(cron_store_path)

    agent = AgentLoop(
        bus=bus, provider=provider, workspace=config.workspace_path,
        model=config.agents.defaults.model,
        max_iterations=config.agents.defaults.max_tool_iterations,
        memory_window=config.agents.defaults.memory_window,
        subagent_max_iterations=config.agents.defaults.subagent_max_iterations,
        brave_api_key=config.tools.web.search.api_key or None,
        exec_config=config.tools.exec,
        cron_service=cron,
        restrict_to_workspace=config.tools.restrict_to_workspace,
        session_manager=session_manager,
        config=config,
    )

    async def on_cron_job(job: CronJob) -> str | None:
        response = await agent.process_direct(
            job.payload.message, session_key=f"cron:{job.id}",
            channel=job.payload.channel or "cli", chat_id=job.payload.to or "direct",
        )
        if job.payload.deliver and job.payload.to:
            from nanobot.bus.events import OutboundMessage
            await bus.publish_outbound(OutboundMessage(
                channel=job.payload.channel or "cli", chat_id=job.payload.to, content=response or "",
            ))
        return response

    cron.on_job = on_cron_job
    channels = ChannelManager(config, bus, session_manager=session_manager)

    async def run():
        await cron.start()
        await asyncio.gather(agent.run(), channels.start_all())

    try:
        asyncio.run(run())
    except KeyboardInterrupt:
        pass


@app.command()
def agent(
    message: str = typer.Option(None, "--message", "-m", help="Message to send to the agent"),
    session_id: str = typer.Option("cli:default", "--session", "-s", help="Session ID"),
    markdown: bool = typer.Option(True, "--markdown/--no-markdown", help="Render output as Markdown"),
    logs: bool = typer.Option(False, "--logs/--no-logs", help="Show runtime logs"),
):
    """Interact with the agent directly."""
    from nanobot.agent.loop import AgentLoop
    from nanobot.bus.queue import MessageBus
    from nanobot.utils.logging import setup_logging

    config = load_config()
    setup_logging(config)
    bus = MessageBus()
    provider = _make_provider(config)

    agent_loop = AgentLoop(
        bus=bus, provider=provider, workspace=config.workspace_path,
        model=config.agents.defaults.model,
        max_iterations=config.agents.defaults.max_tool_iterations,
        memory_window=config.agents.defaults.memory_window,
        subagent_max_iterations=config.agents.defaults.subagent_max_iterations,
        brave_api_key=config.tools.web.search.api_key or None,
        exec_config=config.tools.exec,
        restrict_to_workspace=config.tools.restrict_to_workspace,
        config=config,
    )

    if message:
        async def run_once():
            await agent_loop.process_direct(
                message, session_id,
                stream_callback=lambda chunk: console.print(chunk, end=""),
            )
            console.print()
        asyncio.run(run_once())
    else:
        _init_prompt_session()
        console.print(f"{__logo__} Interactive mode (type [bold]exit[/bold] to quit)\n")

        async def run_interactive():
            while True:
                try:
                    user_input = await _read_interactive_input_async()
                    command = user_input.strip()
                    if not command:
                        continue
                    if _is_exit_command(command):
                        break

                    if command == "/explain":
                        from nanobot.agent.work_log_manager import get_work_log_manager
                        manager = get_work_log_manager()
                        console.print(manager.get_formatted_log("detailed"))
                        continue

                    response = await agent_loop.process_direct(user_input, session_id)
                    _print_agent_response(response, render_markdown=markdown)
                except KeyboardInterrupt:
                    break
        asyncio.run(run_interactive())


@app.command("explain")
def explain_command(mode: str = "detailed", session: str = None):
    """Explain the last decision."""
    from nanobot.agent.work_log_manager import get_work_log_manager
    manager = get_work_log_manager()
    log = manager.get_log_by_session(session) if session else manager.get_last_log()
    if not log:
        console.print("[yellow]No work log found.[/yellow]")
        return
    console.print(manager.get_formatted_log(mode))


channels_app = typer.Typer(help="Manage channels")
app.add_typer(channels_app, name="channels")

@channels_app.command("status")
def channels_status():
    """Show channel status."""
    config = load_config()
    table = Table(title="Channel Status")
    table.add_column("Channel", style="cyan")
    table.add_column("Enabled", style="green")
    for name in ["whatsapp", "telegram", "discord", "feishu", "slack", "email"]:
        c = getattr(config.channels, name)
        table.add_row(name.capitalize(), "✓" if c.enabled else "✗")
    console.print(table)


if __name__ == "__main__":
    app()

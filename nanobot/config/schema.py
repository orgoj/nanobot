"""Configuration schema using Pydantic."""

from pathlib import Path

from pydantic import BaseModel, ConfigDict, Field
from pydantic_settings import BaseSettings


class WhatsAppConfig(BaseModel):
    """WhatsApp channel configuration."""

    enabled: bool = False
    bridge_url: str = "ws://localhost:3001"
    allow_from: list[str] = Field(default_factory=list)  # Allowed phone numbers


class TelegramConfig(BaseModel):
    """Telegram channel configuration."""

    enabled: bool = False
    token: str = ""  # Bot token from @BotFather
    allow_from: list[str] = Field(default_factory=list)  # Allowed user IDs or usernames
    proxy: str | None = (
        None  # HTTP/SOCKS5 proxy URL, e.g. "http://127.0.0.1:7890" or "socks5://127.0.0.1:1080"
    )


class FeishuConfig(BaseModel):
    """Feishu/Lark channel configuration using WebSocket long connection."""

    enabled: bool = False
    app_id: str = ""  # App ID from Feishu Open Platform
    app_secret: str = ""  # App Secret from Feishu Open Platform
    encrypt_key: str = ""  # Encrypt Key for event subscription (optional)
    verification_token: str = ""  # Verification Token for event subscription (optional)
    allow_from: list[str] = Field(default_factory=list)  # Allowed user open_ids
    render_markdown: bool = True  # Render markdown as rich text (post format)
    reaction_emoji: str = "THUMBSUP"  # Emoji reaction on received messages
    streaming: bool = (
        True  # Enable streaming output with CardKit (requires cardkit:card:write permission)
    )


class DingTalkConfig(BaseModel):
    """DingTalk channel configuration using Stream mode."""

    enabled: bool = False
    client_id: str = ""  # AppKey
    client_secret: str = ""  # AppSecret
    allow_from: list[str] = Field(default_factory=list)  # Allowed staff_ids


class DiscordConfig(BaseModel):
    """Discord channel configuration."""

    enabled: bool = False
    token: str = ""  # Bot token from Discord Developer Portal
    allow_from: list[str] = Field(default_factory=list)  # Allowed user IDs
    gateway_url: str = "wss://gateway.discord.gg/?v=10&encoding=json"
    intents: int = 37377  # GUILDS + GUILD_MESSAGES + DIRECT_MESSAGES + MESSAGE_CONTENT


class EmailConfig(BaseModel):
    """Email channel configuration (IMAP inbound + SMTP outbound)."""

    enabled: bool = False
    consent_granted: bool = False  # Explicit owner permission to access mailbox data

    # IMAP (receive)
    imap_host: str = ""
    imap_port: int = 993
    imap_username: str = ""
    imap_password: str = ""
    imap_mailbox: str = "INBOX"
    imap_use_ssl: bool = True

    # SMTP (send)
    smtp_host: str = ""
    smtp_port: int = 587
    smtp_username: str = ""
    smtp_password: str = ""
    smtp_use_tls: bool = True
    smtp_use_ssl: bool = False
    from_address: str = ""

    # Behavior
    auto_reply_enabled: bool = (
        True  # If false, inbound email is read but no automatic reply is sent
    )
    poll_interval_seconds: int = 30
    mark_seen: bool = True
    max_body_chars: int = 12000
    subject_prefix: str = "Re: "
    allow_from: list[str] = Field(default_factory=list)  # Allowed sender email addresses


class MochatMentionConfig(BaseModel):
    """Mochat mention behavior configuration."""

    require_in_groups: bool = False


class MochatGroupRule(BaseModel):
    """Mochat per-group mention requirement."""

    require_mention: bool = False


class MochatConfig(BaseModel):
    """Mochat channel configuration."""

    enabled: bool = False
    base_url: str = "https://mochat.io"
    socket_url: str = ""
    socket_path: str = "/socket.io"
    socket_disable_msgpack: bool = False
    socket_reconnect_delay_ms: int = 1000
    socket_max_reconnect_delay_ms: int = 10000
    socket_connect_timeout_ms: int = 10000
    refresh_interval_ms: int = 30000
    watch_timeout_ms: int = 25000
    watch_limit: int = 100
    retry_delay_ms: int = 500
    max_retry_attempts: int = 0  # 0 means unlimited retries
    claw_token: str = ""
    agent_user_id: str = ""
    sessions: list[str] = Field(default_factory=list)
    panels: list[str] = Field(default_factory=list)
    allow_from: list[str] = Field(default_factory=list)
    mention: MochatMentionConfig = Field(default_factory=MochatMentionConfig)
    groups: dict[str, MochatGroupRule] = Field(default_factory=dict)
    reply_delay_mode: str = "non-mention"  # off | non-mention
    reply_delay_ms: int = 120000


class SlackDMConfig(BaseModel):
    """Slack DM policy configuration."""

    enabled: bool = True
    policy: str = "open"  # "open" or "allowlist"
    allow_from: list[str] = Field(default_factory=list)  # Allowed Slack user IDs


class SlackConfig(BaseModel):
    """Slack channel configuration."""

    enabled: bool = False
    mode: str = "socket"  # "socket" supported
    webhook_path: str = "/slack/events"
    bot_token: str = ""  # xoxb-...
    app_token: str = ""  # xapp-...
    user_token_read_only: bool = True
    group_policy: str = "mention"  # "mention", "open", "allowlist"
    group_allow_from: list[str] = Field(default_factory=list)  # Allowed channel IDs if allowlist
    dm: SlackDMConfig = Field(default_factory=SlackDMConfig)


class QQConfig(BaseModel):
    """QQ channel configuration using botpy SDK."""

    enabled: bool = False
    app_id: str = ""  # AppID from q.qq.com
    secret: str = ""  # AppSecret from q.qq.com
    allow_from: list[str] = Field(default_factory=list)


class ChannelsConfig(BaseModel):
    """Configuration for chat channels."""

    whatsapp: WhatsAppConfig = Field(default_factory=WhatsAppConfig)
    telegram: TelegramConfig = Field(default_factory=TelegramConfig)
    discord: DiscordConfig = Field(default_factory=DiscordConfig)
    feishu: FeishuConfig = Field(default_factory=FeishuConfig)
    mochat: MochatConfig = Field(default_factory=MochatConfig)
    dingtalk: DingTalkConfig = Field(default_factory=DingTalkConfig)
    email: EmailConfig = Field(default_factory=EmailConfig)
    slack: SlackConfig = Field(default_factory=SlackConfig)
    qq: QQConfig = Field(default_factory=QQConfig)


class AgentFeaturesConfig(BaseModel):
    """Agentic features configuration."""

    multi_agent: bool = False  # Enable instructions for specialized model delegation
    journaling: bool = False  # Enable strict journaling requirements


class AgentDefaults(BaseModel):
    """Default agent configuration."""

    workspace: str = "~/.nanobot/workspace"
    model: str = "anthropic/claude-opus-4-5"
    max_tokens: int = 8192
    temperature: float = 0.7
    max_tool_iterations: int = 20
    memory_window: int = 50
    subagent_max_iterations: int = 25
    startup_prompt: str | None = None
    startup_target: str = "cli:direct"
    heartbeat_on_start: bool = False
    heartbeat_target: str = "cli:direct"
    stream_intermediate_responses: bool = False  # If True, send intermediate thoughts to user
    features: AgentFeaturesConfig = Field(default_factory=AgentFeaturesConfig)


class AgentsConfig(BaseModel):
    """Agent configuration."""

    defaults: AgentDefaults = Field(default_factory=AgentDefaults)


class ProviderConfig(BaseModel):
    """LLM provider configuration."""

    api_key: str = ""
    api_base: str | None = None
    extra_headers: dict[str, str] | None = None


class ProvidersConfig(BaseModel):
    """Configuration for LLM providers."""

    anthropic: ProviderConfig = Field(default_factory=ProviderConfig)
    openai: ProviderConfig = Field(default_factory=ProviderConfig)
    openrouter: ProviderConfig = Field(default_factory=ProviderConfig)
    deepseek: ProviderConfig = Field(default_factory=ProviderConfig)
    groq: ProviderConfig = Field(default_factory=ProviderConfig)
    zhipu: ProviderConfig = Field(default_factory=ProviderConfig)
    dashscope: ProviderConfig = Field(default_factory=ProviderConfig)
    vllm: ProviderConfig = Field(default_factory=ProviderConfig)
    gemini: ProviderConfig = Field(default_factory=ProviderConfig)
    moonshot: ProviderConfig = Field(default_factory=ProviderConfig)
    minimax: ProviderConfig = Field(default_factory=ProviderConfig)
    aihubmix: ProviderConfig = Field(default_factory=ProviderConfig)


class GatewayConfig(BaseModel):
    """Gateway/server configuration."""

    host: str = "0.0.0.0"
    port: int = 18790


class HeartbeatConfig(BaseModel):
    """Heartbeat service configuration."""

    interval_s: int = 30 * 60  # 30 minutes by default


class WebSearchConfig(BaseModel):
    """Web search tool configuration."""

    api_key: str = ""
    max_results: int = 5


class WebToolsConfig(BaseModel):
    """Web tools configuration."""

    search: WebSearchConfig = Field(default_factory=WebSearchConfig)


class ExecToolConfig(BaseModel):
    """Shell exec tool configuration."""

    timeout: int = 60


class ToolsConfig(BaseModel):
    """Tools configuration."""

    web: WebToolsConfig = Field(default_factory=WebToolsConfig)
    exec: ExecToolConfig = Field(default_factory=ExecToolConfig)
    restrict_to_workspace: bool = False
    evolutionary: bool = False
    allowed_paths: list[str] = Field(default_factory=list)
    protected_paths: list[str] = Field(default_factory=lambda: ["~/.nanobot/config.json"])


class RoutingTierConfig(BaseModel):
    """Configuration for a routing tier."""

    model: str
    cost_per_mtok: float = 1.0
    secondary_model: str | None = None


class RoutingTiersConfig(BaseModel):
    """Configuration for all routing tiers."""

    simple: RoutingTierConfig = Field(
        default_factory=lambda: RoutingTierConfig(
            model="deepseek/deepseek-chat-v3-0324",
            cost_per_mtok=0.27,
            secondary_model="deepseek/deepseek-chat-v3.1",
        )
    )
    medium: RoutingTierConfig = Field(
        default_factory=lambda: RoutingTierConfig(
            model="openai/gpt-4.1-mini", cost_per_mtok=0.40, secondary_model="openai/gpt-4o-mini"
        )
    )
    complex: RoutingTierConfig = Field(
        default_factory=lambda: RoutingTierConfig(
            model="anthropic/claude-sonnet-4.5",
            cost_per_mtok=3.0,
            secondary_model="anthropic/claude-sonnet-4",
        )
    )
    reasoning: RoutingTierConfig = Field(
        default_factory=lambda: RoutingTierConfig(
            model="openai/o3", cost_per_mtok=2.0, secondary_model="openai/gpt-4o"
        )
    )
    coding: RoutingTierConfig = Field(
        default_factory=lambda: RoutingTierConfig(
            model="moonshotai/kimi-k2.5",
            cost_per_mtok=0.45,
            secondary_model="anthropic/claude-sonnet-4",
        )
    )


class ClientClassifierConfig(BaseModel):
    """Configuration for client-side classifier."""

    min_confidence: float = 0.85


class LLMClassifierConfig(BaseModel):
    """Configuration for LLM-assisted classifier."""

    model: str = "gpt-4o-mini"
    timeout_ms: int = 500
    secondary_model: str | None = None


class StickyRoutingConfig(BaseModel):
    """Configuration for sticky routing behavior."""

    context_window: int = 5
    downgrade_confidence: float = 0.9


class AutoCalibrationConfig(BaseModel):
    """Configuration for auto-calibration."""

    enabled: bool = True
    interval: str = "24h"
    min_classifications: int = 50
    max_patterns: int = 100
    backup_before_calibration: bool = True


class RoutingConfig(BaseModel):
    """Configuration for smart routing."""

    enabled: bool = False
    tiers: RoutingTiersConfig = Field(default_factory=RoutingTiersConfig)
    client_classifier: ClientClassifierConfig = Field(default_factory=ClientClassifierConfig)
    llm_classifier: LLMClassifierConfig = Field(default_factory=LLMClassifierConfig)
    sticky: StickyRoutingConfig = Field(default_factory=StickyRoutingConfig)
    auto_calibration: AutoCalibrationConfig = Field(default_factory=AutoCalibrationConfig)


class BackgroundConfig(BaseModel):
    """Background processing configuration for memory system."""

    enabled: bool = True
    interval_seconds: int = 60
    quiet_threshold_seconds: int = 30


class EmbeddingConfig(BaseModel):
    """Embedding provider configuration."""

    provider: str = "local"
    local_model: str = "BAAI/bge-small-en-v1.5"
    api_model: str = "qwen/qwen3-embedding-0.6b"
    api_fallback: bool = True
    cache_embeddings: bool = True
    lazy_load: bool = True


class ExtractionConfig(BaseModel):
    """Entity extraction configuration."""

    enabled: bool = True
    provider: str = "gliner2"
    gliner2_model: str = "fastino/gliner2-base-v1"
    interval_seconds: int = 60
    batch_size: int = 20
    api_fallback: bool = False
    api_model: str = ""


class SummaryConfig(BaseModel):
    """Summary node configuration."""

    staleness_threshold: int = 10
    max_refresh_batch: int = 20
    model: str = ""


class LearningConfig(BaseModel):
    """Learning and preferences configuration."""

    enabled: bool = True
    decay_days: int = 14
    max_learnings: int = 200
    relevance_decay_rate: float = 0.05


class MemoryContextConfig(BaseModel):
    """Context assembly configuration for TurboMemory."""

    total_budget: int = 4000
    always_include_preferences: bool = True


class SessionCompactionConfig(BaseModel):
    """Session compaction configuration for long conversations."""

    enabled: bool = True
    mode: str = "summary"
    threshold_percent: float = 0.8
    target_tokens: int = 3000
    min_messages: int = 10
    max_messages: int = 100
    preserve_recent: int = 20
    preserve_tool_chains: bool = True
    summary_chunk_size: int = 10
    enable_memory_flush: bool = True


class EnhancedContextConfig(BaseModel):
    """Enhanced context assembly with real-time monitoring."""

    max_context_tokens: int = 8000
    response_buffer: int = 1000
    memory_budget_percent: float = 0.35
    history_budget_percent: float = 0.35
    system_budget_percent: float = 0.20
    enable_real_time_tracking: bool = True
    show_context_percentage: bool = True
    warning_threshold: float = 0.70
    compaction_threshold: float = 0.80
    enable_priority_truncation: bool = True
    min_history_messages: int = 10
    preserve_user_preferences: bool = True


class PrivacyConfig(BaseModel):
    """Privacy and security configuration."""

    auto_redact_pii: bool = True
    auto_redact_credentials: bool = True
    excluded_patterns: list[str] = Field(
        default_factory=lambda: ["password", "api_key", "secret", "token", "credential"]
    )


class SecurityConfig(BaseModel):
    """Security and skill scanning configuration."""

    enabled: bool = True
    strict_mode: bool = False
    block_on_critical: bool = True
    block_on_high: bool = True
    scan_on_install: bool = True
    scan_on_load: bool = False
    allowed_shell_commands: list[str] = Field(
        default_factory=lambda: ["git", "npm", "node", "python", "python3", "pip", "pnpm", "yarn"]
    )
    blocked_patterns: list[str] = Field(
        default_factory=lambda: [
            "curl.*\\|.*bash",
            "curl.*\\|.*sh",
            "wget.*\\|.*bash",
            "wget.*\\|.*sh",
            "sudo",
            "rm -rf /",
            "rm -rf /*",
            "> /etc/",
            "> ~/.ssh/",
        ]
    )
    allow_network_installs: bool = False
    sandbox_skills: bool = False


class TurboMemoryConfig(BaseModel):
    """Turbo memory system configuration."""

    enabled: bool = True
    db_path: str = "memory/memory.db"

    background: BackgroundConfig = Field(default_factory=BackgroundConfig)
    embedding: EmbeddingConfig = Field(default_factory=EmbeddingConfig)
    extraction: ExtractionConfig = Field(default_factory=ExtractionConfig)
    summary: SummaryConfig = Field(default_factory=SummaryConfig)
    learning: LearningConfig = Field(default_factory=LearningConfig)
    context: MemoryContextConfig = Field(default_factory=MemoryContextConfig)
    privacy: PrivacyConfig = Field(default_factory=PrivacyConfig)
    session_compaction: SessionCompactionConfig = Field(default_factory=SessionCompactionConfig)
    enhanced_context: EnhancedContextConfig = Field(default_factory=EnhancedContextConfig)


class WorkLogsConfig(BaseModel):
    """Work logs configuration."""

    enabled: bool = True
    storage: str = "sqlite"
    retention_days: int = 30
    show_in_response: bool = False
    default_mode: str = "summary"
    log_tool_calls: bool = True
    log_routing_decisions: bool = True
    min_confidence_to_log: float = 0.0
    beta: bool = False


class LegacyContextConfig(BaseModel):
    """Legacy context builder configuration."""

    context_plugin_package: str = "nanobot.agent.context"
    context_plugin_class: str = "ContextBuilder"
    context_plugin_config: dict[str, str] | None = None


class LoggingConfig(BaseModel):
    """Logging configuration."""

    file_logging_enabled: bool = False
    file_log_path: str | None = None
    log_full_messages: bool = False
    log_full_tool_args: bool = False


class LegacyMemoryConfig(BaseModel):
    """Legacy file-based memory configuration."""

    max_long_term_lines: int = 50
    max_daily_lines: int = 100
    include_recent_days: int = 3


class Config(BaseSettings):
    """Root configuration for nanobot."""

    agents: AgentsConfig = Field(default_factory=AgentsConfig)
    channels: ChannelsConfig = Field(default_factory=ChannelsConfig)
    providers: ProvidersConfig = Field(default_factory=ProvidersConfig)
    gateway: GatewayConfig = Field(default_factory=GatewayConfig)
    heartbeat: HeartbeatConfig = Field(default_factory=HeartbeatConfig)
    tools: ToolsConfig = Field(default_factory=ToolsConfig)
    routing: RoutingConfig = Field(default_factory=RoutingConfig)
    memory: TurboMemoryConfig = Field(default_factory=TurboMemoryConfig)
    security: SecurityConfig = Field(default_factory=SecurityConfig)
    work_logs: WorkLogsConfig = Field(default_factory=WorkLogsConfig)
    context: LegacyContextConfig = Field(default_factory=LegacyContextConfig)
    logging: LoggingConfig = Field(default_factory=LoggingConfig)
    legacy_memory: LegacyMemoryConfig = Field(default_factory=LegacyMemoryConfig)

    @property
    def workspace_path(self) -> Path:
        """Get expanded workspace path."""
        from nanobot.utils.helpers import get_root_path

        configured = Path(self.agents.defaults.workspace).expanduser()
        root = get_root_path()

        if str(root) != str(Path.home()) and str(configured) == str(
            Path.home() / ".nanobot" / "workspace"
        ):
            return root / ".nanobot" / "workspace"

        return configured

    def _match_provider(
        self, model: str | None = None
    ) -> tuple["ProviderConfig | None", str | None]:
        """Match provider config and its registry name. Returns (config, spec_name)."""
        from nanobot.providers.registry import PROVIDERS, find_by_name

        model_lower = (model or self.agents.defaults.model).lower()

        if "/" in model_lower:
            prefix = model_lower.split("/")[0]
            spec = find_by_name(prefix)
            if spec:
                p = getattr(self.providers, spec.name, None)
                if p and p.api_key:
                    return p, spec.name

        for spec in PROVIDERS:
            p = getattr(self.providers, spec.name, None)
            if p and any(kw in model_lower for kw in spec.keywords) and p.api_key:
                return p, spec.name

        for spec in PROVIDERS:
            p = getattr(self.providers, spec.name, None)
            if p and p.api_key:
                return p, spec.name
        return None, None

    def get_provider(self, model: str | None = None) -> ProviderConfig | None:
        """Get matched provider config."""
        p, _ = self._match_provider(model)
        return p

    def get_provider_name(self, model: str | None = None) -> str | None:
        """Get the registry name of the matched provider."""
        _, name = self._match_provider(model)
        return name

    def get_api_key(self, model: str | None = None) -> str | None:
        """Get API key for the given model."""
        p = self.get_provider(model)
        return p.api_key if p else None

    def get_api_base(self, model: str | None = None) -> str | None:
        """Get API base URL for the given model."""
        from nanobot.providers.registry import find_by_name

        p, name = self._match_provider(model)
        if p and p.api_base:
            return p.api_base
        if name:
            spec = find_by_name(name)
            if spec and spec.is_gateway and spec.default_api_base:
                return spec.default_api_base
        return None

    model_config = ConfigDict(env_prefix="NANOBOT_", env_nested_delimiter="__")

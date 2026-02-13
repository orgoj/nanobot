# Proposal: nanobot-turbo Memory System v2 (REVISED)

## Executive Summary

Replace the current flat-file memory system with a 3-layer local-first memory architecture. This revision incorporates lessons from technical review and optimizes for nanobot's existing architecture.

**Key Changes from Original Proposal:**
- ✅ GLiNER2-base as default extractor (superior accuracy, manageable resource footprint)
- ✅ English-only embeddings for v1 (no multi-language support exists in current codebase)
- ✅ SQLite WAL mode for better concurrency
- ✅ TUI-style model downloads with progress bars
- ✅ Equal cross-channel weighting (removed complexity)
- ✅ Lazy model loading to improve startup time

**Design Principles:**
- No LLM calls on the hot path (context assembly is pure lookup)
- Local-first (works offline, zero ongoing cost for embeddings + extraction)
- Graceful degradation (every layer can fail independently)
- Backward-compatible (existing JSONL sessions preserved)
- Modular extractors (swap GLiNER2, spaCy, or API without changing core)

---

## Current State

### What Exists

```
User message → Session (JSONL, last 50 msgs) → System prompt
                                                  ├── MEMORY.md (agent writes manually)
                                                  ├── YYYY-MM-DD.md (agent writes manually)
                                                  ├── SOUL.md, USER.md, etc. (static)
                                                  └── Skills (static)
```

### Key Limitations
- Agent must manually decide to write to MEMORY.md (passive memory)
- Hard cutoff at 50 messages, no summarization of dropped messages
- No entity tracking, no relationship mapping, no semantic search
- No automatic learning from user feedback
- Tool calls and reasoning chains are discarded after each request
- No cross-session context (Telegram can't see CLI history)
- `get_recent_memories(days=7)` exists but is never called (dead code)
- No configurable context budget (everything concatenated blindly)
- **No language/i18n support exists in codebase** (English-only is acceptable for v1)

---

## Proposed Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                    LAYER 1: Event Log                        │
│  Immutable record of ALL interactions                        │
│  SQLite table: events                                        │
│  Fields: timestamp, channel, direction, event_type,          │
│          content, content_embedding, session_key,            │
│          parent_event_id, extraction_status                  │
│  Stores: user msgs, assistant msgs, tool calls, tool results │
└─────────────────────┬───────────────────────────────────────┘
                      │ Background extraction (every 60s)
                      │ GLiNER2 NER/relations + spaCy fallback
                      v
┌─────────────────────────────────────────────────────────────┐
│                    LAYER 2: Knowledge Graph                  │
│  Structured knowledge extracted from events                  │
│  SQLite tables: entities, edges, facts, topics               │
│  Entities: people, orgs, tools, concepts (with embeddings)   │
│  Edges: relationships between entities (with strength)     │
│  Facts: subject-predicate-object triplets                    │
│  Topics: theme clusters linked to events                     │
└─────────────────────┬───────────────────────────────────────┘
                      │ Staleness-driven refresh
                      │ Batch summarization when threshold reached
                      v
┌─────────────────────────────────────────────────────────────┐
│                    LAYER 3: Hierarchical Summaries            │
│  Pre-computed summaries organized as a tree                  │
│  SQLite table: summary_nodes                                 │
│  Tree: root → channel → entity_type → entity/topic           │
│  Special node: user_preferences (always in context)          │
│  Staleness counter per node, refresh when > 10 new events    │
└─────────────────────────────────────────────────────────────┘
          │
          │ Context assembly (no LLM calls, pure lookup)
          v
┌─────────────────────────────────────────────────────────────┐
│                    CONTEXT BUDGET                             │
│  Per-section token allocation (~4000 tokens total)           │
│  identity: 200  │ state: 150   │ knowledge: 500              │
│  channel: 300   │ entity: 400  │ topics: 400                 │
│  user_prefs: 300│ learnings: 200│ recent: 400                │
└─────────────────────────────────────────────────────────────┘
```

---

## Technology Stack

### Storage: SQLite with WAL Mode

```
~/.nanobot/workspace/memory/memory.db
```

Single file, zero config, perfect for single-user. **WAL mode enabled** for better concurrency:
- Allows readers during writes (no blocking)
- Better performance for concurrent access
- Automatic checkpointing

Tables:
- `events` - Immutable event log
- `entities` - People, orgs, concepts
- `edges` - Relationships between entities
- `facts` - Subject-predicate-object triplets
- `topics` - Theme clusters
- `event_topics` - Junction table
- `summary_nodes` - Hierarchical summary tree
- `learnings` - Self-improvement records

### Embeddings: Local-first via FastEmbed (English-only v1)

```
Model: BAAI/bge-small-en-v1.5
Size: 67MB on disk
RAM: ~200-400MB at runtime
Dimensions: 384
Quality: MTEB 62.2 (comparable to OpenAI text-embedding-3-small)
Runtime: ONNX (no PyTorch)
Fallback: qwen/qwen3-embedding-0.6b via OpenRouter ($0.01/M tokens)
Languages: English only (acceptable for v1 - no multi-lang in current codebase)
```

New dependency: `fastembed` (~50MB install, pulls `onnxruntime` + `tokenizers` + `numpy`)

**Future Enhancement**: BAAI/bge-m3 (100MB, multilingual, MTEB 79.9) when multi-language support is added.

### Extraction: GLiNER2 + spaCy Fallback

**Primary: GLiNER2-base (fastino/gliner2-base-v1)**
```
Parameters: 205M
Disk: ~60-80MB
RAM: ~400-600MB
Speed: ~2-3k docs/sec
Capabilities: Any entity type, relationships, schema-based extraction
Quality: State-of-the-art for CPU-based extraction
```

**Fallback: spaCy en_core_web_sm (lightweight option)**
```
Parameters: 12MB model
RAM: ~50-80MB
Speed: ~10k docs/sec
Capabilities: 18 entity types (PERSON, ORG, GPE, DATE, etc.), basic SVO
Use case: Resource-constrained environments, or when GLiNER2 unavailable
```

New dependencies: 
- `gliner2` (~80MB total)
- `spacy` + `en_core_web_sm` (~60MB, optional fallback)

### RAM Budget

| Component | RAM | Notes |
|-----------|-----|-------|
| OS + Python + Bot | ~500MB-1GB | Existing |
| FastEmbed + bge-small | ~200-400MB | New |
| GLiNER2-base | ~400-600MB | New (primary) |
| spaCy (fallback) | ~50-80MB | New (optional) |
| SQLite memory.db | ~10-50MB | New |
| **Total system** | **~1.8-2.2GB** | With GLiNER2 |
| **Total system** | **~1.3-1.6GB** | With spaCy only |
| **Free RAM** | **~5.8-6.2GB** | Plenty of headroom |

**Server Capacity**: ✅ 4 cores, 8GB RAM, 150GB disk handles this easily

---

## Data Models

### Event

```python
@dataclass
class Event:
    id: str                    # UUID
    timestamp: datetime
    channel: str               # cli, telegram, whatsapp, system
    direction: str             # inbound, outbound, internal
    event_type: str            # message, tool_call, tool_result, observation
    content: str               # Raw text
    content_embedding: bytes | None  # Packed float32 vector (384 dims)
    session_key: str           # channel:chat_id
    parent_event_id: str | None     # For threading (tool_result → tool_call)
    person_id: str | None      # Entity ID of the person involved
    tool_name: str | None      # For tool_call/tool_result events
    extraction_status: str     # pending, complete, skipped, failed
    metadata: dict             # Flexible extra data
    relevance_score: float = 1.0  # Decays over time unless re-mentioned
    last_accessed: datetime | None  # For relevance boost on access
```

### Entity

```python
@dataclass
class Entity:
    id: str                    # UUID
    name: str                  # Canonical name
    entity_type: str           # person, org, location, concept, tool, topic
    aliases: list[str]         # Alternative names
    description: str           # Brief description
    name_embedding: bytes | None
    source_event_ids: list[str]
    event_count: int           # How many events mention this entity
    first_seen: datetime
    last_seen: datetime
```

### Edge (Relationship)

```python
@dataclass
class Edge:
    id: str
    source_entity_id: str      # Entity A
    target_entity_id: str      # Entity B
    relation: str              # "works at", "likes", "knows"
    relation_type: str         # professional, social, technical, etc.
    strength: float            # 0.0-1.0 (incremented on re-mention)
    source_event_ids: list[str]
    first_seen: datetime
    last_seen: datetime
```

### Fact

```python
@dataclass
class Fact:
    id: str
    subject_entity_id: str
    predicate: str             # "prefers", "lives in", "is expert in"
    object_text: str           # Literal value or entity reference
    object_entity_id: str | None
    fact_type: str             # relation, attribute, preference, state
    confidence: float
    strength: float            # Incremented on re-mention
    source_event_ids: list[str]
    valid_from: datetime | None
    valid_to: datetime | None  # For temporal facts
```

### SummaryNode

```python
@dataclass
class SummaryNode:
    id: str
    node_type: str             # root, channel, entity, entity_type, topic, preferences
    key: str                   # "root", "channel:telegram", "entity:{id}", "user_preferences"
    parent_id: str | None
    summary: str               # LLM-generated text
    summary_embedding: bytes | None
    events_since_update: int   # Staleness counter
    last_updated: datetime
```

### Learning

```python
@dataclass
class Learning:
    id: str
    content: str               # The insight
    content_embedding: bytes | None
    source: str                # user_feedback, self_evaluation
    sentiment: str             # positive, negative, neutral
    confidence: float
    tool_name: str | None      # Tool-specific learning
    recommendation: str        # Actionable instruction
    superseded_by: str | None  # Contradiction resolution
    created_at: datetime
    updated_at: datetime       # For decay calculation (14-day half-life)
```

---

## Implementation Plan

### Phase 1: Foundation (SQLite + Event Log)
**Estimated effort: 3-5 days**

New files:
- `nanobot/memory/__init__.py` - Module exports
- `nanobot/memory/models.py` - All dataclasses above
- `nanobot/memory/store.py` - SQLite database manager with WAL mode
- `nanobot/memory/events.py` - Event logging (write events, query events)

Changes to existing files:
- `nanobot/agent/loop.py` - After each message exchange, log events to SQLite
- `pyproject.toml` - No new dependencies for Phase 1 (SQLite is built-in)

**WAL Mode Setup:**
```python
# In nanobot/memory/store.py
def _setup_database(self):
    self.conn.execute("PRAGMA journal_mode=WAL;")
    self.conn.execute("PRAGMA synchronous=NORMAL;")
    self.conn.execute("PRAGMA cache_size=10000;")
```

What this gives you:
- Complete, immutable record of all interactions
- Tool calls and reasoning chains preserved (currently discarded)
- Cross-session queryable history (all channels in one DB)
- Foundation for all subsequent phases

Backward compatibility:
- Existing JSONL session manager continues to work unchanged
- Events are logged IN ADDITION to JSONL (dual-write)
- No existing behavior changes

### Phase 2: Embeddings + Semantic Search + Lazy Loading
**Estimated effort: 2-3 days**

New files:
- `nanobot/memory/embeddings.py` - Embedding provider with lazy loading

Changes to existing files:
- `nanobot/memory/store.py` - Add embedding columns, cosine similarity search
- `nanobot/memory/events.py` - Embed event content on write (with lazy model load)
- `pyproject.toml` - Add `fastembed` dependency
- `nanobot/config/schema.py` - Add `MemoryConfig` with embedding settings

**Lazy Loading Implementation:**
```python
# In nanobot/memory/embeddings.py
class EmbeddingProvider:
    def __init__(self, config: MemoryConfig):
        self.config = config
        self._model = None  # Not loaded yet
        self._model_path = None
    
    def _ensure_model(self):
        """Lazy load model on first use."""
        if self._model is None:
            from fastembed import TextEmbedding
            self._model = TextEmbedding(self.config.embedding.local_model)
    
    def embed(self, text: str) -> list[float]:
        self._ensure_model()
        return next(self._model.embed([text]))
```

What this gives you:
- Semantic search over all past conversations
- "Search your memory for anything about pricing" actually works
- Foundation for knowledge graph extraction
- **No startup delay** - models download on first use

### Phase 3: Knowledge Graph Extraction (GLiNER2)
**Estimated effort: 5-7 days**

New files:
- `nanobot/memory/extraction.py` - Background extraction pipeline
- `nanobot/memory/graph.py` - Entity resolution, edge management, fact deduplication
- `nanobot/memory/extractors/gliner2_extractor.py` - GLiNER2 unified extraction
- `nanobot/memory/extractors/spacy_extractor.py` - spaCy fallback extractor

Changes to existing files:
- `nanobot/agent/loop.py` - Start background extraction task on agent startup
- `pyproject.toml` - Add `gliner2` dependency, optional `spacy`
- `nanobot/config/schema.py` - Add extraction config

Extraction pipeline:
```
Every 60 seconds:
  1. Check if user is actively chatting → back off if yes
  2. Fetch up to 20 pending events
  3. For each event:
     a. GLiNER2 → extract entities, relationships, facts (all in one pass)
     b. If GLiNER2 fails → fallback to spaCy for basic NER only
  4. Resolve entities (merge duplicates, update aliases)
  5. Create/update edges with strength tracking
  6. Store facts with deduplication
  7. Mark events as extraction_status = "complete"
```

**GLiNER2 Advantages:**
- Single forward pass for NER + relationships + structured extraction
- Custom entity types: "programming_language", "framework", "API_endpoint"
- Schema-based extraction: "works_at", "prefers", "expert_in"
- No need for separate heuristic rules

What this gives you:
- Automatic entity tracking (people, orgs, concepts, custom types)
- Relationship mapping ("John works at Acme Corp")
- Fact storage ("User prefers short emails")
- Background processing that doesn't slow down chat

### Phase 4: Hierarchical Summaries
**Estimated effort: 4-6 days**

New files:
- `nanobot/memory/summaries.py` - Summary tree management, staleness tracking, refresh logic

Changes to existing files:
- `nanobot/memory/extraction.py` - After extraction, increment staleness counters
- `nanobot/memory/extraction.py` - After extraction batch, trigger stale summary refresh

What this gives you:
- Pre-computed summaries for fast context assembly
- "What do you know about John Smith?" returns a summary, not raw events
- Summaries automatically refresh when enough new information accumulates
- Tree structure allows drill-down (root → channel → entity)

### Phase 5: Learning + User Preferences + Relevance Decay
**Estimated effort: 3-5 days**

New files:
- `nanobot/memory/learning.py` - Feedback detection, learning storage, contradiction resolution
- `nanobot/memory/preferences.py` - Aggregate learnings into user_preferences summary

Changes to existing files:
- `nanobot/memory/extraction.py` - Add feedback detection to extraction pipeline
- `nanobot/memory/summaries.py` - Add special `user_preferences` node (always in context)
- `nanobot/memory/events.py` - Add relevance_score decay logic

**Relevance Decay:**
```python
def update_relevance_scores(self):
    """Decay relevance of old events, boost recently accessed ones."""
    for event in self.get_old_events(days=30):
        days_old = (datetime.now() - event.timestamp).days
        event.relevance_score *= (0.95 ** days_old)  # 5% decay per day
        
    for event in self.get_recently_accessed(hours=24):
        event.relevance_score = min(1.0, event.relevance_score * 1.2)  # 20% boost
```

What this gives you:
- Bot learns from corrections: "Actually, I prefer shorter emails"
- Preferences persist across sessions and channels
- 14-day decay with re-boost (useful learnings survive, stale ones fade)
- Contradiction resolution (new preference supersedes old one)
- Relevance-based retrieval (important memories surface, old ones fade)

### Phase 6: Context Assembly + Retrieval + Privacy Controls
**Estimated effort: 3-4 days**

New files:
- `nanobot/memory/context.py` - Token-budgeted context assembly from summaries
- `nanobot/memory/retrieval.py` - Query interface (search, lookup, traverse)

Changes to existing files:
- `nanobot/agent/context.py` - Replace current `get_memory_context()` with summary-based assembly
- `nanobot/agent/loop.py` - Register memory tools

New agent tools:
- `search_memory` - Semantic search over events, entities, facts
- `get_entity` - Look up everything known about a person/org/concept
- `get_relationships` - Find connections between entities
- `recall` - Retrieve relevant context for a topic

**Privacy Controls:**
```python
class MemoryConfig:
    # Redaction patterns
    excluded_patterns: list[str] = ["password", "api_key", "secret", "token"]
    auto_redact_pii: bool = True  # Redact emails, phone numbers, SSNs
    auto_redact_credentials: bool = True  # Redact anything that looks like a key
```

What this gives you:
- Smart context assembly that respects token budgets
- Agent can actively query its own memory
- User can ask "What do you know about X?" and get a real answer
- Sensitive data automatically redacted from memory

### Phase 7: CLI Commands + Testing + Model Download TUI
**Estimated effort: 2-3 days**

Changes to existing files:
- `nanobot/cli/commands.py` - Add memory subcommands with TUI

New CLI commands:
```bash
nanobot memory init              # Initialize memory system (with TUI progress)
nanobot memory status            # Show memory stats (events, entities, summaries)
nanobot memory search "query"    # Semantic search
nanobot memory entities          # List known entities
nanobot memory entity "John"     # Show everything about John
nanobot memory summary           # Show root summary
nanobot memory forget "entity"   # Remove an entity and related data
nanobot memory export            # Export memory to JSON
nanobot memory import file.json  # Import memory from JSON
nanobot memory doctor            # Health check (integrity, models, etc.)
```

**TUI Model Download:**
```python
# In nanobot/memory/setup.py
from rich.progress import Progress, SpinnerColumn, TextColumn

def download_models_with_tui():
    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        transient=False,
    ) as progress:
        # Download embedding model
        task1 = progress.add_task("📦 Downloading embedding model...", total=None)
        download_model("BAAI/bge-small-en-v1.5")
        progress.update(task1, completed=True, description="[green]✓ Embedding model ready[/green]")
        
        # Download extraction model
        task2 = progress.add_task("📦 Downloading extraction model...", total=None)
        download_model("fastino/gliner2-base-v1")
        progress.update(task2, completed=True, description="[green]✓ Extraction model ready[/green]")
```

New test files:
- `tests/memory/test_store.py` - SQLite CRUD operations
- `tests/memory/test_events.py` - Event logging and querying
- `tests/memory/test_embeddings.py` - Embedding generation and search
- `tests/memory/test_extraction.py` - Entity/relationship extraction
- `tests/memory/test_summaries.py` - Summary tree and staleness
- `tests/memory/test_learning.py` - Feedback detection and contradiction resolution
- `tests/memory/test_context.py` - Token-budgeted context assembly

---

## Configuration Schema

```python
class MemoryConfig(BaseModel):
    """Configuration for the memory system."""
    enabled: bool = True
    db_path: str = "memory/memory.db"  # Relative to workspace

    class EmbeddingConfig(BaseModel):
        provider: str = "local"        # "local" or "api"
        local_model: str = "BAAI/bge-small-en-v1.5"
        api_model: str = "qwen/qwen3-embedding-0.6b"
        api_fallback: bool = True       # Fall back to API if local fails
        cache_embeddings: bool = True
        lazy_load: bool = True         # Download models on first use

    class ExtractionConfig(BaseModel):
        enabled: bool = True
        provider: str = "gliner2"      # "gliner2", "spacy", "api"
        gliner2_model: str = "fastino/gliner2-base-v1"
        spacy_model: str = "en_core_web_sm"
        interval_seconds: int = 60
        batch_size: int = 20
        api_fallback: bool = False     # Use LLM for complex extractions
        api_model: str = ""            # Uses LLM classifier model if empty
        activity_backoff: bool = True  # Back off when user is chatting

    class SummaryConfig(BaseModel):
        staleness_threshold: int = 10  # Events before refresh
        max_refresh_batch: int = 20    # Max nodes to refresh per cycle
        model: str = ""                # Uses LLM classifier model if empty

    class LearningConfig(BaseModel):
        enabled: bool = True
        decay_days: int = 14           # Half-life for learning relevance
        max_learnings: int = 200        # Max active learnings
        relevance_decay_rate: float = 0.05  # 5% per day

    class ContextConfig(BaseModel):
        total_budget: int = 4000       # Total token budget for memory context
        always_include_preferences: bool = True

    class PrivacyConfig(BaseModel):
        auto_redact_pii: bool = True
        auto_redact_credentials: bool = True
        excluded_patterns: list[str] = Field(default_factory=lambda: [
            "password", "api_key", "secret", "token", "credential"
        ])

    embedding: EmbeddingConfig = Field(default_factory=EmbeddingConfig)
    extraction: ExtractionConfig = Field(default_factory=ExtractionConfig)
    summary: SummaryConfig = Field(default_factory=SummaryConfig)
    learning: LearningConfig = Field(default_factory=LearningConfig)
    context: ContextConfig = Field(default_factory=ContextConfig)
    privacy: PrivacyConfig = Field(default_factory=PrivacyConfig)
```

Example config.json addition:
```json
{
  "memory": {
    "enabled": true,
    "embedding": {
      "provider": "local",
      "api_fallback": true,
      "lazy_load": true
    },
    "extraction": {
      "enabled": true,
      "provider": "gliner2",
      "interval_seconds": 60,
      "api_fallback": false
    },
    "learning": {
      "enabled": true,
      "decay_days": 14,
      "relevance_decay_rate": 0.05
    },
    "privacy": {
      "auto_redact_pii": true,
      "auto_redact_credentials": true
    }
  }
}
```

---

## New Dependencies

| Package | Size | Purpose | Phase | Lazy Load |
|---------|------|---------|-------|-----------|
| `fastembed` | ~50MB install | Local embeddings (ONNX) | Phase 2 | ✅ Yes |
| `gliner2` | ~80MB install | Advanced extraction | Phase 3 | ✅ Yes |
| `spacy` | ~30MB install | Fallback NER | Phase 3 | ✅ Optional |
| `en_core_web_sm` | ~12MB model | spaCy English model | Phase 3 | ✅ Optional |

**Total new disk (if all downloaded): ~170MB**
**Total new RAM (with GLiNER2): ~600-1000MB**
**RAM with spaCy only: ~250-480MB**

**No PyTorch, no TensorFlow, no GPU required.**

---

## Migration Strategy

### Existing JSONL Sessions
- Continue to work unchanged (dual-write approach)
- New events are logged to SQLite AND JSONL
- JSONL remains the source for `Session.get_history()` (sliding window)
- SQLite becomes the source for semantic search, entity queries, and summaries
- Optional future: one-time migration script to import historical JSONL into SQLite events

### Existing MEMORY.md + Daily Notes
- Continue to work as before
- Content from MEMORY.md is imported into the knowledge graph as facts/entities on first run
- Daily notes are imported as events on first run
- After migration, new memories go to SQLite; old files remain readable

### Existing Bootstrap Files (SOUL.md, USER.md, etc.)
- Unchanged. These are static identity files, not memory.
- Over time, `user_preferences` summary node may partially replace USER.md with learned preferences.

---

## File Map (New Files)

```
nanobot/memory/
├── __init__.py              # Module exports
├── models.py                # Event, Entity, Edge, Fact, Topic, SummaryNode, Learning
├── store.py                 # SQLite database manager (tables, CRUD, migrations, WAL mode)
├── events.py                # Event logging and querying
├── embeddings.py            # FastEmbed local + API fallback with lazy loading
├── graph.py                 # Entity resolution, edges, facts, dedup
├── extraction.py            # Background extraction pipeline + scheduling
├── extractors/
│   ├── __init__.py
│   ├── base.py              # Extractor interface
│   ├── gliner2_extractor.py # GLiNER2 unified extraction (primary)
│   └── spacy_extractor.py   # spaCy fallback (lightweight)
├── summaries.py             # Summary tree, staleness, refresh
├── learning.py              # Feedback detection, decay, contradictions
├── preferences.py           # User preferences aggregation
├── context.py               # Token-budgeted context assembly
├── retrieval.py             # Query interface (search, lookup, traverse)
└── setup.py                 # Model download with TUI progress

tests/memory/
├── __init__.py
├── test_store.py
├── test_events.py
├── test_embeddings.py
├── test_extraction.py
├── test_summaries.py
├── test_learning.py
└── test_context.py
```

---

## Risks and Mitigations

| Risk | Impact | Mitigation |
|------|--------|------------|
| GLiNER2 RAM usage too high | High | Fallback to spaCy (50-80MB) via config toggle |
| Model download failures | Medium | Lazy loading + retry logic + manual download command |
| SQLite write contention | Medium | WAL mode + activity-aware throttling |
| Extraction quality issues | Medium | Modular extractors: swap GLiNER2 → spaCy → API |
| Embedding model too large | Low | Configurable: disable local, use API-only, or disable entirely |
| Summary refresh costs money | Medium | Uses cheapest model; configurable threshold; can disable |
| Memory.db grows too large | Medium | Configurable retention + compression of old embeddings |
| Breaking context changes | High | Dual-mode: old context builder path preserved behind flag |
| Privacy concerns | Medium | Auto-redaction of PII/credentials; excluded patterns |

---

## Timeline Estimate

| Phase | Effort | Dependencies |
|-------|--------|-------------|
| Phase 1: Foundation (SQLite + Events + WAL) | 3-5 days | None |
| Phase 2: Embeddings + Search + Lazy Load | 2-3 days | Phase 1 |
| Phase 3: Knowledge Graph (GLiNER2) | 5-7 days | Phase 2 |
| Phase 4: Hierarchical Summaries | 4-6 days | Phase 3 |
| Phase 5: Learning + Preferences + Decay | 3-5 days | Phase 4 |
| Phase 6: Context Assembly + Privacy | 3-4 days | Phase 4, 5 |
| Phase 7: CLI + Testing + TUI | 2-3 days | All phases |
| **Total** | **22-33 days** | |

**Realistic timeline with buffer**: 4-5 weeks

**MVP Ship Point**: After Phase 3 (event logging + semantic search + entity extraction) = ~2-3 weeks

---

## Success Criteria

After full implementation:

1. **"What do you know about John?"** - Returns structured entity summary with relationships
2. **"Actually, I prefer shorter responses"** - Creates learning record, reflected in future responses
3. **Greeting "hi" after a week** - Bot recalls recent topics, ongoing tasks, and user preferences
4. **Cross-channel continuity** - Information shared on Telegram is available when chatting via CLI
5. **Zero-cost baseline** - With API fallback disabled, entire memory system runs locally at $0/month
6. **RAM under 2.5GB total** - Memory infrastructure uses <1GB on top of existing bot
7. **Privacy by default** - PII and credentials automatically redacted from memory
8. **No startup delay** - Models download on first use with beautiful TUI progress

---

## Comparison: Original vs Revised

| Aspect | Original Proposal | Revised (This Document) |
|--------|-------------------|------------------------|
| **Extractor** | spaCy primary + API fallback | GLiNER2 primary + spaCy fallback |
| **Languages** | Implied multi-lang via spaCy | **English-only v1** (no multi-lang in codebase) |
| **SQLite Mode** | Standard | **WAL mode** (better concurrency) |
| **Model Loading** | At startup | **Lazy loading** (on first use) |
| **Cross-channel** | Weighted scoring | **Equal weighting** (simpler) |
| **Relevance** | Staleness only | **+ Decay/re-boost** |
| **Privacy** | Not mentioned | **Auto-redaction of PII/credentials** |
| **TUI Downloads** | Not mentioned | **Rich progress bars** |
| **RAM (GLiNER2)** | N/A (didn't include) | **~400-600MB** (manageable) |
| **CLI Commands** | Basic | **+ `memory doctor` health check** |

---

## Detailed Design: Background Processing

The memory system requires background processing for extraction and maintenance without blocking interactive chat. For a single-user deployment, we use a minimal async loop rather than complex worker pools.

### Design Goals

1. **Non-blocking** - Chat never waits for background tasks
2. **Activity-aware** - Pause processing when user is active
3. **Lightweight** - Minimal code, minimal resources
4. **Reliable** - Failures are logged but don't crash the agent

### Architecture

```
┌─────────────────────────────────────────────────────────┐
│                     AgentLoop                            │
│  - Main message processing loop                          │
│  - Tracks user activity                                  │
│  - Runs BackgroundProcessor                              │
└─────────────────┬───────────────────────────────────────┘
                  │
                  v
┌─────────────────────────────────────────────────────────┐
│              BackgroundProcessor                         │
│  - Single async task loop                                │
│  - Runs every 60 seconds when user is inactive           │
│  - Processes: extraction → summaries → learning decay    │
└─────────────────────────────────────────────────────────┘
```

### Core Components

#### 1. ActivityTracker

Tracks user chat activity to determine when it's safe to run background tasks.

```python
from datetime import datetime, timedelta
from dataclasses import dataclass

@dataclass
class ActivityTracker:
    """Tracks user activity for activity-aware task scheduling."""
    quiet_threshold_seconds: int = 30
    last_activity: datetime = None
    
    def mark_activity(self):
        """Call when user sends a message."""
        self.last_activity = datetime.now()
    
    def is_user_active(self) -> bool:
        """True if user was active in the last N seconds."""
        if not self.last_activity:
            return False
        return (datetime.now() - self.last_activity).seconds < self.quiet_threshold_seconds
```

#### 2. BackgroundProcessor

Minimal background task runner for single-user deployment.

```python
import asyncio
from loguru import logger
from dataclasses import dataclass
from typing import Optional, Callable

@dataclass
class BackgroundProcessor:
    """Lightweight background processor for memory maintenance tasks."""
    memory_store: 'MemoryStore'
    activity_tracker: ActivityTracker
    interval_seconds: int = 60
    
    def __post_init__(self):
        self.running = False
        self._task: Optional[asyncio.Task] = None
    
    async def start(self):
        """Start the background loop."""
        self.running = True
        self._task = asyncio.create_task(self._loop())
        logger.info("Background processor started")
    
    async def stop(self):
        """Stop gracefully."""
        self.running = False
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
        logger.info("Background processor stopped")
    
    async def _loop(self):
        """Main loop: sleep, check activity, process."""
        while self.running:
            await asyncio.sleep(self.interval_seconds)
            
            if self.activity_tracker.is_user_active():
                continue  # User chatting, skip this cycle
            
            try:
                await self._process_cycle()
            except Exception as e:
                logger.error(f"Background processing error: {e}")
                # Log and continue - will retry next cycle
    
    async def _process_cycle(self):
        """Process one cycle of background tasks."""
        # 1. Extract entities from pending events
        pending = await self.memory_store.get_pending_events(limit=20)
        if pending:
            from nanobot.memory.extraction import extract_entities
            for event in pending:
                entities = await extract_entities(event)
                await self.memory_store.save_entities(entities)
                await self.memory_store.mark_event_extracted(event.id)
            logger.info(f"Extracted entities from {len(pending)} events")
        
        # 2. Refresh stale summaries (every 5th cycle = every 5 min)
        if asyncio.get_event_loop().time() % 300 < 60:  # Approximate 5 min
            from nanobot.memory.summaries import refresh_stale_summaries
            refreshed = await refresh_stale_summaries(self.memory_store)
            if refreshed:
                logger.info(f"Refreshed {refreshed} summary nodes")
        
        # 3. Apply learning decay (every hour)
        if asyncio.get_event_loop().time() % 3600 < 60:  # Approximate 1 hour
            from nanobot.memory.learning import decay_learnings
            decayed = await decay_learnings(self.memory_store)
            if decayed:
                logger.info(f"Applied decay to {decayed} learnings")
```

### Configuration

Add to MemoryConfig:

```python
class BackgroundConfig(BaseModel):
    """Background processing configuration."""
    enabled: bool = True
    interval_seconds: int = 60          # Check every 60s
    quiet_threshold_seconds: int = 30   # User inactive for 30s = safe to run

class MemoryConfig(BaseModel):
    # ... existing fields ...
    background: BackgroundConfig = Field(default_factory=BackgroundConfig)
```

Example config:
```json
{
  "memory": {
    "background": {
      "enabled": true,
      "interval_seconds": 60,
      "quiet_threshold_seconds": 30
    }
  }
}
```

### Integration with AgentLoop

```python
# nanobot/agent/loop.py

class AgentLoop:
    def __init__(self, ..., memory_config: Optional[MemoryConfig] = None):
        # Existing init...
        
        # Memory system (optional)
        self.memory_store = None
        self.background_processor = None
        
        if memory_config and memory_config.enabled:
            from nanobot.memory.store import MemoryStore
            from nanobot.memory.background import ActivityTracker, BackgroundProcessor
            
            self.memory_store = MemoryStore(memory_config)
            self.activity_tracker = ActivityTracker(
                quiet_threshold_seconds=memory_config.background.quiet_threshold_seconds
            )
            self.background_processor = BackgroundProcessor(
                memory_store=self.memory_store,
                activity_tracker=self.activity_tracker,
                interval_seconds=memory_config.background.interval_seconds
            )
    
    async def start(self):
        """Start the agent loop and background processing."""
        # Existing startup...
        
        if self.background_processor:
            await self.background_processor.start()
        
        logger.info("Agent loop started")
    
    async def stop(self):
        """Stop the agent loop gracefully."""
        if self.background_processor:
            await self.background_processor.stop()
        
        # Existing shutdown...
        logger.info("Agent loop stopped")
    
    async def process_message(self, message: InboundMessage):
        """Process a user message."""
        # Mark user activity
        if self.activity_tracker:
            self.activity_tracker.mark_activity()
        
        # Log event to memory if enabled
        if self.memory_store:
            await self.memory_store.log_event(
                channel=message.channel,
                direction="inbound",
                content=message.content
            )
        
        # Existing message processing...
```

### Why This Design?

**Compared to complex WorkerPool/TaskQueue approach:**

| Aspect | Complex Design | This Design |
|--------|---------------|-------------|
| **Lines of code** | ~600 | ~80 |
| **Workers** | 2+ concurrent | 1 (sequential) |
| **Queue management** | Priority queue + dedup | None needed |
| **Memory overhead** | ~5-10MB | ~1MB |
| **Suitable for** | Multi-user, high throughput | Single user, casual use |
| **Debuggability** | Hard (concurrency) | Easy (sequential) |

**For a single-user personal assistant:**
- User generates ~1 message per minute at most
- Background tasks run every 60s, process ~20 events
- One sequential worker is more than enough
- Simpler code = fewer bugs, easier maintenance

### Future Enhancement

If you later need multi-user support or higher throughput, you can upgrade to the WorkerPool/TaskQueue architecture without changing the public API. The ActivityTracker and BackgroundProcessor interface remain the same.

## Detailed Design: Entity Resolution Algorithm

Entity resolution is the core deduplication mechanism in Phase 3 (Knowledge Graph Extraction). It prevents the knowledge graph from fragmenting into redundant entities ("John", "john", "John Smith", "J. Smith" should all resolve to one canonical entity).

### Design Goals

1. **High precision** (false positive merges are worse than false negatives)
2. **Fast execution** (<50ms p99 for typical workloads)
3. **No LLM calls on hot path** (everything is heuristic or embedding-based)
4. **Progressive resolution** (cheap fast checks first, expensive checks only when necessary)
5. **Auditable** (track why entities were merged, support manual correction)

### Resolution Pipeline (5 Layers)

```
New mention → Layer 1: Rule-based exact/case-insensitive match
           → Layer 2: Fuzzy string matching (Levenshtein)
           → Layer 3: Semantic embedding similarity
           → Layer 4: Contextual scoring (shared relationships)
           → Layer 5: LLM fallback (optional, batched, async)
           → Decision: merge, create new, or tentative
```

### Layer 1: Rule-Based Matching

**Speed**: <1ms per candidate set  
**Precision**: 100% (no false positives)  
**Coverage**: ~40-50% of mentions

```python
def rule_based_match(
    mention: str,
    mention_type: str,
    candidates: list[Entity]
) -> Entity | None:
    """
    Fast exact matching with case/whitespace normalization.
    """
    normalized = normalize_mention(mention)
    
    for entity in candidates:
        # Exact match on canonical name
        if normalize_mention(entity.name) == normalized:
            return entity
        
        # Exact match on any alias
        for alias in entity.aliases:
            if normalize_mention(alias) == normalized:
                return entity
    
    return None

def normalize_mention(text: str) -> str:
    """Normalization preserving semantic identity."""
    text = text.strip().lower()
    text = re.sub(r'\s+', ' ', text)  # Collapse whitespace
    text = re.sub(r'[^\w\s]', '', text)  # Remove punctuation
    return text
```

### Layer 2: Fuzzy String Matching

**Speed**: ~1-5ms for 100 candidates  
**Precision**: ~85% (with tuned threshold)  
**Coverage**: +20-25% of mentions

```python
from rapidfuzz import fuzz

def fuzzy_match(
    mention: str,
    candidates: list[Entity],
    threshold: float = 0.85
) -> Entity | None:
    """
    Fuzzy string matching using Levenshtein distance.
    """
    best_entity = None
    best_score = 0.0
    
    for entity in candidates:
        # Check canonical name
        score = fuzz.ratio(mention.lower(), entity.name.lower()) / 100.0
        if score > best_score:
            best_score = score
            best_entity = entity
        
        # Check aliases
        for alias in entity.aliases:
            score = fuzz.ratio(mention.lower(), alias.lower()) / 100.0
            if score > best_score:
                best_score = score
                best_entity = entity
    
    if best_score >= threshold:
        return best_entity
    
    return None
```

**Threshold tuning**:
- PERSON: 0.85 (stricter - "John Smith" vs "Jane Smith" are different)
- ORG: 0.80 (looser - "Acme Corp" vs "Acme Corporation")
- LOCATION: 0.90 (stricter - "Paris, France" vs "Paris, Texas")
- CONCEPT: 0.75 (looser - "machine learning" vs "ML")

### Layer 3: Semantic Embedding Similarity

**Speed**: ~10-30ms for 100 candidates (with FAISS index)  
**Precision**: ~75% (embedding models can conflate similar concepts)  
**Coverage**: +15-20% of mentions

```python
import numpy as np

def semantic_match(
    mention: str,
    mention_embedding: np.ndarray,
    candidates: list[Entity],
    threshold: float = 0.80
) -> Entity | None:
    """
    Semantic similarity using cosine distance on embeddings.
    """
    best_entity = None
    best_similarity = 0.0
    
    for entity in candidates:
        if entity.name_embedding is None:
            continue
        
        # Cosine similarity
        entity_emb = unpack_embedding(entity.name_embedding)
        similarity = np.dot(mention_embedding, entity_emb) / (
            np.linalg.norm(mention_embedding) * np.linalg.norm(entity_emb)
        )
        
        if similarity > best_similarity:
            best_similarity = similarity
            best_entity = entity
    
    if best_similarity >= threshold:
        return best_entity
    
    return None
```

**Optimization**: For large entity sets (>1000), use FAISS approximate nearest neighbor search instead of brute-force.

```python
# Optional FAISS index for scaling to 10K+ entities
import faiss

class EntityIndex:
    def __init__(self, embedding_dim: int = 384):
        self.index = faiss.IndexFlatIP(embedding_dim)  # Inner product (cosine)
        self.entity_ids: list[str] = []
    
    def add(self, entity_id: str, embedding: np.ndarray):
        # Normalize for cosine similarity
        embedding = embedding / np.linalg.norm(embedding)
        self.index.add(embedding.reshape(1, -1))
        self.entity_ids.append(entity_id)
    
    def search(self, query_embedding: np.ndarray, k: int = 10) -> list[tuple[str, float]]:
        query_embedding = query_embedding / np.linalg.norm(query_embedding)
        scores, indices = self.index.search(query_embedding.reshape(1, -1), k)
        return [(self.entity_ids[i], scores[0][idx]) for idx, i in enumerate(indices[0])]
```

### Layer 4: Contextual Scoring

**Speed**: ~5-10ms (requires DB queries)  
**Precision**: ~90% (high signal)  
**Coverage**: +5-10% of mentions

```python
def contextual_match(
    mention: str,
    mention_context: dict,  # {event_id, nearby_entities, session_key}
    candidates: list[Entity],
    threshold: float = 0.70
) -> Entity | None:
    """
    Score candidates by shared context (co-occurring entities, session).
    """
    scores = {}
    
    for entity in candidates:
        score = 0.0
        
        # Boost if mentioned in same session
        if mention_context.get("session_key") in entity.metadata.get("sessions", []):
            score += 0.3
        
        # Boost if shares relationships with nearby entities
        nearby_entity_ids = mention_context.get("nearby_entities", [])
        for nearby_id in nearby_entity_ids:
            if has_edge(entity.id, nearby_id):
                score += 0.2
        
        # Boost if mentioned in recent events
        days_since_last_seen = (datetime.now() - entity.last_seen).days
        if days_since_last_seen < 7:
            score += 0.2
        
        scores[entity.id] = score
    
    best_entity = max(candidates, key=lambda e: scores.get(e.id, 0.0))
    if scores.get(best_entity.id, 0.0) >= threshold:
        return best_entity
    
    return None
```

### Layer 5: LLM Fallback (Optional)

**Speed**: ~200-2000ms (batched, async)  
**Precision**: ~95% (best, but expensive)  
**Coverage**: Remaining ~5-10% of hard cases

```python
async def llm_fallback_match(
    mention: str,
    mention_context: str,
    candidates: list[Entity],
    llm_client: LLM
) -> Entity | None:
    """
    LLM-based disambiguation for hard cases.
    Batched and async to avoid blocking.
    """
    if not candidates:
        return None
    
    prompt = f"""Given the mention "{mention}" in context:
    {mention_context}
    
    Which entity does this refer to?
    
    Candidates:
    {format_candidates(candidates)}
    
    Respond with ONLY the candidate number (1-{len(candidates)}) or "NEW" if none match.
    """
    
    response = await llm_client.complete(prompt, model="gpt-5-nano")
    
    if response.strip().upper() == "NEW":
        return None
    
    try:
        idx = int(response.strip()) - 1
        if 0 <= idx < len(candidates):
            return candidates[idx]
    except ValueError:
        pass
    
    return None
```

**Usage policy**:
- Only enabled if `extraction.api_fallback = true`
- Only used for mentions with 2+ viable candidates after Layer 4
- Batched every 60 seconds (not per-mention)
- Falls back to "create new entity" if LLM fails

### Full Resolution Flow

```python
@dataclass
class ResolutionResult:
    entity: Entity | None
    confidence: float
    method: str  # "rule", "fuzzy", "semantic", "contextual", "llm", "new"

async def resolve_entity(
    mention: str,
    mention_type: str,
    mention_embedding: np.ndarray,
    context: dict,
    config: ExtractionConfig,
    store: MemoryStore
) -> ResolutionResult:
    """
    Progressive entity resolution through 5 layers.
    """
    # Step 1: Candidate filtering (cheap, fast)
    candidates = get_candidate_entities(
        entity_type=mention_type,
        max_candidates=100,
        filters={
            "last_seen_after": datetime.now() - timedelta(days=90),
            "event_count_min": 2  # Skip one-off entities
        }
    )
    
    if not candidates:
        return ResolutionResult(None, 1.0, "new")
    
    # Step 2: Layer 1 - Rule-based
    entity = rule_based_match(mention, mention_type, candidates)
    if entity:
        return ResolutionResult(entity, 1.0, "rule")
    
    # Step 3: Layer 2 - Fuzzy
    entity = fuzzy_match(mention, candidates, threshold=get_threshold(mention_type))
    if entity:
        return ResolutionResult(entity, 0.85, "fuzzy")
    
    # Step 4: Layer 3 - Semantic
    entity = semantic_match(mention, mention_embedding, candidates, threshold=0.80)
    if entity:
        return ResolutionResult(entity, 0.75, "semantic")
    
    # Step 5: Layer 4 - Contextual
    entity = contextual_match(mention, context, candidates, threshold=0.70)
    if entity:
        return ResolutionResult(entity, 0.80, "contextual")
    
    # Step 6: Layer 5 - LLM fallback (optional, async)
    if config.api_fallback and len(candidates) <= 5:
        entity = await llm_fallback_match(mention, context, candidates, store.llm_client)
        if entity:
            return ResolutionResult(entity, 0.95, "llm")
    
    # Step 7: Create new entity
    return ResolutionResult(None, 1.0, "new")
```

### Performance Optimizations

#### 1. Candidate Filtering

Don't check all entities; pre-filter by:
- Entity type (PERSON mentions only check PERSON entities)
- Recency (entities mentioned in last 90 days)
- Frequency (entities mentioned 2+ times)
- First letter (for large sets, use prefix index)

```python
def get_candidate_entities(
    entity_type: str,
    max_candidates: int = 100,
    filters: dict = None
) -> list[Entity]:
    """
    Fetch candidate entities with smart filtering.
    """
    query = """
        SELECT * FROM entities
        WHERE entity_type = ?
        AND last_seen > ?
        AND event_count >= ?
        ORDER BY event_count DESC
        LIMIT ?
    """
    # Returns top N most-mentioned entities of the right type
```

#### 2. Caching

Cache resolution results for the duration of an extraction batch:
```python
@dataclass
class ResolutionCache:
    cache: dict[str, Entity | None] = field(default_factory=dict)
    
    def get(self, mention: str, mention_type: str) -> Entity | None:
        key = f"{mention_type}:{normalize_mention(mention)}"
        return self.cache.get(key)
    
    def set(self, mention: str, mention_type: str, entity: Entity | None):
        key = f"{mention_type}:{normalize_mention(mention)}"
        self.cache[key] = entity
```

#### 3. Tentative Merges

For low-confidence matches (0.70-0.85), create "tentative" merge records instead of immediate merges. After 3+ confirmations (same mention resolves to same entity), promote to permanent.

```python
@dataclass
class TentativeMerge:
    mention: str
    entity_id: str
    confidence: float
    confirmation_count: int
    created_at: datetime
```

### Configuration Schema

```python
class EntityResolutionConfig(BaseModel):
    """Entity resolution algorithm configuration."""
    
    # Candidate filtering
    max_candidates: int = 100
    candidate_recency_days: int = 90
    candidate_min_mentions: int = 2
    
    # Layer thresholds
    fuzzy_threshold_person: float = 0.85
    fuzzy_threshold_org: float = 0.80
    fuzzy_threshold_location: float = 0.90
    fuzzy_threshold_concept: float = 0.75
    semantic_threshold: float = 0.80
    contextual_threshold: float = 0.70
    
    # Tentative merges
    tentative_threshold: float = 0.70
    tentative_confirmation_count: int = 3
    
    # LLM fallback
    llm_fallback_enabled: bool = False
    llm_fallback_max_candidates: int = 5
    
    # Performance
    use_faiss_index: bool = False  # Enable for 10K+ entities
    faiss_neighbors: int = 10
```

Example config:
```json
{
  "memory": {
    "extraction": {
      "entity_resolution": {
        "fuzzy_threshold_person": 0.85,
        "semantic_threshold": 0.80,
        "llm_fallback_enabled": false
      }
    }
  }
}
```

### Monitoring and Observability

Track resolution metrics:
```python
@dataclass
class ResolutionMetrics:
    total_resolutions: int
    method_counts: dict[str, int]  # {"rule": 450, "fuzzy": 230, ...}
    avg_latency_ms: dict[str, float]  # {"rule": 0.8, "fuzzy": 3.2, ...}
    confidence_distribution: dict[str, int]  # {"high": 600, "medium": 100, ...}
    tentative_merges: int
    false_positive_reports: int  # User-reported incorrect merges
```

CLI command to inspect:
```bash
$ nanobot memory resolution-stats
Entity Resolution Statistics (last 7 days)
─────────────────────────────────────────
Total resolutions:    1,234
  - Rule-based:       45% (avg 0.8ms)
  - Fuzzy:            28% (avg 3.2ms)
  - Semantic:         18% (avg 12ms)
  - Contextual:       7%  (avg 8ms)
  - LLM fallback:     0%  (disabled)
  - New entities:     2%

Tentative merges:     23 (awaiting confirmation)
False positives:      2 (0.16%)
```

### Testing Strategy

```python
# tests/memory/test_entity_resolution.py

def test_rule_based_exact_match():
    """Layer 1: Exact match on canonical name."""
    entity = Entity(id="1", name="John Smith", entity_type="person", aliases=[])
    result = rule_based_match("john smith", "person", [entity])
    assert result == entity

def test_fuzzy_match_nickname():
    """Layer 2: Fuzzy match for nickname."""
    entity = Entity(id="1", name="Elizabeth", entity_type="person", aliases=["Liz"])
    result = fuzzy_match("Lizzy", [entity], threshold=0.80)
    assert result == entity

def test_semantic_match_synonym():
    """Layer 3: Semantic match for synonym."""
    entity = Entity(
        id="1", 
        name="machine learning", 
        entity_type="concept",
        name_embedding=embed("machine learning")
    )
    result = semantic_match("ML", embed("ML"), [entity], threshold=0.75)
    assert result == entity

def test_no_false_positive_merge():
    """Precision: Don't merge different people with similar names."""
    john_smith = Entity(id="1", name="John Smith", entity_type="person", aliases=[])
    jane_smith = Entity(id="2", name="Jane Smith", entity_type="person", aliases=[])
    result = fuzzy_match("John Smith", [jane_smith], threshold=0.85)
    assert result is None  # Should NOT match Jane
```

### Performance Targets

| Percentile | Latency Target | Notes |
|------------|---------------|-------|
| p50 | <1ms | Rule-based fast path |
| p90 | <5ms | Fuzzy + semantic |
| p95 | <10ms | Contextual scoring |
| p99 | <50ms | Rare LLM fallback |

For 100 entity candidates:
- Layer 1 (rule): ~0.5ms
- Layer 2 (fuzzy): ~2-3ms
- Layer 3 (semantic): ~10ms (brute force) or ~2ms (FAISS)
- Layer 4 (contextual): ~5ms (requires DB queries)
- Layer 5 (LLM): ~200-2000ms (batched, async)

### Resource Requirements

**Memory**:
- Entity cache: ~10KB per 100 entities
- Embedding cache: ~1.5KB per entity (384 dims × 4 bytes)
- FAISS index (optional): ~2MB per 10K entities

**Disk**:
- SQLite indexes on entities.name, entities.entity_type, entities.last_seen

**CPU**:
- Minimal (string operations + vector dot products)
- FAISS index build: ~1-2 seconds for 10K entities (one-time)

---


## References

- [babyagi3 memory system](https://github.com/yoheinakajima/babyagi3/tree/main/memory) - Inspiration for 3-layer architecture
- [BAAI/bge-small-en-v1.5](https://huggingface.co/BAAI/bge-small-en-v1.5) - Local embedding model (English)
- [BAAI/bge-m3](https://huggingface.co/BAAI/bge-m3) - Future multilingual embedding model
- [FastEmbed](https://github.com/qdrant/fastembed) - ONNX-based embedding runtime
- [GLiNER2](https://github.com/fastino-ai/GLiNER2) - Unified extraction model
- [GLiNER2 Paper](https://arxiv.org/pdf/2507.18546) - Technical details
- [spaCy en_core_web_sm](https://spacy.io/models/en#en_core_web_sm) - Fallback NER model
- [SQLite WAL Mode](https://www.sqlite.org/wal.html) - Write-Ahead Logging documentation

---

**Last Updated**: 2026-02-10
**Status**: Proposal REVISED - Ready for Implementation
**Author**: nanobot-turbo development team
**Revisions**: 
- v1: Original proposal with spaCy
- v2: Revised with GLiNER2, WAL mode, lazy loading, privacy controls, TUI downloads

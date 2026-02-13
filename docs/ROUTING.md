# Smart Routing System

**nanobot-turbo** features an intelligent routing system that automatically selects the most appropriate and cost-effective LLM model based on message complexity.

## Overview

The smart routing system analyzes incoming messages and routes them to one of four capability tiers, each with a different model and cost profile.

### Why Smart Routing?

- 💰 **Cost Savings**: Up to 96% reduction in API costs
- ⚡ **Performance**: Fast client-side classification (~1ms) for most queries
- 🧠 **Intelligence**: Automatically handles simple vs complex queries differently
- 📊 **Self-Improving**: Learns from decisions and optimizes over time

### Cost Comparison

| Usage Pattern | Without Routing | With Routing | Savings |
|--------------|----------------|--------------|---------|
| Typical (45% simple, 35% medium, 15% complex, 5% reasoning) | $75.00/M | $3.17/M | **96%** |
| Mostly Simple (80% simple) | $75.00/M | $1.34/M | **98%** |
| Balanced (25% each) | $75.00/M | $25.15/M | **66%** |

## Architecture

### Two-Layer Classification

```
┌─────────────────────────────────────────────────────────────┐
│                    INCOMING MESSAGE                         │
└──────────────────────┬──────────────────────────────────────┘
                       ↓
┌─────────────────────────────────────────────────────────────┐
│  LAYER 1: Client-Side Classification (~1ms)                │
│  • 14-dimension heuristic analysis                         │
│  • Pattern matching with learned patterns                  │
│  • Sigmoid confidence calibration                          │
│                                                            │
│  IF confidence ≥ threshold:                                │
│     → Return result (skip Layer 2)                         │
└──────────────────────┬──────────────────────────────────────┘
                       ↓ (if confidence < threshold)
┌─────────────────────────────────────────────────────────────┐
│  LAYER 2: LLM-Assisted Classification (~200ms)             │
│  • GPT-4o-mini analyzes the query                          │
│  • JSON response with tier, confidence, reasoning          │
│  • More accurate for edge cases                            │
└──────────────────────┬──────────────────────────────────────┘
                       ↓
┌─────────────────────────────────────────────────────────────┐
│  STICKY ROUTING                                            │
│  • Maintains tier across conversation                      │
│  • Allows downgrade when explicitly simple                 │
│  • Context window: 5 messages                              │
└──────────────────────┬──────────────────────────────────────┘
                       ↓
┌─────────────────────────────────────────────────────────────┐
│              EXECUTE WITH SELECTED MODEL                    │
└─────────────────────────────────────────────────────────────┘
```

### The 14 Dimensions

The client-side classifier evaluates messages across 14 dimensions:

| Dimension | Weight | Description | Examples |
|-----------|--------|-------------|----------|
| reasoning_markers | 0.18 | Formal reasoning indicators | "prove", "theorem", "step by step" |
| code_presence | 0.15 | Code-related content | "function", "class", "```" |
| simple_indicators | 0.12 | Simple question markers | "what is", "define", "how to" |
| multi_step_patterns | 0.12 | Multi-step task indicators | "first", "then", "step 1" |
| technical_terms | 0.10 | Technical vocabulary | "algorithm", "distributed", "kubernetes" |
| token_count | 0.08 | Message length | Short (<50) vs Long (>500) |
| creative_markers | 0.05 | Creative content | "story", "poem", "brainstorm" |
| question_complexity | 0.05 | Question structure | Multiple question marks |
| constraint_count | 0.04 | Constraints/limits | "at most", "O(n)", "maximum" |
| imperative_verbs | 0.03 | Action verbs | "build", "create", "implement" |
| output_format | 0.03 | Format specifications | "json", "yaml", "markdown" |
| domain_specificity | 0.02 | Specialized domains | "quantum", "blockchain", "genomics" |
| reference_complexity | 0.02 | Context references | "the docs", "above", "previous" |
| negation_complexity | 0.01 | Negative constraints | "don't", "avoid", "without" |

### Confidence Calculation

```python
# Weighted sum of all dimensions
weighted_sum = Σ(dimension_score × weight)

# Sigmoid calibration for confidence
confidence = 1 / (1 + e^(-weighted_sum × 2))
```

### Tier Selection

Based on confidence score:

| Confidence | Tier | Typical Use Case |
|------------|------|------------------|
| ≥ 0.97 | REASONING | Proofs, derivations, step-by-step analysis |
| ≥ 0.85 | COMPLEX | Multi-step debugging, architecture, complex algorithms |
| ≥ 0.50 | MEDIUM | General coding, explanations, file operations |
| < 0.50 | SIMPLE | Quick facts, definitions, translations |

## Configuration

### Basic Configuration

Add to `~/.nanobot/config.json`:

```json
{
  "routing": {
    "enabled": true,
    "tiers": {
      "simple": {
        "model": "gpt-4o-mini",
        "cost_per_mtok": 0.60
      },
      "medium": {
        "model": "anthropic/claude-sonnet-4",
        "cost_per_mtok": 15.0
      },
      "complex": {
        "model": "anthropic/claude-opus-4",
        "cost_per_mtok": 75.0
      },
      "reasoning": {
        "model": "o3",
        "cost_per_mtok": 10.0
      }
    }
  }
}
```

### Advanced Configuration

```json
{
  "routing": {
    "enabled": true,
    "tiers": {
      "simple": {
        "model": "gpt-4o-mini",
        "cost_per_mtok": 0.60
      },
      "medium": {
        "model": "anthropic/claude-sonnet-4",
        "cost_per_mtok": 15.0
      },
      "complex": {
        "model": "anthropic/claude-opus-4",
        "cost_per_mtok": 75.0
      },
      "reasoning": {
        "model": "o3",
        "cost_per_mtok": 10.0
      }
    },
    "client_classifier": {
      "min_confidence": 0.85
    },
    "llm_classifier": {
      "model": "gpt-4o-mini",
      "timeout_ms": 500
    },
    "sticky": {
      "context_window": 5,
      "downgrade_confidence": 0.9
    },
    "auto_calibration": {
      "enabled": true,
      "interval": "24h",
      "min_classifications": 50,
      "max_patterns": 100,
      "backup_before_calibration": true
    }
  }
}
```

### Configuration Options

#### Tiers

Each tier defines a model to use and its cost for analytics:

- `model`: Model identifier (passed to provider)
- `cost_per_mtok`: Cost per million tokens (for analytics only)

#### Client Classifier

- `min_confidence`: Threshold for accepting client-side classification (0.0-1.0)
  - Lower = more Layer 2 calls (more accurate, slower, more expensive)
  - Higher = more Layer 1 calls (faster, cheaper, less accurate)
  - Default: 0.85

#### LLM Classifier

- `model`: Model to use for Layer 2 classification
- `timeout_ms`: Timeout for LLM calls (default: 500ms)

#### Sticky Routing

- `context_window`: Number of messages to look back (default: 5)
- `downgrade_confidence`: Confidence threshold for allowing downgrade (default: 0.9)

#### Auto-Calibration

- `enabled`: Enable automatic calibration (default: true)
- `interval`: Calibration interval (e.g., "24h", "100_classifications", "7d")
- `min_classifications`: Minimum classifications before calibrating (default: 50)
- `max_patterns`: Maximum patterns to keep (default: 100)
- `backup_before_calibration`: Create backup before calibrating (default: true)

## CLI Commands

### Status

```bash
nanobot routing status
```

Shows:
- Routing configuration
- All tiers with models and costs
- Client/LLM classifier settings
- Sticky routing configuration
- Calibration status

### Test Classification

```bash
# Basic test
nanobot routing test "What is Python?"

# Verbose output with all 14 dimensions
nanobot routing test "Write a function to parse JSON" --verbose
```

Shows:
- Selected tier
- Confidence score
- Classification layer (client/llm)
- Estimated tokens
- Tool requirements
- All dimension scores (with --verbose)

### View Patterns

```bash
# Show all patterns
nanobot routing patterns

# Show top 10
nanobot routing patterns --limit 10

# Filter by tier
nanobot routing patterns --tier complex
```

Shows:
- Pattern regex
- Tier
- Confidence
- Success rate
- Usage count

### Analytics

```bash
nanobot routing analytics
```

Shows:
- Total classifications
- Client vs LLM split
- Tier distribution
- Blended cost
- Estimated savings

### Calibration

```bash
# Show what would be done
nanobot routing calibrate --dry-run

# Actually run calibration
nanobot routing calibrate
```

## How Sticky Routing Works

### Scenario 1: Maintaining Complex Tier

```
User: "Debug this distributed system race condition"
→ Tier: COMPLEX (confidence: 0.88)

User: "Thanks for that"
→ Tier: COMPLEX (sticky maintained)

User: "Now explain what a race condition is"
→ Tier: MEDIUM (downgrade allowed - explicit shift to explanation)
```

### Scenario 2: Downgrade Detection

```
User: "Refactor this large codebase" 
→ Tier: COMPLEX (confidence: 0.90)

User: "Quick question - what's 2+2?"
→ Tier: SIMPLE (downgrade allowed - short, explicit simple marker)
```

### Downgrade Conditions

A downgrade is allowed when:
1. Message is very short (< 20 words)
2. Has explicit simple markers ("just a quick question", "by the way")
3. High simple_indicators score (> 0.7)
4. Low technical_terms score (< 0.2)

## Auto-Calibration

### How It Works

1. **Recording**: Each classification is recorded with:
   - Client-side tier and confidence
   - LLM tier and confidence (if Layer 2 was used)
   - Final selected tier

2. **Analysis**: Periodically analyzes:
   - Match rate between Layer 1 and Layer 2
   - Which patterns are successful
   - Which patterns fail

3. **Pattern Generation**: Creates new patterns from:
   - Mismatches where LLM was correct
   - Common words/phrases in specific tiers

4. **Eviction**: Removes patterns with:
   - Low success rate (< 30%)
   - Old age (> 7 days) AND low success

5. **Schedule**:
   - Runs every 24 hours OR
   - After 100 new classifications
   - Only if minimum 50 classifications exist

### Calibration Output

```
✓ Calibration complete

Classifications analyzed: 247
Patterns added: 3
Patterns removed: 2
Total patterns: 45
```

## Testing Classification

### Using Python

```python
from nanobot.agent.router import classify_content

# Test classification
decision, scores = classify_content("Write a Python function to sort a list")

print(f"Tier: {decision.tier.value}")
print(f"Confidence: {decision.confidence:.2f}")
print(f"Layer: {decision.layer}")
print(f"Estimated tokens: {decision.estimated_tokens}")
print(f"Needs tools: {decision.needs_tools}")

# View all scores
for dimension, score in scores.to_dict().items():
    print(f"{dimension}: {score:.2f}")
```

### Using CLI

```bash
nanobot routing test "Your message here" --verbose
```

## Customization

### Adding Custom Patterns

Edit `~/.nanobot/workspace/memory/ROUTING_PATTERNS.json`:

```json
{
  "patterns": [
    {
      "regex": "\\b(my custom term)\\b",
      "tier": "complex",
      "confidence": 0.9,
      "examples": ["Example with my custom term"],
      "added_at": "2026-02-09T10:00:00",
      "success_rate": 1.0,
      "usage_count": 0
    }
  ]
}
```

### Adjusting Dimension Weights

Currently, weights are hardcoded in `nanobot/agent/router/classifier.py`:

```python
DEFAULT_WEIGHTS = {
    "reasoning_markers": 0.18,
    "code_presence": 0.15,
    # ... etc
}
```

To customize, modify the weights and restart nanobot.

## Troubleshooting

### Routing Always Uses Same Tier

**Problem**: All messages route to COMPLEX tier

**Solutions**:
1. Check `min_confidence` setting - may be too high
2. Test with `nanobot routing test` to see actual confidence
3. Review patterns in `nanobot routing patterns`

### Too Many LLM Calls

**Problem**: Slow responses due to Layer 2 fallback

**Solutions**:
1. Lower `min_confidence` to accept more client-side classifications
2. Add custom patterns for your common queries
3. Wait for auto-calibration to learn patterns

### Not Saving Costs

**Problem**: Analytics show low savings

**Check**:
1. Are you actually using simple queries?
2. Verify tier distribution in `nanobot routing analytics`
3. Check if `cost_per_mtok` values are correct for your models

### Calibration Not Running

**Check**:
1. `auto_calibration.enabled` is true
2. At least 50 classifications recorded
3. Check `nanobot routing status` for last calibration time

## Best Practices

1. **Start with defaults**: Default settings work well for most use cases
2. **Monitor analytics**: Check `nanobot routing analytics` weekly
3. **Test edge cases**: Use `routing test` for uncertain queries
4. **Let it learn**: Allow auto-calibration to run for a few days
5. **Review patterns**: Check learned patterns periodically
6. **Update costs**: Keep `cost_per_mtok` updated for accurate analytics

## API Reference

### RoutingDecision

```python
@dataclass
class RoutingDecision:
    tier: RoutingTier          # Selected tier
    model: str                 # Model to use
    confidence: float          # 0.0-1.0
    layer: str                 # "client" or "llm"
    reasoning: str             # Explanation
    estimated_tokens: int      # Token estimate
    needs_tools: bool          # Whether tools likely needed
    metadata: dict             # Additional data
```

### ClassificationScores

```python
@dataclass
class ClassificationScores:
    reasoning_markers: float = 0.0
    code_presence: float = 0.0
    simple_indicators: float = 0.0
    # ... (all 14 dimensions)
```

### classify_content()

```python
def classify_content(
    content: str,
    patterns_file: Optional[Path] = None,
    min_confidence: float = 0.85,
) -> Tuple[RoutingDecision, ClassificationScores]:
    """Classify content and return decision with scores."""
```

## Contributing

To improve the routing system:

1. **Test on your data**: Try it with your actual use cases
2. **Report edge cases**: If classification seems wrong, report it
3. **Share patterns**: Good custom patterns can benefit others
4. **Suggest dimensions**: Ideas for new classification dimensions welcome

## License

MIT - See main LICENSE file

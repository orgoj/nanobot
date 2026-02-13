# Router Calibration System Analysis

## Current State Analysis

### What's Working Well ✅

1. **Integration Complete**
   - CalibrationManager initialized in routing_stage.py
   - Records classifications after each routing decision
   - Auto-triggers based on time/count thresholds
   - CLI command available: `nanobot routing calibrate`

2. **Data Collection**
   - Records Layer 1 vs Layer 2 disagreements
   - Stores up to 1000 recent classifications
   - Tracks timestamps for time-based calibration

3. **Pattern Generation**
   - Generates patterns from mismatched classifications
   - Groups by tier, extracts common words
   - Creates regex patterns with 0.8 confidence

4. **Safety Features**
   - Backs up patterns before calibration
   - Max pattern limit (100) to prevent bloat
   - Eviction of low-success patterns (>30% success rate)

---

## Issues & Misalignments Found 🔍

### 1. **Pattern Generation is Too Simple** ⚠️

**Current Implementation:**
```python
def _extract_patterns(self, contents: list[str]) -> list[str]:
    # Just finds common words across mismatches
    words = set(re.findall(r'\b\w+\b', content.lower()))
    common = set.intersection(*words_by_content)
    patterns = [rf"\b{re.escape(word)}\b" for word in meaningful]
```

**Problem:**
- Only extracts single words
- Ignores the context we worked hard to build (action_type, negations)
- Can't capture phrases like "git push" or "explain how"
- Generated patterns are weak (just word boundaries)

**What It Should Do:**
- Extract 2-4 word phrases (n-grams)
- Consider action type context
- Weight patterns by how often they appear
- Handle negations ("don't write" vs "write")

---

### 2. **Missing Action Type Context** ⚠️

**Current Pattern Recording:**
```python
def record_classification(self, record: dict):
    record = {
        "content_preview": ...,
        "client_tier": ...,
        "llm_tier": ...,
        "final_tier": ...,
    }
```

**Missing:**
- `action_type` (write/explain/analyze)
- `has_negations`
- `question_type`
- `code_presence`

**Impact:**
- Calibration doesn't learn that "explain" + "code" → MEDIUM
- Can't distinguish "write code" vs "explain code"
- Missing the nuanced context we built

---

### 3. **No Tier-Specific Pattern Learning** ⚠️

**Current:** All mismatches grouped together
**Should Be:** Tier-specific pattern generation

Example:
```
Mismatches where LLM said CODING but client said MEDIUM:
- "explain how async works"
- "don't write code, just describe"
- "what does this function do"

Pattern to learn: "explain|describe|what does" + code_context → MEDIUM
```

---

### 4. **Calibration Doesn't Update Thresholds** ⚠️

**Current:** Only generates patterns
**Missing:** Threshold adjustment based on accuracy

Example:
```
If 90% of CODING classifications are accurate at confidence 0.85,
but only 60% at confidence 0.80,
→ Should raise CODING threshold to 0.85
```

---

### 5. **No Feedback on Generated Patterns** ⚠️

**Current:**
1. Generate pattern from mismatches
2. Add to patterns with 0.8 confidence
3. Hope it works

**Missing:**
- Track success rate of auto-generated patterns
- Adjust confidence based on real-world performance
- Remove patterns that don't help

---

### 6. **Pattern Eviction Logic Too Simple** ⚠️

**Current:**
```python
def _evict_patterns(self, patterns):
    if p.success_rate >= 0.3:  # Keep if 30%+ success
        keep
```

**Problems:**
- Doesn't consider usage count (pattern used 1000x with 50% success > pattern used 10x with 100% success)
- Doesn't consider age (old patterns might be obsolete)
- No tier-specific eviction (keep more CODING patterns if needed)

---

## Proposed Improvements 🚀

### 1. **Enhanced Pattern Generation**

```python
def _extract_enhanced_patterns(self, contents: list[str], tier: str, 
                               action_types: list[str]) -> list[RoutingPattern]:
    """Extract patterns with context awareness."""
    
    # Extract n-grams (2-4 words)
    ngrams = self._extract_ngrams(contents, n=2)  # "git push", "explain how"
    ngrams += self._extract_ngrams(contents, n=3)  # "explain how code"
    
    # Weight by frequency
    from collections import Counter
    weighted = Counter(ngrams)
    
    # Consider action type context
    common_actions = Counter(action_types)
    dominant_action = common_actions.most_common(1)[0][0]
    
    patterns = []
    for ngram, count in weighted.most_common(5):
        # Create context-aware pattern
        if dominant_action == "explain":
            regex = rf"\b{re.escape(ngram)}.*\b(explain|describe|how|what)\b"
        else:
            regex = rf"\b{re.escape(ngram)}\b"
        
        pattern = RoutingPattern(
            regex=regex,
            tier=RoutingTier(tier),
            confidence=0.7,  # Start lower, will adjust
            examples=contents[:3],
            added_at=datetime.now().isoformat(),
            source="auto_calibration",
            action_context=dominant_action,  # NEW
        )
        patterns.append(pattern)
    
    return patterns
```

---

### 2. **Record Full Context**

```python
def record_classification(self, record: dict) -> None:
    """Record classification with full context."""
    enhanced_record = {
        # Existing fields
        "content_preview": record.get("content_preview", ""),
        "client_tier": record.get("client_tier"),
        "client_confidence": record.get("client_confidence"),
        "llm_tier": record.get("llm_tier"),
        "llm_confidence": record.get("llm_confidence"),
        "final_tier": record.get("final_tier"),
        "timestamp": datetime.now().isoformat(),
        
        # NEW: Context fields
        "action_type": record.get("action_type", "general"),
        "has_negations": record.get("has_negations", False),
        "question_type": record.get("question_type"),
        "code_presence": record.get("code_presence", 0.0),
        "simple_indicators": record.get("simple_indicators", 0.0),
        "technical_terms": record.get("technical_terms", 0.0),
        
        # NEW: Decision info
        "layer_used": record.get("layer", "client"),
        "was_calibration": record.get("was_calibration", False),
    }
    
    self._classifications.append(enhanced_record)
```

---

### 3. **Adaptive Threshold Calibration**

```python
def _calibrate_thresholds(self) -> dict:
    """Adjust tier thresholds based on accuracy data."""
    adjustments = {}
    
    for tier in ["simple", "medium", "complex", "coding", "reasoning"]:
        # Get classifications for this tier
        tier_records = [
            r for r in self._classifications 
            if r.get("client_tier") == tier and r.get("llm_tier")
        ]
        
        if len(tier_records) < 20:
            continue  # Not enough data
        
        # Group by client confidence buckets
        buckets = defaultdict(list)
        for r in tier_records:
            conf = r.get("client_confidence", 0)
            bucket = round(conf * 10) / 10  # 0.1, 0.2, ..., 0.9
            buckets[bucket].append(r)
        
        # Find optimal threshold (highest accuracy)
        best_threshold = 0.5
        best_accuracy = 0
        
        for threshold in [0.5, 0.6, 0.7, 0.8, 0.9, 0.95]:
            # Get records above threshold
            above = [r for bucket, records in buckets.items() 
                    if bucket >= threshold for r in records]
            
            if len(above) < 10:
                continue
            
            # Calculate accuracy
            matches = sum(1 for r in above if r["client_tier"] == r["llm_tier"])
            accuracy = matches / len(above)
            
            if accuracy > best_accuracy:
                best_accuracy = accuracy
                best_threshold = threshold
        
        adjustments[tier] = {
            "old_threshold": DEFAULT_THRESHOLDS[tier],
            "new_threshold": best_threshold,
            "accuracy_improvement": best_accuracy,
            "sample_size": len(tier_records),
        }
    
    return adjustments
```

---

### 4. **Pattern Performance Tracking**

```python
class RoutingPattern:
    """Enhanced with performance tracking."""
    
    regex: str
    tier: RoutingTier
    confidence: float
    examples: list[str]
    added_at: str
    
    # NEW: Performance metrics
    times_used: int = 0
    times_matched: int = 0
    times_correct: int = 0  # When matched, was it right tier?
    last_used: Optional[str] = None
    
    @property
    def success_rate(self) -> float:
        if self.times_matched == 0:
            return 0.0
        return self.times_correct / self.times_matched
    
    @property
    def is_effective(self) -> bool:
        """Pattern is effective if used often and has good success rate."""
        if self.times_used < 5:
            return True  # Too new to judge
        return self.success_rate >= 0.4  # 40% success minimum
```

---

### 5. **Intelligent Pattern Eviction**

```python
def _evict_patterns_intelligent(self, patterns: list[RoutingPattern]) -> list[RoutingPattern]:
    """Smart pattern eviction considering multiple factors."""
    
    scored_patterns = []
    for p in patterns:
        score = 0
        
        # Factor 1: Success rate (0-50 points)
        score += p.success_rate * 50
        
        # Factor 2: Usage frequency (0-30 points)
        # Patterns used more often are more valuable
        if p.times_used > 100:
            score += 30
        elif p.times_used > 50:
            score += 20
        elif p.times_used > 10:
            score += 10
        
        # Factor 3: Recency (0-20 points)
        # Recently used patterns more valuable
        if p.last_used:
            days_since = (datetime.now() - datetime.fromisoformat(p.last_used)).days
            if days_since < 7:
                score += 20
            elif days_since < 30:
                score += 10
            elif days_since < 90:
                score += 5
        
        # Factor 4: Age bonus (auto-generated patterns get grace period)
        try:
            age_days = (datetime.now() - datetime.fromisoformat(p.added_at)).days
            if age_days < 7:
                score += 15  # Grace period for new patterns
        except:
            pass
        
        scored_patterns.append((p, score))
    
    # Sort by score, keep top patterns up to max_patterns
    scored_patterns.sort(key=lambda x: x[1], reverse=True)
    
    return [p for p, score in scored_patterns[:self.max_patterns]]
```

---

### 6. **Tier-Specific Learning**

```python
def _learn_tier_specific_patterns(self, mismatches: list[dict]) -> dict:
    """Learn patterns specific to each tier confusion type."""
    
    # Group mismatches by (client_tier, llm_tier) pairs
    confusion_pairs = defaultdict(list)
    for m in mismatches:
        key = (m.get("client_tier"), m.get("llm_tier"))
        confusion_pairs[key].append(m)
    
    learned_patterns = {}
    
    for (client_tier, llm_tier), records in confusion_pairs.items():
        if len(records) < 5:
            continue
        
        # Analyze what client missed
        contents = [r.get("content_preview", "") for r in records]
        action_types = [r.get("action_type", "general") for r in records]
        
        # Learn patterns for this specific confusion
        patterns = self._extract_enhanced_patterns(
            contents, 
            llm_tier,  # The "correct" tier
            action_types
        )
        
        learned_patterns[f"{client_tier}_vs_{llm_tier}"] = {
            "count": len(records),
            "patterns": patterns,
            "common_actions": Counter(action_types).most_common(3),
        }
    
    return learned_patterns
```

---

## Implementation Priority

### Phase 1: Critical Fixes (1-2 days)
1. ✅ Record full context (action_type, negations, etc.)
2. ✅ Enhance pattern generation (n-grams, not just words)
3. ✅ Add pattern performance tracking

### Phase 2: Smart Features (2-3 days)
4. ✅ Intelligent pattern eviction
5. ✅ Tier-specific learning
6. ✅ Adaptive thresholds

### Phase 3: Polish (1 day)
7. ✅ Calibration analytics dashboard
8. ✅ Pattern effectiveness reports
9. ✅ A/B testing framework for patterns

---

## Quick Wins (Can Implement Now)

### 1. **Fix Pattern Generation** (30 min)
Change from single words to n-grams:
```python
# Instead of:
patterns = [rf"\b{word}\b" for word in words]

# Use:
patterns = self._extract_ngrams(contents, n=2)  # 2-word phrases
```

### 2. **Record Context** (15 min)
Update `record_classification` to include action_type and negations

### 3. **Better Eviction** (30 min)
Implement the scored eviction logic

---

## Summary

**Current System:** ✅ Functional but basic
**Major Gaps:**
- Pattern generation too simple (single words)
- Missing context recording (action_type, negations)
- No threshold adaptation
- Pattern eviction not intelligent

**Impact of Improvements:**
- Better auto-generated patterns (n-grams capture phrases like "git push")
- Context-aware learning ("explain code" → MEDIUM learned properly)
- Self-optimizing thresholds
- Higher quality pattern library over time

Should I start implementing these improvements?
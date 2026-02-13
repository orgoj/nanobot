"""Auto-calibration system for improving routing decisions over time."""

import json
import re
from collections import Counter, defaultdict
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Optional

from .models import ClassificationScores, RoutingPattern, RoutingTier


class CalibrationManager:
    """
    Manages auto-calibration of routing patterns and thresholds.
    
    Runs periodically to:
    1. Analyze classification accuracy
    2. Generate new patterns from successful LLM classifications (with n-grams)
    3. Update confidence thresholds based on accuracy data
    4. Evict low-success patterns intelligently
    5. Learn tier-specific confusion patterns
    """
    
    def __init__(
        self,
        patterns_file: Path,
        analytics_file: Optional[Path] = None,
        config: Optional[dict] = None,
    ):
        self.patterns_file = patterns_file
        self.analytics_file = analytics_file or patterns_file.parent / "routing_stats.json"
        self.config = config or {}
        
        # Default configuration
        self.interval = self.config.get("interval", "24h")
        self.min_classifications = self.config.get("min_classifications", 50)
        self.max_patterns = self.config.get("max_patterns", 100)
        self.backup_before = self.config.get("backup_before_calibration", True)
        
        self._classifications: list[dict] = []
        self._last_calibration: Optional[datetime] = None
        self._load_analytics()
    
    def _load_analytics(self) -> None:
        """Load analytics data from file."""
        if self.analytics_file.exists():
            try:
                data = json.loads(self.analytics_file.read_text())
                self._classifications = data.get("classifications", [])
                last_str = data.get("last_calibration")
                if last_str:
                    self._last_calibration = datetime.fromisoformat(last_str)
            except Exception:
                self._classifications = []
                self._last_calibration = None
    
    def record_classification(self, record: dict) -> None:
        """
        Record a classification with full context for later analysis.
        
        Args:
            record: Dict with comprehensive context:
                - content_preview: str
                - client_tier: str
                - client_confidence: float
                - llm_tier: str (optional)
                - llm_confidence: float (optional)
                - final_tier: str
                - layer: str ("client" or "llm")
                
                # NEW: Context fields
                - action_type: str ("write", "explain", "analyze", etc.)
                - has_negations: bool
                - negations: list of dicts
                - question_type: str ("yes_no", "wh_question", "open")
                - code_presence: float
                - simple_indicators: float
                - technical_terms: float
                - social_interaction: float
        """
        enhanced_record = {
            # Core classification data
            "content_preview": record.get("content_preview", ""),
            "client_tier": record.get("client_tier"),
            "client_confidence": record.get("client_confidence", 0.0),
            "llm_tier": record.get("llm_tier"),
            "llm_confidence": record.get("llm_confidence", 0.0),
            "final_tier": record.get("final_tier"),
            "layer_used": record.get("layer", "client"),
            
            # NEW: Full context
            "action_type": record.get("action_type", "general"),
            "has_negations": record.get("has_negations", False),
            "negations": record.get("negations", []),
            "question_type": record.get("question_type"),
            "code_presence": record.get("code_presence", 0.0),
            "simple_indicators": record.get("simple_indicators", 0.0),
            "technical_terms": record.get("technical_terms", 0.0),
            "social_interaction": record.get("social_interaction", 0.0),
            
            # Metadata
            "timestamp": datetime.now().isoformat(),
            "was_calibration": record.get("was_calibration", False),
        }
        
        self._classifications.append(enhanced_record)
        
        # Keep only recent classifications (last 1000)
        if len(self._classifications) > 1000:
            self._classifications = self._classifications[-1000:]
    
    def should_calibrate(self) -> bool:
        """Check if calibration should run."""
        if not self._classifications:
            return False
        
        # Check time-based interval
        if self._last_calibration:
            interval_hours = self._parse_interval(self.interval)
            time_since = datetime.now() - self._last_calibration
            if time_since < timedelta(hours=interval_hours):
                # Check count-based threshold
                classifications_since = len([
                    c for c in self._classifications
                    if datetime.fromisoformat(c["timestamp"]) > self._last_calibration
                ])
                if classifications_since < self.min_classifications:
                    return False
        
        return True
    
    def calibrate(self) -> dict:
        """
        Run comprehensive calibration and return results.
        
        Returns:
            Dict with detailed calibration results
        """
        if self.backup_before and self.patterns_file.exists():
            self._backup_patterns()
        
        results = {
            "timestamp": datetime.now().isoformat(),
            "classifications_analyzed": len(self._classifications),
            "patterns_added": 0,
            "patterns_removed": 0,
            "threshold_adjustments": {},
            "tier_specific_learning": {},
        }
        
        # 1. Analyze accuracy
        accuracy_report = self._analyze_accuracy()
        results["accuracy"] = accuracy_report["accuracy"]
        results["matches"] = accuracy_report["matches"]
        results["mismatches_count"] = len(accuracy_report["mismatches"])
        
        # 2. Learn tier-specific confusion patterns
        if accuracy_report["mismatches"]:
            tier_learning = self._learn_tier_specific_patterns(accuracy_report["mismatches"])
            results["tier_specific_learning"] = tier_learning
        
        # 3. Generate new patterns from mismatches (with context awareness)
        new_patterns = self._generate_enhanced_patterns(accuracy_report["mismatches"])
        
        # 4. Load existing patterns and update performance stats
        existing_patterns = self._load_existing_patterns()
        self._update_pattern_performance(existing_patterns)
        
        # 5. Add new patterns
        for pattern in new_patterns:
            if len(existing_patterns) < self.max_patterns:
                existing_patterns.append(pattern)
                results["patterns_added"] += 1
        
        # 6. Intelligent pattern eviction
        before_count = len(existing_patterns)
        existing_patterns = self._evict_patterns_intelligent(existing_patterns)
        results["patterns_removed"] = before_count - len(existing_patterns)
        
        # 7. Adaptive threshold calibration
        threshold_adjustments = self._calibrate_thresholds()
        results["threshold_adjustments"] = threshold_adjustments
        
        # 8. Save updated patterns
        self._save_patterns(existing_patterns)
        
        # 9. Update analytics
        self._last_calibration = datetime.now()
        self._save_analytics()
        
        results["total_patterns"] = len(existing_patterns)
        results["effective_patterns"] = sum(1 for p in existing_patterns if p.is_effective)
        
        return results
    
    def _analyze_accuracy(self) -> dict:
        """Analyze classification accuracy with detailed breakdown."""
        total = len(self._classifications)
        matches = 0
        mismatches = []
        
        for record in self._classifications:
            client_tier = record.get("client_tier")
            llm_tier = record.get("llm_tier")
            
            if llm_tier and client_tier:
                if client_tier == llm_tier:
                    matches += 1
                else:
                    mismatches.append(record)
        
        accuracy = matches / total if total > 0 else 0.0
        
        # Analyze by tier
        tier_accuracy = {}
        for tier in ["simple", "medium", "complex", "coding", "reasoning"]:
            tier_records = [r for r in self._classifications if r.get("client_tier") == tier and r.get("llm_tier")]
            if tier_records:
                tier_matches = sum(1 for r in tier_records if r["client_tier"] == r["llm_tier"])
                tier_accuracy[tier] = tier_matches / len(tier_records)
        
        return {
            "total": total,
            "matches": matches,
            "accuracy": accuracy,
            "mismatches": mismatches,
            "tier_accuracy": tier_accuracy,
        }
    
    def _learn_tier_specific_patterns(self, mismatches: list[dict]) -> dict:
        """Learn patterns specific to each tier confusion type."""
        confusion_pairs = defaultdict(list)
        
        # Group mismatches by (client_tier, llm_tier) pairs
        for m in mismatches:
            key = (m.get("client_tier"), m.get("llm_tier"))
            confusion_pairs[key].append(m)
        
        learned = {}
        
        for (client_tier, llm_tier), records in confusion_pairs.items():
            if len(records) < 5:  # Need at least 5 examples
                continue
            
            # Analyze patterns in this confusion
            contents = [r.get("content_preview", "") for r in records]
            action_types = [r.get("action_type", "general") for r in records]
            
            # Extract common n-grams for this confusion
            common_ngrams = self._extract_ngrams(contents, n=2)
            
            # Find dominant action type
            action_counter = Counter(action_types)
            dominant_action = action_counter.most_common(1)[0][0] if action_counter else "general"
            
            learned[f"{client_tier}_vs_{llm_tier}"] = {
                "count": len(records),
                "common_ngrams": common_ngrams[:5],
                "dominant_action": dominant_action,
                "action_distribution": dict(action_counter.most_common(3)),
                "example": contents[0] if contents else "",
            }
        
        return learned
    
    def _generate_enhanced_patterns(self, mismatches: list[dict]) -> list[RoutingPattern]:
        """Generate new patterns from mismatched classifications with context awareness."""
        patterns = []
        
        # Group mismatches by the correct tier (llm_tier)
        by_tier: dict[str, list[dict]] = defaultdict(list)
        for m in mismatches:
            tier = m.get("llm_tier", "medium")
            if tier not in by_tier:
                by_tier[tier] = []
            by_tier[tier].append(m)
        
        # Analyze each tier group
        for tier, records in by_tier.items():
            if len(records) < 3:  # Need at least 3 examples
                continue
            
            content_samples = [r.get("content_preview", "") for r in records]
            action_types = [r.get("action_type", "general") for r in records]
            
            # Extract n-gram patterns (2-3 word phrases)
            bigrams = self._extract_ngrams(content_samples, n=2)
            trigrams = self._extract_ngrams(content_samples, n=3)
            
            # Weight by frequency
            all_ngrams = bigrams + trigrams
            ngram_counter = Counter(all_ngrams)
            
            # Find dominant action context
            action_counter = Counter(action_types)
            dominant_action = action_counter.most_common(1)[0][0] if action_counter else None
            
            # Create patterns from top n-grams
            for ngram, count in ngram_counter.most_common(3):
                # Create regex pattern
                escaped = re.escape(ngram)
                regex = rf"\b{escaped}\b"
                
                pattern = RoutingPattern(
                    regex=regex,
                    tier=RoutingTier(tier),
                    confidence=0.7,  # Start conservative, will improve with usage
                    examples=content_samples[:3],
                    added_at=datetime.now().isoformat(),
                    source="auto_calibration",
                    action_context=dominant_action,
                )
                patterns.append(pattern)
        
        return patterns
    
    def _extract_ngrams(self, contents: list[str], n: int = 2) -> list[str]:
        """Extract n-grams (word phrases) from content samples."""
        ngrams = []
        
        for content in contents:
            # Clean and tokenize
            words = re.findall(r'\b\w+\b', content.lower())
            
            # Filter out very short words (likely not meaningful)
            words = [w for w in words if len(w) > 2]
            
            # Generate n-grams
            for i in range(len(words) - n + 1):
                ngram = " ".join(words[i:i+n])
                ngrams.append(ngram)
        
        return ngrams
    
    def _update_pattern_performance(self, patterns: list[RoutingPattern]) -> None:
        """Update performance stats for all patterns based on classification history."""
        for pattern in patterns:
            # Count how many times this pattern was used
            for record in self._classifications:
                content = record.get("content_preview", "").lower()
                
                if re.search(pattern.regex, content, re.IGNORECASE):
                    pattern.times_used += 1
                    pattern.times_matched += 1
                    
                    # Check if match led to correct tier
                    final_tier = record.get("final_tier")
                    if final_tier and pattern.tier.value == final_tier:
                        pattern.times_correct += 1
    
    def _evict_patterns_intelligent(self, patterns: list[RoutingPattern]) -> list[RoutingPattern]:
        """Intelligent pattern eviction considering multiple factors."""
        # Score all patterns
        scored_patterns = []
        
        for pattern in patterns:
            score = pattern.effectiveness_score
            scored_patterns.append((pattern, score))
        
        # Sort by score descending
        scored_patterns.sort(key=lambda x: x[1], reverse=True)
        
        # Keep top patterns up to max_patterns
        return [p for p, score in scored_patterns[:self.max_patterns]]
    
    def _calibrate_thresholds(self) -> dict:
        """Adaptively calibrate tier thresholds based on accuracy data."""
        adjustments = {}
        
        # Current default thresholds
        current_thresholds = {
            "simple": 0.0,
            "medium": 0.5,
            "complex": 0.85,
            "coding": 0.90,
            "reasoning": 0.97,
        }
        
        for tier in current_thresholds.keys():
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
                bucket = round(conf * 10) / 10  # Round to nearest 0.1
                buckets[bucket].append(r)
            
            # Find optimal threshold
            best_threshold = current_thresholds[tier]
            best_accuracy = 0
            best_sample_size = 0
            
            # Test different thresholds
            test_thresholds = [0.5, 0.6, 0.7, 0.75, 0.8, 0.85, 0.9, 0.95]
            if tier == "simple":
                test_thresholds = [0.0, 0.1, 0.2, 0.3, 0.4, 0.5]
            
            for threshold in test_thresholds:
                # Get records above this threshold
                above_threshold = [
                    r for bucket, records in buckets.items() 
                    if bucket >= threshold for r in records
                ]
                
                if len(above_threshold) < 10:
                    continue
                
                # Calculate accuracy
                matches = sum(1 for r in above_threshold if r["client_tier"] == r["llm_tier"])
                accuracy = matches / len(above_threshold)
                
                # Prefer higher accuracy, but also consider sample size
                # Use a weighted score
                weighted_score = accuracy * 0.8 + (min(len(above_threshold), 100) / 100) * 0.2
                
                if weighted_score > (best_accuracy * 0.8 + (min(best_sample_size, 100) / 100) * 0.2):
                    best_threshold = threshold
                    best_accuracy = accuracy
                    best_sample_size = len(above_threshold)
            
            if best_threshold != current_thresholds[tier]:
                baseline_accuracy = sum(1 for r in tier_records if r["client_tier"] == r["llm_tier"]) / len(tier_records)
                adjustments[tier] = {
                    "old_threshold": current_thresholds[tier],
                    "new_threshold": best_threshold,
                    "accuracy": best_accuracy,
                    "sample_size": best_sample_size,
                    "improvement": best_accuracy - baseline_accuracy,
                }
        
        return adjustments
    
    def _load_existing_patterns(self) -> list[RoutingPattern]:
        """Load existing patterns from file."""
        if not self.patterns_file.exists():
            return []
        
        try:
            data = json.loads(self.patterns_file.read_text())
            return [RoutingPattern.from_dict(p) for p in data.get("patterns", [])]
        except Exception:
            return []
    
    def _save_patterns(self, patterns: list[RoutingPattern]) -> None:
        """Save patterns to file."""
        data = {
            "patterns": [p.to_dict() for p in patterns],
            "version": "2.0",
            "last_calibration": datetime.now().isoformat(),
            "total_classifications": len(self._classifications),
            "pattern_stats": {
                "total": len(patterns),
                "effective": sum(1 for p in patterns if p.is_effective),
                "auto_generated": sum(1 for p in patterns if p.source == "auto_calibration"),
                "manual": sum(1 for p in patterns if p.source == "manual"),
            }
        }
        
        self.patterns_file.parent.mkdir(parents=True, exist_ok=True)
        self.patterns_file.write_text(json.dumps(data, indent=2))
    
    def _backup_patterns(self) -> None:
        """Create backup of current patterns."""
        if self.patterns_file.exists():
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            backup_file = self.patterns_file.parent / f"patterns_backup_{timestamp}.json"
            backup_file.write_text(self.patterns_file.read_text())
    
    def _save_analytics(self) -> None:
        """Save analytics data."""
        data = {
            "classifications": self._classifications,
            "last_calibration": self._last_calibration.isoformat() if self._last_calibration else None,
            "total_count": len(self._classifications),
        }
        
        self.analytics_file.parent.mkdir(parents=True, exist_ok=True)
        self.analytics_file.write_text(json.dumps(data, indent=2))
    
    def _parse_interval(self, interval: str) -> int:
        """Parse interval string to hours."""
        try:
            if interval.endswith("h"):
                return int(interval[:-1])
            elif interval.endswith("d"):
                return int(interval[:-1]) * 24
            elif interval.isdigit():
                return int(interval)
            else:
                return 24  # Default 24 hours
        except ValueError:
            return 24  # Default 24 hours on any parsing error
    
    def get_calibration_report(self) -> dict:
        """Generate a comprehensive calibration report."""
        if not self._classifications:
            return {"error": "No classification data available"}
        
        accuracy_report = self._analyze_accuracy()
        
        # Pattern effectiveness
        patterns = self._load_existing_patterns()
        effective_count = sum(1 for p in patterns if p.is_effective)
        
        # Top performing patterns
        top_patterns = sorted(
            patterns, 
            key=lambda p: p.effectiveness_score, 
            reverse=True
        )[:10]
        
        # Low performing patterns (candidates for eviction)
        low_patterns = [
            p for p in patterns 
            if not p.is_effective and p.times_used > 10
        ]
        
        return {
            "total_classifications": len(self._classifications),
            "accuracy": accuracy_report["accuracy"],
            "matches": accuracy_report["matches"],
            "tier_accuracy": accuracy_report.get("tier_accuracy", {}),
            "total_patterns": len(patterns),
            "effective_patterns": effective_count,
            "ineffective_patterns": len(patterns) - effective_count,
            "top_patterns": [
                {
                    "regex": p.regex[:50],
                    "tier": p.tier.value,
                    "effectiveness": p.effectiveness_score,
                    "success_rate": p.success_rate,
                    "times_used": p.times_used,
                }
                for p in top_patterns
            ],
            "low_performers": [
                {
                    "regex": p.regex[:50],
                    "tier": p.tier.value,
                    "success_rate": p.success_rate,
                    "times_used": p.times_used,
                }
                for p in low_patterns[:5]
            ],
            "last_calibration": self._last_calibration.isoformat() if self._last_calibration else None,
        }

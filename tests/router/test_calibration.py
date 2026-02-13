"""Tests for calibration system."""

import pytest
import json
import re
from datetime import datetime, timedelta
from pathlib import Path
from unittest.mock import Mock

from nanobot.agent.router.calibration import CalibrationManager
from nanobot.agent.router.models import RoutingPattern, RoutingTier


class TestCalibrationManager:
    """Test CalibrationManager."""

    def test_init(self, tmp_path):
        """Test initialization."""
        patterns_file = tmp_path / "patterns.json"
        analytics_file = tmp_path / "analytics.json"

        config = {
            "interval": "24h",
            "min_classifications": 50,
            "max_patterns": 100,
        }

        manager = CalibrationManager(
            patterns_file=patterns_file,
            analytics_file=analytics_file,
            config=config,
        )

        assert manager.patterns_file == patterns_file
        assert manager.analytics_file == analytics_file
        assert manager.interval == "24h"
        assert manager.min_classifications == 50
        assert manager.max_patterns == 100

    def test_record_classification(self):
        """Test recording classifications."""
        manager = CalibrationManager(
            patterns_file=Path("/tmp/test_patterns.json"),
            config={},
        )

        record = {
            "content_preview": "Test message",
            "client_tier": "simple",
            "client_confidence": 0.9,
            "layer": "client",
        }

        manager.record_classification(record)

        assert len(manager._classifications) == 1
        assert manager._classifications[0]["content_preview"] == "Test message"
        assert "timestamp" in manager._classifications[0]

    def test_record_classification_limits_size(self):
        """Test that old classifications are removed after 1000."""
        manager = CalibrationManager(
            patterns_file=Path("/tmp/test_patterns.json"),
            config={},
        )

        # Add 1001 classifications
        for i in range(1001):
            manager.record_classification({"content_preview": str(i)})

        # Should only keep last 1000
        assert len(manager._classifications) == 1000
        # First one should be removed
        assert manager._classifications[0]["content_preview"] == "1"

    def test_should_calibrate_no_data(self):
        """Test calibration check with no data."""
        manager = CalibrationManager(
            patterns_file=Path("/tmp/test_patterns.json"),
            config={"min_classifications": 50},
        )

        assert manager.should_calibrate() is False

    def test_should_calibrate_enough_data(self):
        """Test calibration check with enough data."""
        manager = CalibrationManager(
            patterns_file=Path("/tmp/test_patterns.json"),
            config={"interval": "24h", "min_classifications": 50},
        )

        # Add 50+ classifications
        for i in range(60):
            manager.record_classification({"content_preview": str(i)})

        # No last calibration, so should calibrate
        assert manager.should_calibrate() is True

    def test_should_calibrate_count_override(self):
        """Test calibration when count threshold overrides time."""
        manager = CalibrationManager(
            patterns_file=Path("/tmp/test_patterns.json"),
            config={"interval": "24h", "min_classifications": 50},
        )

        # Set recent calibration
        manager._last_calibration = datetime.now()

        # Add many classifications (overrides time threshold)
        for i in range(100):
            manager.record_classification({"content_preview": str(i)})

        # Should calibrate due to count
        assert manager.should_calibrate() is True

    def test_analyze_accuracy(self):
        """Test accuracy analysis."""
        manager = CalibrationManager(
            patterns_file=Path("/tmp/test_patterns.json"),
            config={},
        )

        # Add classifications with matches and mismatches
        manager._classifications = [
            {"client_tier": "simple", "llm_tier": "simple", "timestamp": datetime.now().isoformat()},  # Match
            {"client_tier": "complex", "llm_tier": "complex", "timestamp": datetime.now().isoformat()},  # Match
            {"client_tier": "simple", "llm_tier": "medium", "timestamp": datetime.now().isoformat()},  # Mismatch
        ]

        report = manager._analyze_accuracy()

        assert report["total"] == 3
        assert report["matches"] == 2
        assert report["accuracy"] == pytest.approx(2/3)
        assert len(report["mismatches"]) == 1

    def test_extract_ngrams(self):
        """Test n-gram extraction from content samples."""
        manager = CalibrationManager(
            patterns_file=Path("/tmp/test_patterns.json"),
            config={},
        )

        contents = [
            "Debug this code error",
            "Debug the issue",
            "Debug system failure",
        ]

        ngrams = manager._extract_ngrams(contents, n=1)

        assert len(ngrams) > 0
        assert any("debug" in p.lower() for p in ngrams)

    def test_evict_patterns_intelligent(self):
        """Test intelligent pattern eviction."""
        manager = CalibrationManager(
            patterns_file=Path("/tmp/test_patterns.json"),
            config={"max_patterns": 2},
        )

        patterns = [
            RoutingPattern(
                regex=r"test1",
                tier=RoutingTier.SIMPLE,
                confidence=0.8,
                examples=[],
                added_at=datetime.now().isoformat(),
                times_matched=10,
                times_correct=9,
                times_used=10,
            ),
            RoutingPattern(
                regex=r"test2",
                tier=RoutingTier.MEDIUM,
                confidence=0.8,
                examples=[],
                added_at=datetime.now().isoformat(),
                times_matched=10,
                times_correct=1,
                times_used=10,
            ),
            RoutingPattern(
                regex=r"test3",
                tier=RoutingTier.COMPLEX,
                confidence=0.8,
                examples=[],
                added_at=(datetime.now() - timedelta(days=10)).isoformat(),
                times_matched=10,
                times_correct=0,
                times_used=10,
            ),
        ]

        result = manager._evict_patterns_intelligent(patterns)

        # Should keep best two
        assert len(result) == 2
        assert result[0].regex == r"test1"
        assert result[1].regex == r"test2"

    def test_parse_interval(self):
        """Test interval parsing."""
        manager = CalibrationManager(
            patterns_file=Path("/tmp/test_patterns.json"),
            config={},
        )

        assert manager._parse_interval("24h") == 24
        assert manager._parse_interval("1d") == 24
        assert manager._parse_interval("100") == 100
        assert manager._parse_interval("invalid") == 24


class TestCalibrationFileOperations:
    """Test file operations in calibration."""

    def test_load_existing_patterns(self, tmp_path):
        """Test loading existing patterns from file."""
        patterns_file = tmp_path / "patterns.json"

        # Create file with patterns
        data = {
            "patterns": [
                {
                    "regex": r"test",
                    "tier": "simple",
                    "confidence": 0.8,
                    "examples": [],
                    "added_at": datetime.now().isoformat(),
                }
            ]
        }
        patterns_file.write_text(json.dumps(data))

        manager = CalibrationManager(
            patterns_file=patterns_file,
            config={},
        )

        patterns = manager._load_existing_patterns()
        assert len(patterns) == 1
        assert patterns[0].regex == r"test"

    def test_save_patterns(self, tmp_path):
        """Test saving patterns to file."""
        patterns_file = tmp_path / "patterns.json"

        manager = CalibrationManager(
            patterns_file=patterns_file,
            config={},
        )

        patterns = [
            RoutingPattern(
                regex=r"test",
                tier=RoutingTier.SIMPLE,
                confidence=0.8,
                examples=["example"],
                added_at=datetime.now().isoformat(),
            )
        ]

        manager._save_patterns(patterns)

        # Verify file was created
        assert patterns_file.exists()
        data = json.loads(patterns_file.read_text())
        assert len(data["patterns"]) == 1
        assert data["version"] == "2.0"

    def test_backup_patterns(self, tmp_path):
        """Test pattern backup before calibration."""
        patterns_file = tmp_path / "patterns.json"
        patterns_file.write_text(json.dumps({"patterns": []}))

        manager = CalibrationManager(
            patterns_file=patterns_file,
            config={"backup_before_calibration": True},
        )

        manager._backup_patterns()

        # Find the backup file
        backups = list(tmp_path.glob("patterns_backup_*.json"))
        assert len(backups) == 1

    def test_load_analytics(self, tmp_path):
        """Test loading analytics from file."""
        analytics_file = tmp_path / "analytics.json"

        data = {
            "classifications": [{"content_preview": "test"}],
            "last_calibration": datetime.now().isoformat(),
        }
        analytics_file.write_text(json.dumps(data))

        manager = CalibrationManager(
            patterns_file=tmp_path / "patterns.json",
            analytics_file=analytics_file,
            config={},
        )

        manager._load_analytics()

        assert len(manager._classifications) == 1
        assert manager._last_calibration is not None

    def test_save_analytics(self, tmp_path):
        """Test saving analytics to file."""
        analytics_file = tmp_path / "analytics.json"

        manager = CalibrationManager(
            patterns_file=tmp_path / "patterns.json",
            analytics_file=analytics_file,
            config={},
        )

        manager._classifications = [{"content_preview": "test"}]
        manager._last_calibration = datetime.now()

        manager._save_analytics()

        assert analytics_file.exists()
        data = json.loads(analytics_file.read_text())
        assert len(data["classifications"]) == 1

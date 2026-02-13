"""Skills loader for agent capabilities with security verification."""

import json
import os
import re
import shutil
from pathlib import Path

from loguru import logger

# Default builtin skills directory
BUILTIN_SKILLS_DIR = Path(__file__).parent.parent / "skills"


class SkillVerificationStatus:
    """Security verification status for a skill."""
    PENDING = "pending"      # Not yet scanned
    APPROVED = "approved"    # Passed security scan
    REJECTED = "rejected"    # Failed security scan (dangerous)
    MANUAL_APPROVAL = "manual_approval"  # Flagged but user approved


class SkillManager:
    """
    Loader for agent skills with security verification.
    
    Skills are markdown files (SKILL.md) that teach the agent how to use
    specific tools or perform certain tasks.
    """

    def __init__(self, workspace: Path, builtin_skills_dir: Path | None = None):
        self.workspace = workspace
        self.workspace_skills = workspace / "skills"
        self.builtin_skills = builtin_skills_dir or BUILTIN_SKILLS_DIR
        self.verification_dir = workspace / ".nanobot" / "skill-verification"
        self.verification_dir.mkdir(parents=True, exist_ok=True)

        # Auto-scan any new skills on initialization
        self._auto_scan_new_skills()

    def _auto_scan_new_skills(self) -> None:
        """Automatically scan any unverified workspace skills."""
        if not self.workspace_skills.exists():
            return

        for skill_dir in self.workspace_skills.iterdir():
            if skill_dir.is_dir() and (skill_dir / "SKILL.md").exists():
                status = self.get_verification_status(skill_dir.name)
                if status == SkillVerificationStatus.PENDING:
                    logger.info(f"New skill detected: {skill_dir.name}, running security scan...")
                    self._scan_skill_for_verification(skill_dir.name)

    def get_verification_status(self, skill_name: str) -> str:
        """Get verification status for a skill."""
        if self.builtin_skills and (self.builtin_skills / skill_name / "SKILL.md").exists():
            return SkillVerificationStatus.APPROVED

        verification_file = self.verification_dir / f"{skill_name}.json"
        if verification_file.exists():
            try:
                data = json.loads(verification_file.read_text())
                return data.get("status", SkillVerificationStatus.PENDING)
            except:
                pass
        return SkillVerificationStatus.PENDING

    def _scan_skill_for_verification(self, skill_name: str) -> dict:
        """Run security scan and save results."""
        try:
            from nanobot.security.skill_scanner import scan_skill
            skill_path = self.workspace_skills / skill_name
            report = scan_skill(skill_path)
            status = SkillVerificationStatus.APPROVED if report.passed else SkillVerificationStatus.REJECTED

            verification_data = {
                "status": status,
                "risk_score": report.total_risk_score,
                "critical_count": report.critical_count,
                "high_count": report.high_count,
                "passed": report.passed,
                "findings_count": len(report.findings)
            }
            verification_file = self.verification_dir / f"{skill_name}.json"
            verification_file.write_text(json.dumps(verification_data, indent=2))
            return verification_data
        except Exception as e:
            logger.error(f"Failed to scan skill {skill_name}: {e}")
            return {"status": SkillVerificationStatus.PENDING, "error": str(e)}

    def list_skills(self, filter_unavailable: bool = True, include_verification: bool = True) -> list[dict]:
        """List all available skills."""
        skills = []

        # Workspace skills
        if self.workspace_skills.exists():
            for skill_dir in self.workspace_skills.iterdir():
                if skill_dir.is_dir() and (skill_dir / "SKILL.md").exists():
                    skill_info = {
                        "name": skill_dir.name,
                        "path": str(skill_dir / "SKILL.md"),
                        "source": "workspace",
                    }
                    if include_verification:
                        skill_info["verified"] = self.get_verification_status(skill_dir.name)
                    skills.append(skill_info)

        # Built-in skills
        if self.builtin_skills and self.builtin_skills.exists():
            for skill_dir in self.builtin_skills.iterdir():
                if skill_dir.is_dir() and (skill_dir / "SKILL.md").exists() and not any(s["name"] == skill_dir.name for s in skills):
                    skill_info = {
                        "name": skill_dir.name,
                        "path": str(skill_dir / "SKILL.md"),
                        "source": "builtin",
                    }
                    if include_verification:
                        skill_info["verified"] = SkillVerificationStatus.APPROVED
                    skills.append(skill_info)

        if filter_unavailable:
            filtered = []
            for s in skills:
                if not self._check_requirements(self._get_skill_meta(s["name"])):
                    continue
                if include_verification:
                    verified = s.get("verified", SkillVerificationStatus.PENDING)
                    if verified not in [SkillVerificationStatus.APPROVED, SkillVerificationStatus.MANUAL_APPROVAL]:
                        continue
                filtered.append(s)
            return filtered
        return skills

    def load_skill(self, name: str) -> str | None:
        """Load a skill by name."""
        workspace_skill = self.workspace_skills / name / "SKILL.md"
        if workspace_skill.exists():
            return workspace_skill.read_text(encoding="utf-8")

        if self.builtin_skills:
            builtin_skill = self.builtin_skills / name / "SKILL.md"
            if builtin_skill.exists():
                return builtin_skill.read_text(encoding="utf-8")
        return None

    def load_skills_for_context(self, skill_names: list[str]) -> str:
        """Load specific skills for inclusion in agent context."""
        parts = []
        for name in skill_names:
            content = self.load_skill(name)
            if content:
                content = self._strip_frontmatter(content)
                parts.append(f"### Skill: {name}\n\n{content}")
        return "\n\n---\n\n".join(parts) if parts else ""

    def get_skills_context(self) -> str:
        """Get the summary of skills for agent context."""
        return self.build_skills_summary()

    def build_skills_summary(self, show_all: bool = True) -> str:
        """Build a summary of all skills."""
        def escape_xml(s: str) -> str:
            return s.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")

        all_skills = self.list_skills(filter_unavailable=False, include_verification=True)
        if not all_skills:
            return ""

        lines = ["<skills>"]
        for s in all_skills:
            name = escape_xml(s["name"])
            path = s["path"]
            desc = escape_xml(self._get_skill_description(s["name"]))
            skill_meta = self._get_skill_meta(s["name"])
            available = self._check_requirements(skill_meta)
            verified = s.get("verified", "unknown")

            lines.append(f'  <skill available="{str(available).lower()}" verified="{verified}">')
            lines.append(f"    <name>{name}</name>")
            lines.append(f"    <description>{desc}</description>")
            lines.append(f"    <location>{path}</location>")

            if not available:
                missing = self._get_missing_requirements(skill_meta)
                if missing:
                    lines.append(f"    <requires>{escape_xml(missing)}</requires>")
            lines.append("  </skill>")
        lines.append("</skills>")
        return "\n".join(lines)

    def _get_missing_requirements(self, skill_meta: dict) -> str:
        """Get a description of missing requirements."""
        missing = []
        requires = skill_meta.get("requires", {})
        for b in requires.get("bins", []):
            if not shutil.which(b):
                missing.append(f"CLI: {b}")
        for env in requires.get("env", []):
            if not os.environ.get(env):
                missing.append(f"ENV: {env}")
        return ", ".join(missing)

    def _get_skill_description(self, name: str) -> str:
        """Get the description of a skill."""
        meta = self.get_skill_metadata(name)
        if meta and meta.get("description"):
            return meta["description"]
        return name

    def _strip_frontmatter(self, content: str) -> str:
        """Remove YAML frontmatter."""
        if content.startswith("---"):
            match = re.match(r"^---\n.*?\n---\n", content, re.DOTALL)
            if match:
                return content[match.end() :].strip()
        return content

    def _parse_nanobot_metadata(self, raw: str) -> dict:
        """Parse nanobot metadata JSON."""
        try:
            data = json.loads(raw)
            return data.get("nanobot", {}) if isinstance(data, dict) else {}
        except (json.JSONDecodeError, TypeError):
            return {}

    def _check_requirements(self, skill_meta: dict) -> bool:
        """Check if skill requirements are met."""
        requires = skill_meta.get("requires", {})
        for b in requires.get("bins", []):
            if not shutil.which(b):
                return False
        for env in requires.get("env", []):
            if not os.environ.get(env):
                return False
        return True

    def _get_skill_meta(self, name: str) -> dict:
        """Get nanobot metadata for a skill."""
        meta = self.get_skill_metadata(name) or {}
        return self._parse_nanobot_metadata(meta.get("metadata", ""))

    def get_always_skills(self) -> list[str]:
        """Get skills marked as always=true."""
        result = []
        for s in self.list_skills(filter_unavailable=True):
            meta = self.get_skill_metadata(s["name"]) or {}
            skill_meta = self._parse_nanobot_metadata(meta.get("metadata", ""))
            if skill_meta.get("always") or meta.get("always"):
                result.append(s["name"])
        return result

    def get_skill_metadata(self, name: str) -> dict | None:
        """Get metadata from a skill's frontmatter."""
        content = self.load_skill(name)
        if not content:
            return None
        if content.startswith("---"):
            match = re.match(r"^---\n(.*?)\n---", content, re.DOTALL)
            if match:
                metadata = {}
                for line in match.group(1).split("\n"):
                    if ":" in line:
                        key, value = line.split(":", 1)
                        metadata[key.strip()] = value.strip().strip("\"'")
                return metadata
        return None

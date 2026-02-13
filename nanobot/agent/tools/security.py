"""Security tool for the agent to scan skills.

This tool allows the agent to validate skills for security issues
before installing or using them.
"""

from pathlib import Path
from typing import Any

from loguru import logger

from nanobot.agent.tools.base import Tool
from nanobot.security.skill_scanner import scan_skill, format_report_for_cli


class ScanSkillTool(Tool):
    """
    Tool to scan a skill for security vulnerabilities.
    
    This tool allows the agent to validate skills before installation,
    ensuring they don't contain malicious code or dangerous operations.
    
    Usage:
        Agent: "I'll scan this skill before we install it..."
        → Calls scan_skill with the skill path
        → Reports findings to user
    """
    
    @property
    def name(self) -> str:
        return "scan_skill"
    
    @property
    def description(self) -> str:
        return (
            "Scan a skill for security vulnerabilities before installation. "
            "Use this tool whenever you're about to install a new skill or "
            "when a user asks you to validate a skill's safety. "
            "This protects against malicious skills that could compromise security."
        )
    
    @property
    def parameters(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "skill_path": {
                    "type": "string",
                    "description": "Path to the skill directory or SKILL.md file to scan (e.g., './skills/my-skill' or './skills/my-skill/SKILL.md')"
                },
                "strict_mode": {
                    "type": "boolean",
                    "description": "If true, blocks on medium severity issues as well as critical/high. Use for extra safety.",
                    "default": False
                }
            },
            "required": ["skill_path"]
        }
    
    async def execute(self, skill_path: str, strict_mode: bool = False, **kwargs) -> str:
        """
        Execute skill security scan.
        
        Args:
            skill_path: Path to skill directory or file
            strict_mode: Enable strict scanning (blocks on medium severity)
            
        Returns:
            Formatted security report
        """
        try:
            path = Path(skill_path)
            
            if not path.exists():
                return f"❌ Error: Skill path not found: {skill_path}"
            
            logger.info(f"Agent scanning skill for security: {path}")
            
            # Perform the scan
            report = scan_skill(path, strict=strict_mode)
            
            # Generate report
            if report.passed:
                result = f"""
✅ **Security Scan Passed**

Skill: {path.name}
Risk Score: {report.total_risk_score}/100
Findings: {len(report.findings)}

The skill appears safe for installation.
"""
                if report.findings:
                    result += "\n⚠️  Minor issues found (informational only):\n"
                    for finding in report.findings:
                        if finding.severity.value in ['medium', 'low']:
                            result += f"\n• [{finding.severity.value.upper()}] {finding.category}:\n"
                            result += f"  {finding.description}\n"
                
                return result
            
            else:
                # Security issues found
                result = f"""
🚫 **Security Scan FAILED - Do Not Install!**

Skill: {path.name}
Risk Score: {report.total_risk_score}/100
Critical Issues: {report.critical_count}
High Issues: {report.high_count}

**This skill contains dangerous patterns that could compromise your system.**

**Critical Findings (Blockers):**
"""
                # List critical and high findings first
                for finding in report.findings:
                    if finding.severity.value in ['critical', 'high']:
                        result += f"""
🚫 **{finding.category.replace('_', ' ').title()}**
- Severity: {finding.severity.value.upper()}
- Description: {finding.description}
"""
                        if finding.line_content:
                            result += f"- Code: `{finding.line_content[:80]}`\n"
                        if finding.remediation:
                            result += f"- Why it's dangerous: {finding.remediation}\n"
                
                # Add medium findings if any
                medium_count = sum(1 for f in report.findings if f.severity.value == 'medium')
                if medium_count > 0:
                    result += f"\n⚠️  Additionally found {medium_count} medium-risk issues.\n"
                
                result += """
**Recommendation:** 
❌ DO NOT install this skill. It contains patterns associated with malware:
- Stealing SSH keys or credentials
- Executing unverified code from the internet  
- Disabling security protections
- Installing persistence mechanisms

**If you trust this skill:**
1. Ask the skill developer to remove the dangerous patterns
2. Review the code manually with security expertise
3. Run in an isolated environment (not recommended)
"""
                
                return result
                
        except Exception as e:
            logger.error(f"Skill scan failed: {e}")
            return f"❌ Error scanning skill: {str(e)}"


class ValidateSkillSafetyTool(Tool):
    """
    Quick validation tool to check if a skill is safe.
    
    This is a lighter-weight version that just returns safe/unsafe status
    without detailed reporting. Good for automatic checks.
    """
    
    @property
    def name(self) -> str:
        return "validate_skill_safety"
    
    @property
    def description(self) -> str:
        return (
            "Quickly check if a skill is safe to use (returns true/false). "
            "Use this for automatic validation when speed is important. "
            "For detailed security analysis, use the scan_skill tool instead."
        )
    
    @property
    def parameters(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "skill_path": {
                    "type": "string",
                    "description": "Path to skill directory or SKILL.md file"
                }
            },
            "required": ["skill_path"]
        }
    
    async def execute(self, skill_path: str, **kwargs) -> str:
        """Quick safety check."""
        try:
            path = Path(skill_path)
            
            if not path.exists():
                return "false"
            
            report = scan_skill(path, strict=False)
            
            # Just return true/false as string for easy parsing
            if report.passed:
                return f"true (Risk score: {report.total_risk_score}/100)"
            else:
                return f"false (Risk score: {report.total_risk_score}/100 - Critical: {report.critical_count}, High: {report.high_count})"
                
        except Exception as e:
            logger.error(f"Safety validation failed: {e}")
            return "false (error)"


def create_security_tools() -> list[Tool]:
    """
    Create all security-related tools for the agent.
    
    Returns:
        List of security tools
    """
    return [
        ScanSkillTool(),
        ValidateSkillSafetyTool(),
    ]

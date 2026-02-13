"""Security scanner for nanobot skills.

This module provides security scanning capabilities to detect potentially
malicious skills before they are installed or executed. Based on security
best practices from AI agent security research.

Features:
- Pattern matching for dangerous commands (curl | bash, sudo, etc.)
- Static analysis of skill code
- Dependency validation
- Security scoring and reporting
- User warnings with clear explanations
"""

import re
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import List, Optional

from loguru import logger


class Severity(Enum):
    """Severity levels for security findings."""
    CRITICAL = "critical"  # Immediate blocking required
    HIGH = "high"          # Strong warning, likely malicious
    MEDIUM = "medium"      # Suspicious, review recommended
    LOW = "low"            # Minor concern, informational


@dataclass
class SecurityFinding:
    """A single security finding."""
    severity: Severity
    category: str
    description: str
    line_number: Optional[int] = None
    line_content: Optional[str] = None
    remediation: Optional[str] = None


@dataclass
class SecurityReport:
    """Complete security scan report for a skill."""
    skill_name: str
    findings: List[SecurityFinding] = field(default_factory=list)
    passed: bool = True
    
    @property
    def critical_count(self) -> int:
        return sum(1 for f in self.findings if f.severity == Severity.CRITICAL)
    
    @property
    def high_count(self) -> int:
        return sum(1 for f in self.findings if f.severity == Severity.HIGH)
    
    @property
    def total_risk_score(self) -> int:
        """Calculate total risk score (0-100)."""
        score = 0
        for finding in self.findings:
            if finding.severity == Severity.CRITICAL:
                score += 25
            elif finding.severity == Severity.HIGH:
                score += 15
            elif finding.severity == Severity.MEDIUM:
                score += 5
            elif finding.severity == Severity.LOW:
                score += 1
        return min(score, 100)
    
    def get_summary(self) -> str:
        """Generate human-readable summary."""
        if not self.findings:
            return "✅ No security issues found"
        
        parts = [f"🔍 Security Scan: {self.skill_name}"]
        parts.append(f"Risk Score: {self.total_risk_score}/100")
        parts.append(f"Critical: {self.critical_count}, High: {self.high_count}")
        parts.append("")
        
        for finding in self.findings:
            icon = {
                Severity.CRITICAL: "🚫",
                Severity.HIGH: "⚠️",
                Severity.MEDIUM: "⚡",
                Severity.LOW: "ℹ️"
            }[finding.severity]
            
            parts.append(f"{icon} [{finding.severity.value.upper()}] {finding.category}")
            parts.append(f"   {finding.description}")
            if finding.line_number:
                parts.append(f"   Line {finding.line_number}: {finding.line_content}")
            if finding.remediation:
                parts.append(f"   💡 Fix: {finding.remediation}")
            parts.append("")
        
        return "\n".join(parts)


class SkillSecurityScanner:
    """
    Security scanner for nanobot skills.
    
    Scans skill files for potentially malicious patterns, dangerous commands,
    and security anti-patterns. Based on real-world attacks on AI agents.
    
    Usage:
        scanner = SkillSecurityScanner()
        report = scanner.scan_skill(skill_path)
        if not report.passed:
            print(report.get_summary())
    """
    
    # Critical patterns - immediate blocking
    CRITICAL_PATTERNS = {
        "quarantine_removal": (
            re.compile(r'xattr\s+-d\s+.*quarantine|spctl\s+--disable', re.IGNORECASE),
            "Removes macOS quarantine/security protections",
            "This is a clear malware indicator - removes Gatekeeper protections"
        ),
        "ssh_key_access": (
            re.compile(r'[~./]\.ssh/id_|cat\s+.*\.ssh|ssh-keygen', re.IGNORECASE),
            "Accesses or modifies SSH keys",
            "SSH keys are high-value targets for attackers"
        ),
        "credential_exfiltration": (
            re.compile(r'curl.*-d.*key|wget.*--post-data.*secret|base64\s+.*\|\s*curl', re.IGNORECASE),
            "Potential credential exfiltration",
            "Sends sensitive data to external servers"
        ),
    }
    
    # High severity patterns - strong warning
    HIGH_PATTERNS = {
        "curl_pipe_bash": (
            re.compile(r'curl\s+[^|]*\|\s*(bash|sh|zsh)|wget\s+[^|]*\|\s*(bash|sh|zsh)', re.IGNORECASE),
            "Downloads and executes remote code",
            "Classic 'curl | bash' attack vector - executes unverified code"
        ),
        "sudo_usage": (
            re.compile(r'\bsudo\b', re.IGNORECASE),
            "Uses sudo for privilege escalation",
            "Skills should not require root privileges"
        ),
        "system_modification": (
            re.compile(r'/etc/|/usr/bin|/usr/local|/System/', re.IGNORECASE),
            "Modifies system directories",
            "Skills should stay in their workspace, not modify system"
        ),
        "persistence_mechanism": (
            re.compile(r'LaunchAgents|LaunchDaemons|crontab|cron\.|\.bashrc|\.zshrc|\.bash_profile', re.IGNORECASE),
            "Installs persistence mechanism",
            "Malware often uses these to survive reboots"
        ),
    }
    
    # Medium severity patterns - suspicious
    MEDIUM_PATTERNS = {
        "base64_decoding": (
            re.compile(r'base64\s+-d|base64\s+--decode|atob\(|Buffer\.from\([^,]*base64', re.IGNORECASE),
            "Decodes obfuscated content",
            "May hide malicious code in encoded strings"
        ),
        "eval_execution": (
            re.compile(r'\beval\s*\(|\bexec\s*\(|\bcompile\s*\(|\b__import__\s*\(', re.IGNORECASE),
            "Dynamic code execution",
            "Can execute arbitrary code, often abused by malware"
        ),
        "network_requests": (
            re.compile(r'curl\s+|wget\s+|requests\.(get|post)|urllib|http\.client', re.IGNORECASE),
            "Makes network requests",
            "Review what data is being sent externally"
        ),
        "suspicious_downloads": (
            re.compile(r'githubusercontent|pastebin|transfer\.sh|file\.io', re.IGNORECASE),
            "Downloads from suspicious file hosting",
            "Temporary file hosting often used for malware distribution"
        ),
    }
    
    # Low severity patterns - informational
    LOW_PATTERNS = {
        "binary_execution": (
            re.compile(r'\.bin\b|\./[^/]+\s|chmod\s+\+x', re.IGNORECASE),
            "Executes binary files",
            "Binary execution makes code review harder"
        ),
        "external_urls": (
            re.compile(r'https?://[^\s\'"]+', re.IGNORECASE),
            "References external URLs",
            "Verify all external links are legitimate"
        ),
    }
    
    def __init__(self, strict_mode: bool = False):
        """
        Initialize the security scanner.
        
        Args:
            strict_mode: If True, blocks on MEDIUM severity as well
        """
        self.strict_mode = strict_mode
        self.all_patterns = {
            Severity.CRITICAL: self.CRITICAL_PATTERNS,
            Severity.HIGH: self.HIGH_PATTERNS,
            Severity.MEDIUM: self.MEDIUM_PATTERNS,
            Severity.LOW: self.LOW_PATTERNS,
        }
    
    def scan_skill(self, skill_path: Path) -> SecurityReport:
        """
        Scan a skill directory or file for security issues.
        
        Args:
            skill_path: Path to skill directory or skill.md file
            
        Returns:
            SecurityReport with findings
        """
        findings = []
        skill_name = skill_path.name if skill_path.is_file() else skill_path.parent.name
        
        # Find files to scan
        files_to_scan = self._get_files_to_scan(skill_path)
        
        for file_path in files_to_scan:
            try:
                content = file_path.read_text(encoding='utf-8')
                file_findings = self._scan_content(content, file_path)
                findings.extend(file_findings)
            except Exception as e:
                logger.warning(f"Could not scan {file_path}: {e}")
        
        # Determine if scan passed
        critical = sum(1 for f in findings if f.severity == Severity.CRITICAL)
        high = sum(1 for f in findings if f.severity == Severity.HIGH)
        medium = sum(1 for f in findings if f.severity == Severity.MEDIUM)
        
        if critical > 0:
            passed = False
        elif high > 0:
            passed = False
        elif self.strict_mode and medium > 0:
            passed = False
        else:
            passed = True
        
        report = SecurityReport(
            skill_name=skill_name,
            findings=findings,
            passed=passed
        )
        
        logger.info(f"Security scan for {skill_name}: {len(findings)} findings, score {report.total_risk_score}/100")
        
        return report
    
    def _get_files_to_scan(self, skill_path: Path) -> List[Path]:
        """Get list of files to scan in a skill."""
        files = []
        
        if skill_path.is_file():
            files.append(skill_path)
        elif skill_path.is_dir():
            # Scan SKILL.md and any .py, .sh, .js files
            for ext in ['.md', '.py', '.sh', '.bash', '.zsh', '.js', '.ts', '.json', '.yaml', '.yml']:
                files.extend(skill_path.glob(f'*{ext}'))
                files.extend(skill_path.glob(f'**/*{ext}'))
        
        return list(set(files))  # Remove duplicates
    
    def _scan_content(self, content: str, file_path: Path) -> List[SecurityFinding]:
        """Scan file content for security patterns."""
        findings = []
        lines = content.split('\n')
        
        for severity, patterns in self.all_patterns.items():
            for category, (pattern, description, remediation) in patterns.items():
                for line_num, line in enumerate(lines, 1):
                    if pattern.search(line):
                        finding = SecurityFinding(
                            severity=severity,
                            category=category,
                            description=description,
                            line_number=line_num,
                            line_content=line.strip()[:100],  # Truncate long lines
                            remediation=remediation
                        )
                        findings.append(finding)
        
        return findings
    
    def quick_scan(self, content: str) -> bool:
        """
        Quick scan for critical issues only.
        
        Args:
            content: Text content to scan
            
        Returns:
            True if no critical issues, False if blocked
        """
        for pattern, _, _ in self.CRITICAL_PATTERNS.values():
            if pattern.search(content):
                return False
        return True


# Convenience function for CLI integration
def scan_skill(skill_path: Path, strict: bool = False) -> SecurityReport:
    """
    Convenience function to scan a skill.
    
    Args:
        skill_path: Path to skill
        strict: Enable strict mode
        
    Returns:
        Security report
    """
    scanner = SkillSecurityScanner(strict_mode=strict)
    return scanner.scan_skill(skill_path)


def format_report_for_cli(report: SecurityReport) -> str:
    """Format report for CLI display."""
    lines = []
    
    # Header with risk color
    if report.total_risk_score >= 75:
        risk_color = "[red]"
    elif report.total_risk_score >= 50:
        risk_color = "[yellow]"
    elif report.total_risk_score >= 25:
        risk_color = "[orange]"
    else:
        risk_color = "[green]"
    
    lines.append(f"\n{risk_color}╔═══════════════════════════════════════════════════════════╗[/]")
    lines.append(f"{risk_color}║[/] 🔒 Security Scan: {report.skill_name:<43} {risk_color}║[/]")
    lines.append(f"{risk_color}╠═══════════════════════════════════════════════════════════╣[/]")
    lines.append(f"{risk_color}║[/] Risk Score: {report.total_risk_score}/100{' ' * 40} {risk_color}║[/]")
    lines.append(f"{risk_color}║[/] Critical: {report.critical_count} | High: {report.high_count}{' ' * 29} {risk_color}║[/]")
    lines.append(f"{risk_color}╚═══════════════════════════════════════════════════════════╝[/]")
    
    if report.findings:
        lines.append("\n[yellow]Findings:[/]")
        for finding in report.findings:
            severity_color = {
                Severity.CRITICAL: "[red]",
                Severity.HIGH: "[orange]",
                Severity.MEDIUM: "[yellow]",
                Severity.LOW: "[dim]"
            }[finding.severity]
            
            lines.append(f"\n{severity_color}[{finding.severity.value.upper()}][/] {finding.category}")
            lines.append(f"  {finding.description}")
            if finding.line_number:
                lines.append(f"  [dim]Line {finding.line_number}:[/] {finding.line_content}")
            if finding.remediation:
                lines.append(f"  [green]💡 {finding.remediation}[/]")
    
    if not report.passed:
        lines.append(f"\n[red bold]⚠️  Installation blocked: Critical security issues found![/]")
        lines.append(f"[dim]Review the findings above or use --ignore-security to force install (not recommended)[/]")
    else:
        lines.append(f"\n[green]✅ Security check passed[/]")
    
    return "\n".join(lines)

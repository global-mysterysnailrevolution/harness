"""
Repo Analyzer — deterministic codebase analysis engine.

Scans a repository and produces an AnalysisResult containing:
- Stack detection (languages, frameworks, package managers)
- Project structure (key directories, entry points)
- Conventions (linting, formatting, testing patterns)
- Dependency graph summary
- Security-relevant patterns (secret files, Dockerfiles, CI configs)

All analysis is deterministic (no LLM calls). LLM reasoning is only used
downstream in the generator for natural-language skill/agent content.
"""
from __future__ import annotations

import hashlib
import json
import os
import subprocess
import time
from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import Optional

from contextforge.packages.events import emit_event, CorrelationIDs


# ── Detection patterns ──────────────────────────────────────────────────

LANGUAGE_INDICATORS = {
    "python": ["*.py", "requirements.txt", "setup.py", "pyproject.toml", "Pipfile"],
    "javascript": ["*.js", "*.mjs", "package.json"],
    "typescript": ["*.ts", "*.tsx", "tsconfig.json"],
    "go": ["*.go", "go.mod", "go.sum"],
    "rust": ["*.rs", "Cargo.toml"],
    "java": ["*.java", "pom.xml", "build.gradle"],
    "csharp": ["*.cs", "*.csproj", "*.sln"],
    "ruby": ["*.rb", "Gemfile"],
    "php": ["*.php", "composer.json"],
    "shell": ["*.sh", "*.bash"],
}

FRAMEWORK_INDICATORS = {
    "react": ["react", "react-dom"],
    "nextjs": ["next"],
    "vue": ["vue"],
    "django": ["django"],
    "flask": ["flask"],
    "fastapi": ["fastapi"],
    "express": ["express"],
    "nestjs": ["@nestjs/core"],
    "prisma": ["prisma", "@prisma/client"],
    "docker": ["Dockerfile", "docker-compose.yml", "docker-compose.yaml"],
    "kubernetes": ["*.yaml:kind: Deployment", "*.yaml:kind: Service"],
    "terraform": ["*.tf"],
    "github-actions": [".github/workflows"],
}

CONVENTION_FILES = {
    "eslint": [".eslintrc", ".eslintrc.js", ".eslintrc.json", ".eslintrc.yml"],
    "prettier": [".prettierrc", ".prettierrc.js", ".prettierrc.json"],
    "black": ["pyproject.toml:tool.black"],
    "ruff": ["pyproject.toml:tool.ruff", "ruff.toml"],
    "pytest": ["pytest.ini", "pyproject.toml:tool.pytest", "conftest.py"],
    "jest": ["jest.config.js", "jest.config.ts"],
    "vitest": ["vitest.config.ts", "vitest.config.js"],
    "editorconfig": [".editorconfig"],
    "gitignore": [".gitignore"],
}


@dataclass
class StackInfo:
    languages: dict[str, int] = field(default_factory=dict)  # lang -> file count
    frameworks: list[str] = field(default_factory=list)
    package_managers: list[str] = field(default_factory=list)
    has_docker: bool = False
    has_ci: bool = False
    ci_system: Optional[str] = None


@dataclass
class ConventionInfo:
    linters: list[str] = field(default_factory=list)
    formatters: list[str] = field(default_factory=list)
    test_frameworks: list[str] = field(default_factory=list)
    has_editorconfig: bool = False
    has_gitignore: bool = False


@dataclass
class ProjectStructure:
    root: str = ""
    key_directories: list[str] = field(default_factory=list)
    entry_points: list[str] = field(default_factory=list)
    config_files: list[str] = field(default_factory=list)
    total_files: int = 0
    total_lines: int = 0


@dataclass
class SecurityProfile:
    has_secrets_file: bool = False
    has_env_files: bool = False
    has_dockerfile: bool = False
    has_ci_secrets: bool = False
    exposed_ports: list[int] = field(default_factory=list)
    security_relevant_files: list[str] = field(default_factory=list)


@dataclass
class AnalysisResult:
    """Complete analysis output — the contract between analyzer and generator."""
    stack: StackInfo = field(default_factory=StackInfo)
    conventions: ConventionInfo = field(default_factory=ConventionInfo)
    structure: ProjectStructure = field(default_factory=ProjectStructure)
    security: SecurityProfile = field(default_factory=SecurityProfile)
    source_commit: str = ""
    analysis_hash: str = ""
    analyzed_at: str = ""
    repo_path: str = ""

    def to_dict(self) -> dict:
        return asdict(self)

    def compute_hash(self) -> str:
        """Deterministic hash of the analysis for idempotence verification."""
        d = self.to_dict()
        d.pop("analysis_hash", None)
        d.pop("analyzed_at", None)
        raw = json.dumps(d, sort_keys=True, ensure_ascii=True)
        return hashlib.sha256(raw.encode()).hexdigest()[:16]


class RepoAnalyzer:
    """Deterministic repository analyzer."""

    def __init__(self, repo_path: str | Path, correlation: Optional[CorrelationIDs] = None):
        self.repo_path = Path(repo_path).resolve()
        self.correlation = correlation or CorrelationIDs()

    def analyze(self) -> AnalysisResult:
        """Run full analysis. Returns AnalysisResult."""
        start = time.time()
        emit_event("analysis.started", "analyzer", self.correlation,
                   payload={"repo_path": str(self.repo_path)})

        result = AnalysisResult(repo_path=str(self.repo_path))
        result.source_commit = self._get_git_commit()

        # Collect all files
        all_files = self._collect_files()
        result.structure.total_files = len(all_files)
        result.structure.root = str(self.repo_path)

        # Stack detection
        result.stack = self._detect_stack(all_files)
        result.structure = self._analyze_structure(all_files)
        result.conventions = self._detect_conventions(all_files)
        result.security = self._analyze_security(all_files)

        # Finalize
        from datetime import datetime, timezone
        result.analyzed_at = datetime.now(timezone.utc).isoformat()
        result.analysis_hash = result.compute_hash()

        duration = int((time.time() - start) * 1000)
        emit_event("analysis.completed", "analyzer", self.correlation,
                   payload={"files_scanned": len(all_files),
                            "languages": list(result.stack.languages.keys()),
                            "frameworks": result.stack.frameworks},
                   duration_ms=duration)

        return result

    def _get_git_commit(self) -> str:
        try:
            r = subprocess.run(
                ["git", "rev-parse", "HEAD"],
                cwd=self.repo_path, capture_output=True, text=True, timeout=10,
            )
            return r.stdout.strip()[:40] if r.returncode == 0 else "unknown"
        except (subprocess.TimeoutExpired, FileNotFoundError):
            return "unknown"

    def _collect_files(self) -> list[Path]:
        """Collect all tracked files, respecting .gitignore."""
        try:
            r = subprocess.run(
                ["git", "ls-files", "--cached", "--others", "--exclude-standard"],
                cwd=self.repo_path, capture_output=True, text=True, timeout=30,
            )
            if r.returncode == 0:
                return [self.repo_path / f for f in r.stdout.strip().split("\n") if f]
        except (subprocess.TimeoutExpired, FileNotFoundError):
            pass

        # Fallback: walk directory
        files = []
        skip = {".git", "node_modules", "__pycache__", ".venv", "venv", ".tox", "dist", "build"}
        for root, dirs, filenames in os.walk(self.repo_path):
            dirs[:] = [d for d in dirs if d not in skip]
            for fn in filenames:
                files.append(Path(root) / fn)
        return files

    def _detect_stack(self, files: list[Path]) -> StackInfo:
        stack = StackInfo()
        file_names = {f.name for f in files}
        file_suffixes = {}
        for f in files:
            s = f.suffix.lower()
            if s:
                file_suffixes[s] = file_suffixes.get(s, 0) + 1

        # Languages
        for lang, indicators in LANGUAGE_INDICATORS.items():
            count = 0
            for ind in indicators:
                if ind.startswith("*."):
                    ext = ind[1:]
                    count += file_suffixes.get(ext, 0)
                elif ind in file_names:
                    count += 1
            if count > 0:
                stack.languages[lang] = count

        # Package managers
        if "package.json" in file_names:
            stack.package_managers.append("npm")
            if "yarn.lock" in file_names:
                stack.package_managers.append("yarn")
            if "pnpm-lock.yaml" in file_names:
                stack.package_managers.append("pnpm")
            if "bun.lockb" in file_names:
                stack.package_managers.append("bun")
        if "requirements.txt" in file_names or "pyproject.toml" in file_names:
            stack.package_managers.append("pip")
        if "Pipfile" in file_names:
            stack.package_managers.append("pipenv")
        if "go.mod" in file_names:
            stack.package_managers.append("go-mod")
        if "Cargo.toml" in file_names:
            stack.package_managers.append("cargo")

        # Frameworks (check package.json / requirements.txt)
        deps = self._extract_dependencies(files)
        for fw, indicators in FRAMEWORK_INDICATORS.items():
            for ind in indicators:
                if ind in deps:
                    stack.frameworks.append(fw)
                    break
                if ind in file_names or any(f.name == ind for f in files):
                    stack.frameworks.append(fw)
                    break
                # Check directory existence
                if (self.repo_path / ind).is_dir():
                    stack.frameworks.append(fw)
                    break

        # Docker
        stack.has_docker = "Dockerfile" in file_names or "docker-compose.yml" in file_names
        if "docker" not in stack.frameworks and stack.has_docker:
            stack.frameworks.append("docker")

        # CI
        ci_dirs = {".github/workflows": "github-actions", ".gitlab-ci.yml": "gitlab",
                   "Jenkinsfile": "jenkins", ".circleci": "circleci"}
        for path, ci in ci_dirs.items():
            if (self.repo_path / path).exists():
                stack.has_ci = True
                stack.ci_system = ci
                break

        return stack

    def _extract_dependencies(self, files: list[Path]) -> set[str]:
        """Extract dependency names from package.json / requirements.txt."""
        deps: set[str] = set()

        pkg_json = self.repo_path / "package.json"
        if pkg_json.exists():
            try:
                with open(pkg_json) as f:
                    pkg = json.load(f)
                for section in ("dependencies", "devDependencies", "peerDependencies"):
                    deps.update(pkg.get(section, {}).keys())
            except (json.JSONDecodeError, OSError):
                pass

        req_txt = self.repo_path / "requirements.txt"
        if req_txt.exists():
            try:
                for line in req_txt.read_text().splitlines():
                    line = line.strip()
                    if line and not line.startswith("#") and not line.startswith("-"):
                        name = line.split("==")[0].split(">=")[0].split("<=")[0].split("[")[0].strip()
                        deps.add(name.lower())
            except OSError:
                pass

        return deps

    def _analyze_structure(self, files: list[Path]) -> ProjectStructure:
        structure = ProjectStructure(
            root=str(self.repo_path),
            total_files=len(files),
        )

        # Key directories (top-level)
        try:
            top_dirs = sorted({
                f.relative_to(self.repo_path).parts[0]
                for f in files if len(f.relative_to(self.repo_path).parts) > 1
            })
            structure.key_directories = [d for d in top_dirs
                                         if d not in {".git", "node_modules", "__pycache__", ".venv"}]
        except ValueError:
            pass

        # Entry points
        entry_names = {"main.py", "app.py", "index.js", "index.ts", "main.go",
                       "main.rs", "Program.cs", "server.js", "server.ts"}
        structure.entry_points = [str(f.relative_to(self.repo_path))
                                  for f in files if f.name in entry_names]

        # Config files
        config_names = {"package.json", "pyproject.toml", "tsconfig.json", "Cargo.toml",
                        "go.mod", "Makefile", "Dockerfile", "docker-compose.yml",
                        ".env.example", "setup.py", "setup.cfg"}
        structure.config_files = [str(f.relative_to(self.repo_path))
                                  for f in files if f.name in config_names]

        return structure

    def _detect_conventions(self, files: list[Path]) -> ConventionInfo:
        conv = ConventionInfo()
        file_names = {f.name for f in files}

        linter_map = {"eslint": "eslint", "ruff": "ruff"}
        formatter_map = {"prettier": "prettier", "black": "black"}
        test_map = {"pytest": "pytest", "jest": "jest", "vitest": "vitest"}

        for tool, indicators in CONVENTION_FILES.items():
            found = False
            for ind in indicators:
                if ":" in ind:
                    fname, section = ind.split(":", 1)
                    fp = self.repo_path / fname
                    if fp.exists():
                        try:
                            content = fp.read_text(errors="replace")
                            if section in content:
                                found = True
                        except OSError:
                            pass
                elif ind in file_names:
                    found = True

            if found:
                if tool in linter_map:
                    conv.linters.append(tool)
                elif tool in formatter_map:
                    conv.formatters.append(tool)
                elif tool in test_map:
                    conv.test_frameworks.append(tool)
                elif tool == "editorconfig":
                    conv.has_editorconfig = True
                elif tool == "gitignore":
                    conv.has_gitignore = True

        return conv

    def _analyze_security(self, files: list[Path]) -> SecurityProfile:
        sec = SecurityProfile()
        for f in files:
            name = f.name.lower()
            rel = str(f.relative_to(self.repo_path))

            if name in (".env", ".env.local", ".env.production"):
                sec.has_env_files = True
                sec.security_relevant_files.append(rel)
            if name in ("secrets.json", "credentials.json", "service-account.json"):
                sec.has_secrets_file = True
                sec.security_relevant_files.append(rel)
            if name == "dockerfile":
                sec.has_dockerfile = True
                sec.security_relevant_files.append(rel)
                # Try to extract EXPOSE ports
                try:
                    for line in f.read_text(errors="replace").splitlines():
                        if line.strip().upper().startswith("EXPOSE"):
                            for part in line.split()[1:]:
                                try:
                                    sec.exposed_ports.append(int(part.split("/")[0]))
                                except ValueError:
                                    pass
                except OSError:
                    pass

        return sec

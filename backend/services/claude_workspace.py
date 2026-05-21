from __future__ import annotations

import json
import re
from datetime import datetime
from pathlib import Path
from typing import Any


REPO_ROOT = Path(__file__).resolve().parents[2]
CLAUDE_HOME = Path.home() / ".claude"

SETTINGS_FILES = [
    CLAUDE_HOME / "settings.json",
    CLAUDE_HOME / "settings.local.json",
    CLAUDE_HOME / "config.json",
    REPO_ROOT / ".claude" / "settings.json",
    REPO_ROOT / ".claude" / "settings.local.json",
]

PROJECT_MARKERS: dict[str, str] = {
    "package.json": "Node",
    "pnpm-workspace.yaml": "PNPM",
    "yarn.lock": "Yarn",
    "package-lock.json": "NPM",
    "requirements.txt": "Python",
    "pyproject.toml": "Python",
    "Pipfile": "Python",
    "poetry.lock": "Poetry",
    "pom.xml": "Maven",
    "build.gradle": "Gradle",
    "build.gradle.kts": "Gradle",
    "go.mod": "Go",
    "Cargo.toml": "Rust",
    "composer.json": "PHP",
    "Gemfile": "Ruby",
    "Dockerfile": "Docker",
    "docker-compose.yml": "Compose",
    "docker-compose.yaml": "Compose",
    ".gitlab-ci.yml": "CI",
    "Jenkinsfile": "CI",
    "README.md": "README",
    "vite.config.js": "Vite",
    "vite.config.ts": "Vite",
    "tsconfig.json": "TypeScript",
    "vue.config.js": "Vue",
    "next.config.js": "Next.js",
    "next.config.mjs": "Next.js",
    "nuxt.config.ts": "Nuxt",
    "main.py": "Python App",
    "manage.py": "Django",
    "main.go": "Go App",
}

STRONG_PROJECT_MARKERS = {
    "package.json",
    "pnpm-workspace.yaml",
    "requirements.txt",
    "pyproject.toml",
    "Pipfile",
    "pom.xml",
    "build.gradle",
    "build.gradle.kts",
    "go.mod",
    "Cargo.toml",
    "composer.json",
    "Gemfile",
    "vite.config.js",
    "vite.config.ts",
    "next.config.js",
    "next.config.mjs",
    "nuxt.config.ts",
    "main.py",
    "manage.py",
    "main.go",
}

ROOT_LIST_KEYS = {
    "workspace_roots",
    "workspaceroots",
    "project_roots",
    "projectroots",
    "workspaces",
    "projects",
    "paths",
    "directories",
    "repos",
    "repositories",
    "roots",
    "allowed_directories",
    "alloweddirectories",
}

VALUE_PATH_KEYS = {
    "path",
    "root",
    "cwd",
    "dir",
    "directory",
    "folder",
    "workspace",
    "workspace_root",
    "project_root",
    "project_path",
    "repo",
    "repo_path",
    "home_dir",
}

SKIP_CHILD_DIRS = {
    ".git",
    ".idea",
    ".vscode",
    ".claude",
    ".codex",
    ".venv",
    "node_modules",
    "__pycache__",
    "dist",
    "build",
    "coverage",
    "target",
    "vendor",
}

SKIP_SCAN_ROOT_NAMES = {
    "windows",
    "program files",
    "program files (x86)",
    "users",
    "appdata",
    ".claude",
    "desktop",
    "documents",
    "downloads",
}

WINDOWS_DRIVE_RE = re.compile(r"^[A-Za-z]:[\\/]")
UNC_RE = re.compile(r"^\\\\[^\\]+\\[^\\]+")
READ_PERMISSION_RE = re.compile(r"Read\(([^)]+)\)", re.IGNORECASE)


def _safe_read_json(path: Path) -> dict[str, Any] | list[Any] | None:
    try:
        if not path.exists() or not path.is_file():
            return None
        return json.loads(path.read_text(encoding="utf-8", errors="ignore"))
    except Exception:
        return None


def _is_probable_path(value: str) -> bool:
    text = str(value or "").strip().strip('"').strip("'")
    if not text:
        return False
    if text.startswith("http://") or text.startswith("https://"):
        return False
    if WINDOWS_DRIVE_RE.match(text) or UNC_RE.match(text):
        return True
    if text.startswith("~/") or text.startswith("~\\"):
        return True
    if text.startswith("/") and len(text) > 1:
        return True
    return False


def _normalize_path(value: str) -> Path | None:
    text = str(value or "").strip().strip('"').strip("'")
    if not text:
        return None
    if text.startswith("//") and len(text) > 3 and text[2].isalpha() and text[3] in {"/", "\\"}:
        text = f"{text[2].upper()}:{text[3:]}"
    elif text.startswith("//"):
        return None
    if text.startswith("~/") or text.startswith("~\\"):
        text = str(Path.home() / text[2:])
    if not _is_probable_path(text):
        return None
    path = Path(text).expanduser()
    return path


def _clean_permission_path(value: str) -> Path | None:
    text = str(value or "").strip().strip('"').strip("'")
    if not text:
        return None
    for suffix in ("/**", "\\**", "/*", "\\*", "//**"):
        if text.endswith(suffix):
            text = text[: -len(suffix)]
            break
    path = _normalize_path(text)
    if not path:
        return None
    suffix = path.suffix.lower()
    if suffix and not path.name.startswith(".") and not path.is_dir():
        return path.parent
    return path


def _unique_paths(paths: list[Path]) -> list[Path]:
    result: list[Path] = []
    seen: set[str] = set()
    for path in paths:
        try:
            key = str(path.resolve()).lower()
        except Exception:
            key = str(path).lower()
        if key in seen:
            continue
        seen.add(key)
        result.append(path)
    return result


def _extract_paths_from_known_field(value: Any) -> list[Path]:
    results: list[Path] = []
    if isinstance(value, str):
        path = _normalize_path(value)
        if path:
            results.append(path)
        return results
    if isinstance(value, list):
        for item in value:
            results.extend(_extract_paths_from_known_field(item))
        return results
    if isinstance(value, dict):
        for key, item in value.items():
            normalized_key = str(key).strip().lower().replace("-", "_")
            if normalized_key in VALUE_PATH_KEYS and isinstance(item, str):
                path = _normalize_path(item)
                if path:
                    results.append(path)
            elif normalized_key in ROOT_LIST_KEYS:
                results.extend(_extract_paths_from_known_field(item))
        return results
    return results


def _extract_paths_from_settings(data: Any) -> list[Path]:
    results: list[Path] = []
    if not isinstance(data, dict):
        return results

    for key, value in data.items():
        normalized_key = str(key).strip().lower().replace("-", "_")
        if normalized_key in ROOT_LIST_KEYS:
            results.extend(_extract_paths_from_known_field(value))
        elif normalized_key in VALUE_PATH_KEYS and isinstance(value, str):
            path = _normalize_path(value)
            if path:
                results.append(path)

    permissions = data.get("permissions")
    if isinstance(permissions, dict):
        for item in permissions.get("allow", []) or []:
            if not isinstance(item, str):
                continue
            match = READ_PERMISSION_RE.search(item)
            if not match:
                continue
            path = _clean_permission_path(match.group(1))
            if path:
                results.append(path)

    return _unique_paths(results)


def _iso_from_timestamp(timestamp: float | None) -> str | None:
    if not timestamp:
        return None
    return datetime.fromtimestamp(timestamp).isoformat(timespec="seconds")


def _path_key(path: Path | str) -> str:
    try:
        return str(Path(path).resolve()).lower()
    except Exception:
        return str(path).lower()


def _path_exists(path: Path) -> bool:
    try:
        return path.exists()
    except Exception:
        return False


def _load_session_meta(session_file: Path) -> dict[str, Any]:
    meta: dict[str, Any] = {
        "cwd": "",
        "git_branch": "",
        "last_active_at": _iso_from_timestamp(session_file.stat().st_mtime),
    }
    try:
        with session_file.open("r", encoding="utf-8", errors="ignore") as handle:
            for index, line in enumerate(handle):
                if index >= 40:
                    break
                text = line.strip()
                if not text or not text.startswith("{"):
                    continue
                try:
                    payload = json.loads(text)
                except Exception:
                    continue
                if not meta["cwd"] and isinstance(payload.get("cwd"), str):
                    meta["cwd"] = payload["cwd"].strip()
                if not meta["git_branch"] and isinstance(payload.get("gitBranch"), str):
                    meta["git_branch"] = payload["gitBranch"].strip()
                if meta["cwd"] and meta["git_branch"]:
                    break
    except Exception:
        pass
    return meta


def _discover_recent_claude_projects() -> list[dict[str, Any]]:
    projects_dir = CLAUDE_HOME / "projects"
    if not projects_dir.exists() or not projects_dir.is_dir():
        return []

    collected: dict[str, dict[str, Any]] = {}
    for folder in projects_dir.iterdir():
        if not folder.is_dir():
            continue
        session_files = sorted(
            folder.glob("*.jsonl"),
            key=lambda item: item.stat().st_mtime,
            reverse=True,
        )
        if not session_files:
            continue
        meta = _load_session_meta(session_files[0])
        cwd = str(meta.get("cwd") or "").strip()
        path = _normalize_path(cwd)
        if not path:
            continue
        key = _path_key(path)
        current = collected.get(key)
        if current and (current.get("last_active_at") or "") >= (meta.get("last_active_at") or ""):
            continue
        collected[key] = {
            "path": path,
            "source": "claude_projects",
            "last_active_at": meta.get("last_active_at"),
            "git_branch": meta.get("git_branch") or "",
        }

    return sorted(
        collected.values(),
        key=lambda item: item.get("last_active_at") or "",
        reverse=True,
    )[:80]


def _list_top_level_dirs(path: Path, limit: int = 6) -> list[str]:
    names: list[str] = []
    try:
        for child in sorted(path.iterdir(), key=lambda item: item.name.lower()):
            if not child.is_dir():
                continue
            if child.name.startswith(".") or child.name in SKIP_CHILD_DIRS:
                continue
            names.append(child.name)
            if len(names) >= limit:
                break
    except Exception:
        return []
    return names


def _marker_files(path: Path) -> list[str]:
    found: list[str] = []
    for filename in PROJECT_MARKERS:
        if (path / filename).exists():
            found.append(filename)
    return found


def _stack_labels(marker_files: list[str]) -> list[str]:
    labels: list[str] = []
    for filename in marker_files:
        label = PROJECT_MARKERS.get(filename)
        if label and label not in labels:
            labels.append(label)
    return labels


def _has_source_dirs(path: Path) -> bool:
    for dirname in ("src", "app", "apps", "backend", "frontend", "services", "cmd"):
        if (path / dirname).exists():
            return True
    return False


def _is_strong_project(path: Path, marker_files: list[str] | None = None) -> bool:
    markers = marker_files if marker_files is not None else _marker_files(path)
    return (path / ".git").exists() or any(item in STRONG_PROJECT_MARKERS for item in markers)


def _looks_like_project(path: Path, marker_files: list[str] | None = None) -> bool:
    markers = marker_files if marker_files is not None else _marker_files(path)
    return _is_strong_project(path, markers) or _has_source_dirs(path)


def _command_hints(marker_files: list[str]) -> list[str]:
    hints: list[str] = []
    marker_set = set(marker_files)
    if "package.json" in marker_set:
        hints.extend(["npm install", "npm run dev", "npm run build"])
    if any(item in marker_set for item in {"requirements.txt", "pyproject.toml", "Pipfile", "main.py"}):
        hints.extend(["pip install -r requirements.txt", "python main.py"])
    if "pom.xml" in marker_set:
        hints.extend(["mvn test", "mvn package"])
    if "build.gradle" in marker_set or "build.gradle.kts" in marker_set:
        hints.extend(["./gradlew test", "./gradlew build"])
    if "go.mod" in marker_set:
        hints.extend(["go test ./...", "go run ."])
    if "Cargo.toml" in marker_set:
        hints.extend(["cargo test", "cargo run"])

    unique: list[str] = []
    seen: set[str] = set()
    for hint in hints:
        if hint in seen:
            continue
        seen.add(hint)
        unique.append(hint)
    return unique[:4]


def _build_project_summary(
    path: Path,
    source: str,
    last_active_at: str | None = None,
    git_branch: str = "",
    active: bool = False,
) -> dict[str, Any] | None:
    if not _path_exists(path) or not path.is_dir():
        return None

    marker_files = _marker_files(path)
    top_level_dirs = _list_top_level_dirs(path)
    stacks = _stack_labels(marker_files)
    has_git = (path / ".git").exists()

    label_parts: list[str] = []
    if stacks:
        label_parts.extend(stacks[:3])
    elif has_git:
        label_parts.append("Git")
    if has_git and "Git" not in label_parts:
        label_parts.append("Git")

    summary = " · ".join(label_parts or ["Workspace"])
    if marker_files:
        summary = f"{summary} · {', '.join(marker_files[:3])}"

    return {
        "id": re.sub(r"[^a-z0-9]+", "-", str(path).lower()).strip("-")[:120] or "workspace",
        "name": path.name or str(path),
        "path": str(path),
        "source": source,
        "last_active_at": last_active_at,
        "git_branch": git_branch,
        "active": active,
        "has_git": has_git,
        "marker_files": marker_files,
        "stack_labels": stacks,
        "top_level_dirs": top_level_dirs,
        "summary": summary,
        "command_hints": _command_hints(marker_files),
        "quick_prompts": [
            "扫描这个项目的目录结构并总结模块职责",
            "识别启动方式、依赖安装命令和关键配置文件",
            "阅读 README 和主要入口文件，给出开发接手建议",
        ],
    }


def _scan_child_projects(root: Path, source: str) -> list[dict[str, Any]]:
    root_name = root.name.strip().lower()
    if not _path_exists(root) or not root.is_dir():
        return []
    try:
        if root.resolve() == Path.home().resolve():
            return []
    except Exception:
        pass
    if root_name in SKIP_SCAN_ROOT_NAMES:
        return []

    try:
        children = [item for item in root.iterdir() if item.is_dir()]
    except Exception:
        return []
    if len(children) > 80:
        return []

    results: list[dict[str, Any]] = []
    for child in children:
        if child.name.startswith(".") or child.name in SKIP_CHILD_DIRS:
            continue
        marker_files = _marker_files(child)
        if not _is_strong_project(child, marker_files):
            continue
        project = _build_project_summary(child, source=source)
        if project:
            results.append(project)
    return results


def discover_claude_workspaces(config_home_dir: str = "") -> dict[str, Any]:
    explicit_roots: list[dict[str, Any]] = []
    root_candidates: list[Path] = []
    settings_sources: list[str] = []

    for settings_file in SETTINGS_FILES:
        payload = _safe_read_json(settings_file)
        if payload is None:
            continue
        settings_sources.append(str(settings_file))
        for path in _extract_paths_from_settings(payload):
            root_candidates.append(path)
            explicit_roots.append(
                {
                    "path": str(path),
                    "source": f"settings:{settings_file.name}",
                    "exists": path.exists(),
                }
            )

    recent_projects = _discover_recent_claude_projects()
    configured_home = _normalize_path(config_home_dir) if config_home_dir else None

    project_map: dict[str, dict[str, Any]] = {}

    def add_project(
        path: Path,
        source: str,
        last_active_at: str | None = None,
        git_branch: str = "",
        active: bool = False,
    ) -> None:
        if source in {"claude_settings_root", "claude_root_scan"} and not _is_strong_project(path):
            return
        if source not in {"agent_config", "current_repo"} and not _looks_like_project(path):
            return
        project = _build_project_summary(
            path=path,
            source=source,
            last_active_at=last_active_at,
            git_branch=git_branch,
            active=active,
        )
        if not project:
            return
        key = _path_key(path)
        current = project_map.get(key)
        if current:
            current_sources = {item.strip() for item in str(current.get("source") or "").split(",") if item.strip()}
            current_sources.add(source)
            current["source"] = ", ".join(sorted(current_sources))
            if active:
                current["active"] = True
            if last_active_at and (current.get("last_active_at") or "") < last_active_at:
                current["last_active_at"] = last_active_at
            if git_branch and not current.get("git_branch"):
                current["git_branch"] = git_branch
            return
        project_map[key] = project

    add_project(REPO_ROOT, source="current_repo", active=not config_home_dir)

    if configured_home:
        add_project(configured_home, source="agent_config", active=True)

    for item in recent_projects:
        add_project(
            path=item["path"],
            source=item["source"],
            last_active_at=item.get("last_active_at"),
            git_branch=item.get("git_branch") or "",
            active=configured_home is not None and _path_key(item["path"]) == _path_key(configured_home),
        )

    scanned_roots: list[Path] = []
    for root in _unique_paths(root_candidates):
        scanned_roots.append(root)
        if _looks_like_project(root):
            add_project(root, source="claude_settings_root")
            continue
        for project in _scan_child_projects(root, source="claude_root_scan"):
            key = _path_key(project["path"])
            if key not in project_map:
                project_map[key] = project

    if configured_home and configured_home.exists():
        active_key = _path_key(configured_home)
        if active_key in project_map:
            project_map[active_key]["active"] = True

    def _project_sort_key(item: dict[str, Any]) -> tuple[Any, ...]:
        last_active = str(item.get("last_active_at") or "")
        try:
            last_active_rank = -datetime.fromisoformat(last_active).timestamp() if last_active else float("inf")
        except Exception:
            last_active_rank = float("inf")
        return (
            0 if item.get("active") else 1,
            0 if item.get("has_git") else 1,
            last_active_rank,
            str(item.get("name") or "").lower(),
        )

    projects = sorted(project_map.values(), key=_project_sort_key)

    roots = _unique_paths([*(item["path"] for item in recent_projects), *root_candidates])
    root_items = []
    for root in roots:
        root_items.append(
            {
                "path": str(root),
                "exists": _path_exists(root),
                "looks_like_project": _looks_like_project(root) if _path_exists(root) and root.is_dir() else False,
            }
        )

    selected_path = None
    for item in projects:
        if item.get("active"):
            selected_path = item["path"]
            break
    if not selected_path and projects:
        selected_path = projects[0]["path"]

    return {
        "settings_sources": settings_sources,
        "claude_projects_dir": str(CLAUDE_HOME / "projects"),
        "roots": root_items,
        "projects": projects,
        "selected_path": selected_path,
        "source_summary": {
            "settings_files": len(settings_sources),
            "explicit_roots": len(_unique_paths(root_candidates)),
            "recent_projects": len(recent_projects),
            "projects": len(projects),
        },
    }

"""Offline K8S platform knowledge retrieval backed by local Markdown notes."""

from __future__ import annotations

import logging
import os
import re
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

logger = logging.getLogger(__name__)

_DEFAULT_NOTES_DIR = Path(r"D:\LabNotes\raw\K8S可视化学习平台")
_QUERY_TOKEN_RE = re.compile(r"[A-Za-z0-9_.:/-]{2,}|[\u4e00-\u9fff]{2,}")
_FRONT_MATTER_RE = re.compile(r"^---\s*\n(.*?)\n---\s*\n?", re.S)
_COMMAND_RE = re.compile(
    r"^(kubectl|helm|kubeadm|journalctl|systemctl|crictl|ctr|docker|curl|wget|"
    r"etcdctl|tcpdump|ss|netstat|ip(?:tables|vsadm)?|conntrack|dig|nslookup|ping|"
    r"traceroute|bpftool|cilium|calicoctl|openssl|df|free|top|ps|grep|awk|sed|find)\b",
    re.I,
)
_CASE_KEYWORDS = (
    "故障", "排障", "异常", "错误", "告警", "证据链", "恢复", "止血", "回滚", "验证",
    "pending", "crashloop", "imagepull", "backoff", "probe", "dns", "coredns",
    "ingress", "service", "networkpolicy", "cni", "ebpf", "calico", "cilium",
    "storage", "pvc", "pv", "snapshot", "trace", "prometheus", "logging", "oncall",
)
_FALLBACK_TITLES = (
    "故障排查",
    "Pod 生命周期排障",
    "CLI Observation Basics",
    "Cheatsheet",
    "Terminal Practice",
    "OnCall Response",
)
_STOP_WORDS = {
    "请", "帮我", "帮忙", "分析", "查看", "当前", "最近", "这个", "那个", "一下",
    "一下子", "以及", "或者", "还有", "问题", "情况", "平台", "案例", "命令", "方式",
    "能力", "学习", "增加", "需要", "根源", "根因",
}


@dataclass(frozen=True)
class PlatformNote:
    file_name: str
    section_path: str
    title: str
    source_url: str
    summary: str
    case_clues: tuple[str, ...]
    commands: tuple[str, ...]
    searchable_text: str


def _clean_space(text: str) -> str:
    return re.sub(r"\s+", " ", text or "").strip()


def _dedupe(items: list[str], limit: int) -> tuple[str, ...]:
    seen: set[str] = set()
    result: list[str] = []
    for raw in items:
        item = _clean_space(raw)
        if not item:
            continue
        key = item.lower()
        if key in seen:
            continue
        seen.add(key)
        result.append(item)
        if len(result) >= limit:
            break
    return tuple(result)


def _resolve_notes_dir() -> Path | None:
    configured = os.getenv("AIOPS_PLATFORM_NOTES_DIR", "").strip()
    candidates = [Path(configured)] if configured else []
    candidates.append(_DEFAULT_NOTES_DIR)
    for candidate in candidates:
        if candidate and candidate.exists() and candidate.is_dir():
            return candidate
    return None


def _split_front_matter(text: str) -> tuple[dict[str, str], str]:
    match = _FRONT_MATTER_RE.match(text)
    if not match:
        return {}, text
    meta: dict[str, str] = {}
    for line in match.group(1).splitlines():
        if ":" not in line:
            continue
        key, value = line.split(":", 1)
        meta[key.strip().lower()] = value.strip().strip('"')
    return meta, text[match.end():]


def _extract_section_path(lines: list[str]) -> str:
    for line in lines:
        stripped = line.strip()
        if not stripped:
            continue
        if stripped.startswith("## "):
            break
        if stripped.startswith("关注我|"):
            continue
        if "/" in stripped:
            return stripped
    return ""


def _extract_title(lines: list[str], fallback: str) -> str:
    for line in lines:
        stripped = line.strip()
        if stripped.startswith("## "):
            return stripped[3:].strip()
    return fallback


def _iter_plain_lines(lines: list[str]) -> list[str]:
    plain: list[str] = []
    in_code = False
    for line in lines:
        stripped = line.strip()
        if stripped.startswith("```"):
            in_code = not in_code
            continue
        if in_code:
            continue
        if not stripped:
            plain.append("")
            continue
        if stripped.startswith("<") and stripped.endswith(">"):
            continue
        if stripped.startswith("|") or stripped in {"---", "——"}:
            continue
        plain.append(stripped)
    return plain


def _trim_leading_context(lines: list[str], section_path: str, title: str) -> list[str]:
    title_heading = f"## {title}".strip()
    trimmed: list[str] = []
    for line in lines:
        stripped = line.strip()
        if stripped in {section_path.strip(), title.strip(), title_heading}:
            continue
        trimmed.append(line)
    return trimmed


def _extract_summary(lines: list[str], section_path: str, title: str) -> str:
    paragraphs: list[str] = []
    bucket: list[str] = []
    for line in _iter_plain_lines(_trim_leading_context(lines, section_path, title)):
        if not line:
            if bucket:
                paragraphs.append(_clean_space(" ".join(bucket)))
                bucket = []
            continue
        if line.startswith("#"):
            if bucket:
                paragraphs.append(_clean_space(" ".join(bucket)))
                bucket = []
            continue
        if line in {"1.00", "关键说明", "验收点", "注意事项"}:
            continue
        if "听老师讲课" in line or "知识自测" in line or line.startswith("Q0"):
            continue
        if len(line) <= 4:
            continue
        bucket.append(line)
    if bucket:
        paragraphs.append(_clean_space(" ".join(bucket)))

    picked: list[str] = []
    for para in paragraphs:
        if len(para) < 24:
            continue
        picked.append(para)
        if len(" ".join(picked)) >= 420:
            break
    return _clean_space(" ".join(picked))[:520]


def _extract_case_clues(lines: list[str], section_path: str, title: str) -> tuple[str, ...]:
    clues: list[str] = []
    for raw in _iter_plain_lines(_trim_leading_context(lines, section_path, title)):
        line = raw.strip(" -")
        if not line or len(line) < 12 or len(line) > 180:
            continue
        lower = line.lower()
        if line.startswith("#") or line.startswith("步骤 ") or line.startswith("当前步骤"):
            continue
        if any(keyword in lower for keyword in _CASE_KEYWORDS):
            clues.append(line)
    return _dedupe(clues, limit=12)


def _merge_continued_commands(lines: list[str]) -> list[str]:
    merged: list[str] = []
    buffer = ""
    for raw in lines:
        line = raw.rstrip()
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        if stripped.endswith("\\"):
            buffer += stripped[:-1].rstrip() + " "
            continue
        if buffer:
            stripped = buffer + stripped
            buffer = ""
        merged.append(stripped)
    if buffer:
        merged.append(buffer.strip())
    return merged


def _looks_like_command_line(line: str) -> bool:
    if not _COMMAND_RE.match(line):
        return False
    ascii_chars = sum(1 for ch in line if ord(ch) < 128)
    ascii_ratio = ascii_chars / max(1, len(line))
    has_shell_shape = any(token in line for token in (" ", "/", "-", "=", "|", "$", ":"))
    return ascii_ratio >= 0.68 and has_shell_shape and len(line.strip()) >= 6


def _extract_commands(lines: list[str]) -> tuple[str, ...]:
    commands: list[str] = []
    in_code = False
    block: list[str] = []
    for raw in lines:
        stripped = raw.strip()
        if stripped.startswith("```"):
            if in_code and block:
                for line in _merge_continued_commands(block):
                    if _looks_like_command_line(line):
                        commands.append(line)
                block = []
            in_code = not in_code
            continue
        if in_code:
            block.append(raw)
            continue
        if _looks_like_command_line(stripped):
            commands.append(stripped)
    return _dedupe(commands, limit=24)


def _note_priority(note: PlatformNote) -> int:
    title = f"{note.section_path} {note.title}"
    return sum(1 for key in _FALLBACK_TITLES if key.lower() in title.lower())


def _extract_tokens(query: str) -> list[str]:
    tokens: list[str] = []
    for raw in _QUERY_TOKEN_RE.findall((query or "").lower()):
        token = raw.strip("`'\"")
        if len(token) < 2 or token in _STOP_WORDS:
            continue
        tokens.append(token)
    return list(dict.fromkeys(tokens))[:24]


def _score_note(note: PlatformNote, tokens: list[str]) -> tuple[int, list[str]]:
    if not tokens:
        return _note_priority(note), []

    title_text = f"{note.section_path} {note.title}".lower()
    summary_text = note.summary.lower()
    clue_text = "\n".join(note.case_clues).lower()
    command_text = "\n".join(note.commands).lower()
    score = 0
    matched: list[str] = []
    for token in tokens:
        token_hit = False
        if token in title_text:
            score += 10
            token_hit = True
        if token in clue_text:
            score += 7
            token_hit = True
        if token in summary_text:
            score += 4
            token_hit = True
        if token in command_text:
            score += 3
            token_hit = True
        if token_hit:
            matched.append(token)
    if matched and note.commands:
        score += min(4, len(note.commands) // 3)
    score += _note_priority(note)
    return score, list(dict.fromkeys(matched))


def _parse_note(path: Path) -> PlatformNote:
    meta, body = _split_front_matter(path.read_text(encoding="utf-8"))
    lines = body.splitlines()
    section_path = _extract_section_path(lines)
    title = _extract_title(lines, path.stem)
    summary = _extract_summary(lines, section_path, title)
    case_clues = _extract_case_clues(lines, section_path, title)
    commands = _extract_commands(lines)
    searchable_text = _clean_space(
        " ".join([section_path, title, summary, *case_clues, *commands, meta.get("source", "")])
    ).lower()
    return PlatformNote(
        file_name=path.name,
        section_path=section_path,
        title=title,
        source_url=meta.get("source", ""),
        summary=summary,
        case_clues=case_clues,
        commands=commands,
        searchable_text=searchable_text,
    )


@lru_cache(maxsize=1)
def _load_notes() -> tuple[PlatformNote, ...]:
    source_dir = _resolve_notes_dir()
    if not source_dir:
        logger.warning("[platform_kb] markdown source directory not found")
        return ()

    notes: list[PlatformNote] = []
    for path in sorted(source_dir.glob("*.md")):
        try:
            notes.append(_parse_note(path))
        except Exception as exc:
            logger.warning("[platform_kb] failed to parse %s: %s", path, exc)
    logger.info("[platform_kb] loaded %s notes from %s", len(notes), source_dir)
    return tuple(notes)


def platform_knowledge_status() -> dict[str, str | int | bool]:
    source_dir = _resolve_notes_dir()
    notes = _load_notes()
    return {
        "enabled": bool(source_dir and notes),
        "source_dir": str(source_dir) if source_dir else "",
        "note_count": len(notes),
    }


def search_platform_notes(query: str, limit: int = 4) -> list[dict]:
    notes = _load_notes()
    if not notes:
        return []

    tokens = _extract_tokens(query)
    ranked: list[tuple[int, PlatformNote, list[str]]] = []
    for note in notes:
        score, matched_tokens = _score_note(note, tokens)
        ranked.append((score, note, matched_tokens))

    ranked.sort(
        key=lambda item: (
            item[0],
            len(item[2]),
            len(item[1].commands),
            len(item[1].case_clues),
            len(item[1].summary),
        ),
        reverse=True,
    )

    best_match_count = max((len(item[2]) for item in ranked if item[0] > 0), default=0)
    min_match_count = max(1, best_match_count - 1) if best_match_count >= 3 else 1

    picked: list[dict] = []
    for score, note, matched_tokens in ranked:
        if score <= 0 and picked:
            break
        if score <= 0 and _note_priority(note) == 0:
            continue
        if matched_tokens and len(matched_tokens) < min_match_count and _note_priority(note) == 0:
            continue
        picked.append(
            {
                "score": score,
                "section_path": note.section_path or note.title,
                "title": note.title,
                "summary": note.summary,
                "case_clues": list(note.case_clues[:3]),
                "commands": list(note.commands[:8]),
                "matched_tokens": matched_tokens,
                "source_url": note.source_url,
                "file_name": note.file_name,
            }
        )
        if len(picked) >= max(1, limit):
            break

    if picked:
        return picked

    fallback = sorted(notes, key=_note_priority, reverse=True)[: max(1, limit)]
    return [
        {
            "score": _note_priority(note),
            "section_path": note.section_path or note.title,
            "title": note.title,
            "summary": note.summary,
            "case_clues": list(note.case_clues[:3]),
            "commands": list(note.commands[:8]),
            "matched_tokens": [],
            "source_url": note.source_url,
            "file_name": note.file_name,
        }
        for note in fallback
    ]


def render_platform_guidance(
    query: str,
    limit: int = 4,
    command_limit: int = 6,
    max_chars: int = 2600,
) -> str:
    status = platform_knowledge_status()
    if not status["enabled"]:
        return "（本地 K8S 平台知识库未加载，无法补充平台案例与命令。）"

    matches = search_platform_notes(query, limit=limit)
    if not matches:
        return "（本地 K8S 平台知识库未命中相关专题。）"

    commands: list[str] = []
    seen_commands: set[str] = set()
    for item in matches:
        for cmd in item["commands"]:
            key = cmd.lower()
            if key in seen_commands:
                continue
            seen_commands.add(key)
            commands.append(cmd)
            if len(commands) >= command_limit:
                break
        if len(commands) >= command_limit:
            break

    lines = [
        f"已加载本地 K8S 平台知识库，共 {status['note_count']} 篇 Markdown。",
        "## 平台排障案例",
    ]
    for item in matches:
        clue = item["case_clues"][0] if item["case_clues"] else item["summary"]
        summary = _clean_space(clue or item["summary"])[:180]
        matched = f"（命中：{', '.join(item['matched_tokens'][:4])}）" if item["matched_tokens"] else ""
        lines.append(f"- {item['section_path']}：{summary}{matched}")

    lines.extend(
        [
            "## 命令方式",
        ]
    )
    if commands:
        for idx, cmd in enumerate(commands[:command_limit], 1):
            lines.append(f"{idx}. `{cmd}`")
    else:
        lines.append("1. `kubectl get pods -A -o wide`")
        lines.append("2. `kubectl describe pod <pod-name>`")
        lines.append("3. `kubectl get events --sort-by=.lastTimestamp`")

    lines.extend(
        [
            "## 排障顺序",
            "- 先定义症状与影响范围，再区分单 Pod、单节点、单命名空间还是跨集群问题。",
            "- 先查 `get/describe/events`，再对齐 `logs/metrics/trace`，不要一上来就随机重启或删除资源。",
            "- 修复时一次只改一个关键变量，修复后用 `kubectl wait` 或 `kubectl rollout status` 验证是否真正恢复。",
        ]
    )

    rendered = "\n".join(lines)
    return rendered[:max_chars]

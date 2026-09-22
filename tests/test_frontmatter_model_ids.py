"""Structural test: agent `model:` values — aliases for Claude, pins for Cursor.

FORK DEVIATION (smcinerney-merkle/atelier-pipeline). Upstream requires every
agent under both `source/claude/agents/` and `source/cursor/agents/` to pin an
explicit `claude-*` ID (ADR-0047 Phase 4), so that an Anthropic alias remap
cannot silently move agents off the model their budgets were tuned for.

This fork runs on Bedrock, where the host sets ANTHROPIC_DEFAULT_OPUS_MODEL,
ANTHROPIC_DEFAULT_SONNET_MODEL and ANTHROPIC_DEFAULT_HAIKU_MODEL. There an
alias cannot drift without the operator changing it, and a pin is a second
copy of the model choice that goes stale every release. So the Claude Code
agents here must carry the family ALIAS, and this test is the fork's guard:
an upstream merge that re-pins any of them turns it red.

Cursor has no equivalent host mapping, so `source/cursor/agents/` keeps
upstream's pinned-ID assertion unchanged.
"""

from __future__ import annotations

from pathlib import Path

import pytest

try:
    import yaml  # type: ignore

    _HAS_YAML = True
except ImportError:  # pragma: no cover - fallback path
    _HAS_YAML = False


REPO_ROOT = Path(__file__).resolve().parent.parent
CURSOR_DIR = REPO_ROOT / "source" / "cursor" / "agents"
FRONTMATTER_DIRS = (CURSOR_DIR,)
REQUIRED_PREFIX = "claude-"
GENERIC_ALIASES = {"opus", "sonnet", "haiku"}


def _discover_frontmatter_files() -> list[Path]:
    files: list[Path] = []
    for directory in FRONTMATTER_DIRS:
        files.extend(sorted(directory.glob("*.frontmatter.yml")))
    return files


def _extract_model_field(path: Path) -> str | None:
    """Return the `model` field value, or None if missing.

    Uses PyYAML when available; otherwise falls back to a line-by-line
    scan that matches the project's flat frontmatter format.
    """
    text = path.read_text(encoding="utf-8")
    if _HAS_YAML:
        data = yaml.safe_load(text)
        if not isinstance(data, dict):
            return None
        value = data.get("model")
        return str(value) if value is not None else None
    for line in text.splitlines():
        stripped = line.strip()
        if stripped.startswith("model:"):
            return stripped.split(":", 1)[1].strip()
    return None


FRONTMATTER_FILES = _discover_frontmatter_files()


def test_frontmatter_files_discovered() -> None:
    """Sanity: at least one frontmatter file exists in each tree."""
    assert FRONTMATTER_FILES, (
        f"No *.frontmatter.yml files found under {FRONTMATTER_DIRS!r}; "
        "the test would otherwise pass vacuously."
    )
    for directory in FRONTMATTER_DIRS:
        present = list(directory.glob("*.frontmatter.yml"))
        assert present, f"No frontmatter files under {directory}"


@pytest.mark.parametrize(
    "frontmatter_path",
    FRONTMATTER_FILES,
    ids=[str(p.relative_to(REPO_ROOT)) for p in FRONTMATTER_FILES],
)
def test_model_field_is_explicit_id(frontmatter_path: Path) -> None:
    """`model:` must be an explicit `claude-*` ID, not a generic alias."""
    model = _extract_model_field(frontmatter_path)
    rel = frontmatter_path.relative_to(REPO_ROOT)
    assert model is not None, f"{rel}: missing `model:` field"
    assert model not in GENERIC_ALIASES, (
        f"{rel}: model field is generic alias {model!r}; "
        f"pin an explicit ID starting with {REQUIRED_PREFIX!r} "
        "(see ADR-0047 Phase 4)."
    )
    assert model.startswith(REQUIRED_PREFIX), (
        f"{rel}: model field {model!r} does not start with "
        f"{REQUIRED_PREFIX!r}; pin an explicit Anthropic model ID such as "
        "`claude-opus-4-7`, `claude-sonnet-4-6`, or "
        "`claude-haiku-4-5-20251001` (see ADR-0047 Phase 4)."
    )


# ---------------------------------------------------------------------------
# Claude Code agents: must be aliases (fork deviation, see module docstring).
# Covers the overlay sources AND the plugin's own assembled .claude/agents/.
# ---------------------------------------------------------------------------
CLAUDE_FILES = sorted((REPO_ROOT / "source" / "claude" / "agents").glob("*.frontmatter.yml")) + \
    sorted((REPO_ROOT / ".claude" / "agents").glob("*.md"))


def _frontmatter_model(path: Path) -> str | None:
    """`model:` from a flat frontmatter block, with or without `---` fences."""
    lines = path.read_text(encoding="utf-8").splitlines()
    if lines and lines[0].strip() == "---":
        try:
            lines = lines[1:lines.index("---", 1)]
        except ValueError:
            return None
    for line in lines:
        if line.startswith("model:"):
            return line.split(":", 1)[1].strip()
    return None


def test_claude_files_discovered() -> None:
    assert len(CLAUDE_FILES) >= 28, (
        f"expected source + assembled Claude agents, found {len(CLAUDE_FILES)}"
    )


@pytest.mark.parametrize(
    "agent_path",
    CLAUDE_FILES,
    ids=[str(p.relative_to(REPO_ROOT)) for p in CLAUDE_FILES],
)
def test_claude_model_field_is_alias(agent_path: Path) -> None:
    """Claude Code agents follow the host's ANTHROPIC_DEFAULT_*_MODEL mapping."""
    model = _frontmatter_model(agent_path)
    rel = agent_path.relative_to(REPO_ROOT)
    assert model is not None, f"{rel}: missing `model:` field"
    assert model in GENERIC_ALIASES, (
        f"{rel}: model field {model!r} is pinned; this fork requires one of "
        f"{sorted(GENERIC_ALIASES)} so the host settings decide the model. "
        "An upstream merge probably re-pinned it."
    )


@pytest.mark.parametrize(
    "agent_path",
    CLAUDE_FILES[: len(CLAUDE_FILES) // 2],
    ids=[p.stem.replace(".frontmatter", "") for p in CLAUDE_FILES[: len(CLAUDE_FILES) // 2]],
)
def test_assembled_agent_matches_its_source(agent_path: Path) -> None:
    """The assembled .claude/agents copy carries the same alias as its source."""
    name = agent_path.name.replace(".frontmatter.yml", "")
    assembled = REPO_ROOT / ".claude" / "agents" / f"{name}.md"
    if not assembled.exists():
        pytest.skip(f"no assembled copy for {name}")
    assert _frontmatter_model(assembled) == _frontmatter_model(agent_path)

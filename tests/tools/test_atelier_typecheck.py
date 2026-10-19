"""The atelier render path type-checks a composition before bundling it.

Remotion bundles with esbuild, which strips TypeScript types without checking
them. Without this gate a composition that reads a token that does not exist
renders `undefined` silently. These tests drive the real compiler shipped in
remotion-composer against tiny fixture entries, one clean and one broken.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from tools.video.video_compose import VideoCompose

COMPOSER = Path(__file__).resolve().parents[2] / "remotion-composer"

pytestmark = pytest.mark.skipif(
    not (COMPOSER / "node_modules" / ".bin" / "tsc").exists(),
    reason="remotion-composer dependencies are not installed",
)

TOKENS = 'export const T = {body: 24, h3: 38} as const;\n'

ENTRY_TEMPLATE = """\
import React from "react";
import {{AbsoluteFill}} from "remotion";
import {{T}} from "./tokens";

export type SceneProps = {{title: string}};

export const Scene: React.FC<SceneProps> = ({{title}}) => (
  <AbsoluteFill>
    <div style={{{{fontSize: T.{step}}}}}>{{title}}</div>
  </AbsoluteFill>
);
"""


def _write_entry(root: Path, step: str) -> Path:
    project = root / "fixture"
    project.mkdir()
    (project / "tokens.ts").write_text(TOKENS, encoding="utf-8")
    entry = project / "Composition.tsx"
    entry.write_text(ENTRY_TEMPLATE.format(step=step), encoding="utf-8")
    return entry


def test_clean_composition_passes(tmp_path: Path) -> None:
    entry = _write_entry(tmp_path, "h3")
    assert VideoCompose()._typecheck_atelier_entry(entry, COMPOSER) is None


def test_dangling_token_blocks_the_render(tmp_path: Path) -> None:
    """Regression: `T.quoteOrH3` bundled cleanly and rendered at a fallback size."""
    entry = _write_entry(tmp_path, "quoteOrH3")
    result = VideoCompose()._typecheck_atelier_entry(entry, COMPOSER)
    assert result is not None and not result.success
    assert "quoteOrH3" in result.error
    assert "refusing to render" in result.error


def test_typecheck_leaves_the_project_tree_untouched(tmp_path: Path) -> None:
    entry = _write_entry(tmp_path, "h3")
    before = sorted(p.name for p in entry.parent.iterdir())
    VideoCompose()._typecheck_atelier_entry(entry, COMPOSER)
    assert sorted(p.name for p in entry.parent.iterdir()) == before

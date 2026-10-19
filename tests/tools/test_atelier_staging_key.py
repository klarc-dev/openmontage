"""Atelier projects stage into a collision-free directory under the composer.

The staging key used to be the first segment under ``projects/``, so every
project of a nested layout (``projects/<group>/<topic>``) staged into the same
``remotion-composer/projects/<group>/`` and concurrent renders overwrote each
other's sources.
"""

from __future__ import annotations

from pathlib import Path

from tools.video.video_compose import VideoCompose


def _project(root: Path, *parts: str) -> Path:
    d = root.joinpath("projects", *parts)
    d.mkdir(parents=True)
    (d / "index.tsx").write_text(f"export const ID = {'/'.join(parts)!r};\n", encoding="utf-8")
    return d / "index.tsx"


def test_nested_projects_stage_to_distinct_dirs(tmp_path):
    composer = tmp_path / "remotion-composer"
    composer.mkdir()
    a = _project(tmp_path, "group", "series-a", "topic")
    b = _project(tmp_path, "group", "series-b", "topic")

    tool = VideoCompose()
    staged_a = tool._stage_atelier_project(a, composer)
    staged_b = tool._stage_atelier_project(b, composer)

    assert staged_a.parent != staged_b.parent
    assert staged_a.read_text(encoding="utf-8") != staged_b.read_text(encoding="utf-8")
    assert staged_a.parent.parent == composer / "projects"


def test_staging_key_is_stable_and_readable(tmp_path):
    entry = _project(tmp_path, "group", "series", "my-topic")
    first = VideoCompose._atelier_staging_key(entry.parent)
    second = VideoCompose._atelier_staging_key(entry.parent)

    assert first == second
    assert first.startswith("series-my-topic-")
    assert len(first.rsplit("-", 1)[1]) == 10


def test_staging_key_without_projects_ancestor(tmp_path):
    d = tmp_path / "elsewhere" / "demo"
    d.mkdir(parents=True)
    key = VideoCompose._atelier_staging_key(d)
    assert key.startswith("demo-")

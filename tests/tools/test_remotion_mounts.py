"""OPENMONTAGE_REMOTION_MOUNTS copies shared composition source into the composer.

A brand kit or component library that lives outside this repository is
mounted at remotion-composer/src/<name>/ so atelier compositions import it as
`../../src/<name>`, without editing composer source.
"""

from __future__ import annotations

import os
from pathlib import Path

import pytest

from tools.video.video_compose import VideoCompose


@pytest.fixture
def composer(tmp_path: Path) -> Path:
    root = tmp_path / "remotion-composer"
    (root / "src" / "components").mkdir(parents=True)
    (root / "src" / "Explainer.tsx").write_text("export {};\n", encoding="utf-8")
    return root


def _kit(tmp_path: Path, name: str = "kit") -> Path:
    kit = tmp_path / name
    (kit / "short").mkdir(parents=True)
    (kit / "index.tsx").write_text("export const A = 1;\n", encoding="utf-8")
    (kit / "short" / "geometry.ts").write_text("export const B = 2;\n", encoding="utf-8")
    (kit / "notes.md").write_text("not source\n", encoding="utf-8")
    return kit


def test_unset_variable_mounts_nothing(composer, monkeypatch):
    monkeypatch.delenv("OPENMONTAGE_REMOTION_MOUNTS", raising=False)
    assert VideoCompose()._stage_remotion_mounts(composer) == []


def test_mount_copies_source_files_and_marks_the_copy(composer, tmp_path, monkeypatch):
    kit = _kit(tmp_path)
    monkeypatch.setenv("OPENMONTAGE_REMOTION_MOUNTS", f"brand-kit={kit}")

    (dest,) = VideoCompose()._stage_remotion_mounts(composer)

    assert dest == composer / "src" / "brand-kit"
    assert (dest / "index.tsx").read_text(encoding="utf-8") == "export const A = 1;\n"
    assert (dest / "short" / "geometry.ts").exists()
    assert not (dest / "notes.md").exists()
    assert (dest / ".openmontage-mount").read_text(encoding="utf-8").strip() == str(kit.resolve())


def test_files_removed_from_the_source_are_pruned(composer, tmp_path, monkeypatch):
    kit = _kit(tmp_path)
    monkeypatch.setenv("OPENMONTAGE_REMOTION_MOUNTS", f"brand-kit={kit}")
    tool = VideoCompose()
    tool._stage_remotion_mounts(composer)

    (kit / "short" / "geometry.ts").unlink()
    tool._stage_remotion_mounts(composer)

    assert not (composer / "src" / "brand-kit" / "short" / "geometry.ts").exists()
    assert (composer / "src" / "brand-kit" / "index.tsx").exists()


def test_several_mounts_use_the_path_separator(composer, tmp_path, monkeypatch):
    a, b = _kit(tmp_path, "a"), _kit(tmp_path, "b")
    monkeypatch.setenv("OPENMONTAGE_REMOTION_MOUNTS", os.pathsep.join([f"kit-a={a}", f"kit-b={b}"]))

    mounted = VideoCompose()._stage_remotion_mounts(composer)

    assert [p.name for p in mounted] == ["kit-a", "kit-b"]


@pytest.mark.parametrize("name", ["components", "Explainer"])
def test_names_that_collide_with_composer_source_are_refused(composer, tmp_path, monkeypatch, name):
    monkeypatch.setenv("OPENMONTAGE_REMOTION_MOUNTS", f"{name}={_kit(tmp_path)}")
    with pytest.raises(ValueError, match="collides"):
        VideoCompose()._stage_remotion_mounts(composer)
    # Composer source is untouched.
    assert (composer / "src" / "Explainer.tsx").read_text(encoding="utf-8") == "export {};\n"


@pytest.mark.parametrize("value", ["no-equals", "=/tmp", "../escape=/tmp", "ok=/does/not/exist"])
def test_malformed_entries_are_refused(composer, monkeypatch, value):
    monkeypatch.setenv("OPENMONTAGE_REMOTION_MOUNTS", value)
    with pytest.raises(ValueError):
        VideoCompose()._stage_remotion_mounts(composer)

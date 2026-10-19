"""Workspace roots in lib.paths: defaults and environment overrides."""

from __future__ import annotations

import importlib
import os
import shutil
from pathlib import Path

import pytest

import lib.paths

ROOT_VARS = (
    "OPENMONTAGE_PROJECTS_DIR",
    "OPENMONTAGE_CONFIG",
    "OPENMONTAGE_ENV_FILE",
    "OPENMONTAGE_STYLES_PATH",
    "OPENMONTAGE_PIPELINE_DIRS",
    "OPENMONTAGE_WORK_DIR",
    "OPENMONTAGE_MUSIC_LIBRARY_DIR",
)


@pytest.fixture
def paths(monkeypatch):
    """Reload lib.paths under a clean environment; restore it afterwards."""
    for var in ROOT_VARS:
        monkeypatch.delenv(var, raising=False)

    def reload():
        return importlib.reload(lib.paths)

    yield reload
    # Restore the caller's environment first, then reload, so later tests see
    # the roots the session started with (not a stripped environment).
    monkeypatch.undo()
    importlib.reload(lib.paths)


def test_defaults_are_the_source_checkout(paths):
    p = paths()
    home = Path(p.__file__).resolve().parent.parent
    assert p.OPENMONTAGE_HOME == p.REPO_ROOT == home
    assert p.PROJECTS_DIR == home / "projects"
    assert p.CONFIG_PATH == home / "config.yaml"
    assert p.ENV_FILE == home / ".env"
    assert p.STYLES_PATH == [] and p.PIPELINE_DIRS == []
    assert p.style_dirs() == [home / "styles"]
    assert p.pipeline_dirs() == [home / "pipeline_defs"]
    assert p.WORK_DIR == home
    assert p.MUSIC_LIBRARY_DIR == home / "music_library"


def test_every_root_is_overridable(paths, monkeypatch, tmp_path):
    styles_a, styles_b = tmp_path / "sa", tmp_path / "sb"
    monkeypatch.setenv("OPENMONTAGE_PROJECTS_DIR", str(tmp_path / "projects"))
    monkeypatch.setenv("OPENMONTAGE_CONFIG", str(tmp_path / "c.yaml"))
    monkeypatch.setenv("OPENMONTAGE_ENV_FILE", str(tmp_path / "e.env"))
    monkeypatch.setenv("OPENMONTAGE_STYLES_PATH", os.pathsep.join([str(styles_a), "", str(styles_b)]))
    monkeypatch.setenv("OPENMONTAGE_PIPELINE_DIRS", str(tmp_path / "pipes"))
    monkeypatch.setenv("OPENMONTAGE_WORK_DIR", str(tmp_path / "work"))
    monkeypatch.setenv("OPENMONTAGE_MUSIC_LIBRARY_DIR", str(tmp_path / "music"))
    p = paths()
    assert p.PROJECTS_DIR == tmp_path / "projects"
    assert p.CONFIG_PATH == tmp_path / "c.yaml"
    assert p.ENV_FILE == tmp_path / "e.env"
    assert p.STYLES_PATH == [styles_a, styles_b]  # empty entries ignored
    assert p.style_dirs() == [styles_a, styles_b, p.REPO_ROOT / "styles"]
    assert p.pipeline_dirs() == [tmp_path / "pipes", p.REPO_ROOT / "pipeline_defs"]
    assert p.WORK_DIR == tmp_path / "work"
    assert p.MUSIC_LIBRARY_DIR == tmp_path / "music"
    assert p.OPENMONTAGE_HOME == Path(p.__file__).resolve().parent.parent


def test_config_load_uses_configured_path(paths, monkeypatch, tmp_path):
    cfg = tmp_path / "config.yaml"
    cfg.write_text("budget:\n  total_usd: 1.25\n", encoding="utf-8")
    monkeypatch.setenv("OPENMONTAGE_CONFIG", str(cfg))
    paths()
    from lib.config_model import OpenMontageConfig

    assert OpenMontageConfig.load().budget.total_usd == 1.25
    assert OpenMontageConfig.load(tmp_path / "missing.yaml").budget.total_usd == OpenMontageConfig().budget.total_usd


def test_env_file_loaders_use_configured_path(paths, monkeypatch, tmp_path):
    env = tmp_path / "workspace.env"
    env.write_text("OM_TEST_ROOTS_KEY=from-workspace\n", encoding="utf-8")
    monkeypatch.setenv("OPENMONTAGE_ENV_FILE", str(env))
    monkeypatch.delenv("OM_TEST_ROOTS_KEY", raising=False)
    paths()
    from tools.tool_registry import ToolRegistry

    ToolRegistry._load_dotenv()
    assert os.environ.get("OM_TEST_ROOTS_KEY") == "from-workspace"

    monkeypatch.delenv("OM_TEST_ROOTS_KEY", raising=False)
    from tools import base_tool

    base_tool._load_dotenv()
    assert os.environ.get("OM_TEST_ROOTS_KEY") == "from-workspace"

    monkeypatch.delenv("OM_TEST_ROOTS_KEY", raising=False)
    from lib.env_loader import load_env

    load_env()
    assert os.environ.get("OM_TEST_ROOTS_KEY") == "from-workspace"
    monkeypatch.delenv("OM_TEST_ROOTS_KEY", raising=False)


def test_external_styles_are_searched_first(paths, monkeypatch, tmp_path):
    from styles import playbook_loader

    builtin = sorted(playbook_loader.STYLES_DIR.glob("*.yaml"))[0]
    external = tmp_path / "styles"
    (external / "custom").mkdir(parents=True)
    shutil.copy(builtin, external / "workspace-only.yaml")
    shutil.copy(builtin, external / "custom" / "generated-only.yaml")
    shutil.copy(builtin, external / builtin.name)  # shadows the built-in name
    monkeypatch.setenv("OPENMONTAGE_STYLES_PATH", str(external))
    paths()

    assert playbook_loader.find_playbook("workspace-only") == external / "workspace-only.yaml"
    assert playbook_loader.find_playbook("generated-only") == external / "custom" / "generated-only.yaml"
    assert playbook_loader.find_playbook(builtin.stem) == external / builtin.name
    names = playbook_loader.list_playbooks()
    assert {"workspace-only", "generated-only", builtin.stem} <= set(names)
    assert playbook_loader.load_playbook("workspace-only")

    from lib import playbook_generator

    assert playbook_generator.load_existing_playbook("workspace-only")
    assert "generated-only" in playbook_generator.list_playbooks()
    assert playbook_generator._custom_styles_dir() == external / "custom"

    # An explicit styles_dir is searched alone.
    with pytest.raises(FileNotFoundError):
        playbook_loader.find_playbook("workspace-only", styles_dir=playbook_loader.STYLES_DIR)


def test_builtin_styles_unchanged_without_env(paths):
    paths()
    from lib import playbook_generator
    from styles import playbook_loader

    builtin = sorted(playbook_loader.STYLES_DIR.glob("*.yaml"))[0]
    assert playbook_loader.find_playbook(builtin.stem) == builtin
    assert playbook_generator._custom_styles_dir() == playbook_generator.CUSTOM_STYLES_DIR


def test_external_pipeline_dirs_are_searched_first(paths, monkeypatch, tmp_path):
    from lib import pipeline_loader

    builtin = sorted(pipeline_loader.PIPELINE_DEFS_DIR.glob("*.yaml"))[0]
    extra = tmp_path / "pipes"
    extra.mkdir()
    shutil.copy(builtin, extra / "workspace-pipeline.yaml")
    monkeypatch.setenv("OPENMONTAGE_PIPELINE_DIRS", str(extra))
    paths()

    assert pipeline_loader.load_pipeline("workspace-pipeline")
    assert pipeline_loader.load_pipeline(builtin.stem)
    names = pipeline_loader.list_pipelines()
    assert "workspace-pipeline" in names and builtin.stem in names
    assert len(names) == len(set(names))
    with pytest.raises(FileNotFoundError):
        pipeline_loader.load_pipeline("does-not-exist-anywhere")


def test_music_library_follows_root(paths, monkeypatch, tmp_path):
    monkeypatch.setenv("OPENMONTAGE_MUSIC_LIBRARY_DIR", str(tmp_path / "music"))
    monkeypatch.delenv("MUSIC_LIBRARY_DIR", raising=False)
    paths()
    from tools.audio.music_library import MusicLibrary

    assert MusicLibrary()._library_dir() == tmp_path / "music"
    monkeypatch.setenv("MUSIC_LIBRARY_DIR", str(tmp_path / "legacy"))
    assert MusicLibrary()._library_dir() == tmp_path / "legacy"


def test_runtime_caches_follow_work_dir(paths, monkeypatch, tmp_path):
    monkeypatch.setenv("OPENMONTAGE_WORK_DIR", str(tmp_path / "work"))
    paths()
    pytest.importorskip("fastapi")
    import backlot.server
    import tools.graphics.blender_world as blender_world

    try:
        server = importlib.reload(backlot.server)
        assert server.THUMB_CACHE_DIR == tmp_path / "work" / ".backlot" / "thumbs"
        blender = importlib.reload(blender_world)
        assert blender._PORTABLE_BLENDER.is_relative_to(tmp_path / "work" / ".runtime")
    finally:
        monkeypatch.delenv("OPENMONTAGE_WORK_DIR")
        importlib.reload(lib.paths)
        importlib.reload(backlot.server)
        importlib.reload(blender_world)

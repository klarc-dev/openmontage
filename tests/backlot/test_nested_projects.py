"""Grouped project layouts: projects/<group>/[<series>/]<project>/ appear in the library."""
from __future__ import annotations

import json

import pytest

from backlot.state import (
    discover_project_dirs,
    list_projects,
    load_board_state,
    project_dir_for,
    project_id_for,
)


def _project(path, title):
    path.mkdir(parents=True)
    (path / "project.json").write_text(json.dumps({"project_id": path.name, "title": title}))
    return path


def test_flat_projects_keep_their_ids(tmp_path):
    flat = _project(tmp_path / "demo", "Demo")
    unmarked = tmp_path / "scratch-run"
    unmarked.mkdir()
    assert discover_project_dirs(tmp_path) == [flat, unmarked]
    assert project_id_for(flat, tmp_path) == "demo"


def test_grouping_dirs_are_expanded(tmp_path):
    a = _project(tmp_path / "generated" / "series" / "topic-a", "A")
    b = _project(tmp_path / "generated" / "series" / "topic-b", "B")
    w = _project(tmp_path / "webinars" / "talk", "Talk")
    _project(tmp_path / "generated" / "series" / "topic-a" / "archive" / "old", "nested in a project")
    found = discover_project_dirs(tmp_path)
    assert found == [a, b, w]
    ids = [project_id_for(p, tmp_path) for p in found]
    assert ids == ["generated~series~topic-a", "generated~series~topic-b", "webinars~talk"]
    assert [s["project_id"] for s in sorted(list_projects(tmp_path), key=lambda s: s["project_id"])] == ids


def test_id_round_trip_and_safety(tmp_path):
    a = _project(tmp_path / "generated" / "series" / "topic-a", "A")
    assert project_dir_for("generated~series~topic-a", tmp_path) == a
    for bad in ("", "..", "a/b", "a\\b", "C:", "a~..~b", "a~~b", "a~b~c~d"):
        assert project_dir_for(bad, tmp_path) is None


def test_board_state_uses_the_nested_id(tmp_path, monkeypatch):
    import backlot.state as state
    monkeypatch.setattr(state, "PROJECTS_DIR", tmp_path)
    a = _project(tmp_path / "generated" / "series" / "topic-a", "A")
    assert load_board_state(a)["project_id"] == "generated~series~topic-a"


from tests.backlot.test_server import client, projects_root  # noqa: E402,F401  (fixtures)
from backlot import server as server_mod  # noqa: E402


def test_api_serves_nested_projects(client, projects_root):
    _project(projects_root / "generated" / "series" / "topic-a", "Topic A")
    _project(projects_root / "flat", "Flat")
    ids = sorted(p["project_id"] for p in client.get("/api/projects").json())
    assert ids == ["flat", "generated~series~topic-a"]
    state = client.get("/api/project/generated~series~topic-a/state").json()
    assert state["project_id"] == "generated~series~topic-a" and state["title"] == "Topic A"
    assert client.get("/api/project/generated~..~x/state").status_code == 400
    assert client.get("/api/project/generated~series~missing/state").status_code == 404


def test_changes_map_to_the_nested_project(client, projects_root):
    _project(projects_root / "generated" / "series" / "topic-a", "Topic A")
    client.get("/api/projects")  # refreshes the nested-id index
    changed = projects_root / "generated" / "series" / "topic-a" / "renders" / "x.mp4"
    assert server_mod._project_of_change(str(changed)) == "generated~series~topic-a"
    assert server_mod._project_of_change(str(projects_root / "flat" / "a.json")) == "flat"

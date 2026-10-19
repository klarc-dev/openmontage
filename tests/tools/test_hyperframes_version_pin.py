"""OPENMONTAGE_HYPERFRAMES_VERSION pins the npx package spec."""
from tools.video.hyperframes_compose import HyperFramesCompose


def test_unpinned_by_default(monkeypatch):
    monkeypatch.delenv("OPENMONTAGE_HYPERFRAMES_VERSION", raising=False)
    assert HyperFramesCompose._npx_spec() == "hyperframes"


def test_version_pin(monkeypatch):
    monkeypatch.setenv("OPENMONTAGE_HYPERFRAMES_VERSION", " 0.8.174 ")
    assert HyperFramesCompose._npx_spec() == "hyperframes@0.8.174"

"""The Remotion theme must be derived from the playbook's real schema keys.

`VideoCompose._build_theme_from_playbook` says it reads "a playbook's actual
color values [...] not picked from a preset menu", but it read three keys the
playbook schema does not define, so each silently fell back to a hardcoded
default for every playbook:

    typo.get("heading")        schema key is `headings`
    palette.get("muted_text")  schema key is `muted`
    motion.get("pace")         `pace` is an identity field, not a motion one

Expectations come from the playbook YAML rather than a hardcoded table, so a
playbook that changes its typeface keeps this honest.

This is the Remotion counterpart of the HyperFrames style-bridge defect in
issue #306; that bridge lives in lib/hyperframes_style_bridge.py and is not
touched here.
"""

from pathlib import Path

import pytest
import yaml

from styles.playbook_loader import find_playbook, list_playbooks
from tools.video.video_compose import VideoCompose

REPO_ROOT = Path(__file__).resolve().parents[2]
STYLES_DIR = REPO_ROOT / "styles"

PLAYBOOK_NAMES = sorted(list_playbooks())


def _raw(name: str) -> dict:
    # Resolve like the loader does: playbooks may come from OPENMONTAGE_STYLES_PATH.
    return yaml.safe_load(find_playbook(name).read_text(encoding="utf-8"))


def _theme(name: str) -> dict:
    theme = VideoCompose()._build_theme_from_playbook(name, {})
    if not theme:
        pytest.skip(f"{name} does not currently yield a theme")
    return theme


@pytest.mark.parametrize("name", PLAYBOOK_NAMES)
def test_heading_font_comes_from_the_playbook(name: str) -> None:
    """Regression: read from `heading`, so every playbook rendered in Inter."""
    expected = _raw(name)["typography"]["headings"]["font"]
    assert _theme(name)["headingFont"] == expected


@pytest.mark.parametrize("name", PLAYBOOK_NAMES)
def test_muted_text_color_comes_from_the_playbook(name: str) -> None:
    """Regression: read from `muted_text`, so this was always #6B7280."""
    palette = _raw(name)["visual_language"]["color_palette"]
    if "muted" not in palette:
        pytest.skip(f"{name} declares no muted color")
    assert _theme(name)["mutedTextColor"] == palette["muted"]


def test_identity_pace_drives_the_motion_feel() -> None:
    """Regression: read `pace` off motion, where the schema has no such key,
    so the spring never left its moderate default."""
    fast = [n for n in PLAYBOOK_NAMES if _raw(n)["identity"]["pace"] == "fast"]
    if not fast:
        pytest.skip("no playbook declares a fast pace")

    moderate_default = {"damping": 20, "stiffness": 120, "mass": 1}
    for name in fast:
        theme = _theme(name)
        assert theme["springConfig"] != moderate_default, (
            f"{name} declares pace=fast but still got the moderate spring"
        )
        assert theme["transitionDuration"] < 0.4


@pytest.mark.parametrize("name", PLAYBOOK_NAMES)
def test_derived_theme_only_reads_documented_palette_keys(name: str) -> None:
    """The derived colors must be values the playbook can actually express."""
    palette = _raw(name)["visual_language"]["color_palette"]
    theme = _theme(name)

    primary = palette["primary"]
    accent = palette["accent"]
    assert theme["primaryColor"] == (primary[0] if isinstance(primary, list) else primary)
    assert theme["accentColor"] == (accent[0] if isinstance(accent, list) else accent)
    assert theme["backgroundColor"] == palette["background"]
    assert theme["textColor"] == palette["text"]


@pytest.mark.parametrize("name", PLAYBOOK_NAMES)
def test_body_and_mono_fonts_come_from_the_playbook(name: str) -> None:
    typography = _raw(name)["typography"]
    theme = _theme(name)
    assert theme["bodyFont"] == typography["body"]["font"]
    if "code" in typography:
        assert theme["monoFont"] == typography["code"]["font"]


@pytest.mark.parametrize("name", PLAYBOOK_NAMES)
def test_chart_colors_prefer_the_declared_chart_palette(name: str) -> None:
    declared = _raw(name).get("chart_palette") or []
    if len(declared) < 3:
        pytest.skip(f"{name} declares no chart palette")
    assert _theme(name)["chartColors"] == declared[:6]


@pytest.mark.parametrize("name", PLAYBOOK_NAMES)
def test_declared_transition_duration_wins(name: str) -> None:
    declared = _raw(name)["motion"]["pacing_rules"].get("transition_duration_seconds")
    if declared is None:
        pytest.skip(f"{name} declares no transition duration")
    assert _theme(name)["transitionDuration"] == pytest.approx(declared)


def _synthetic(monkeypatch, **overrides) -> dict:
    """Theme built from a minimal playbook, so each rule is checked in isolation."""
    playbook = {
        "identity": {"name": "synthetic", "category": "custom", "mood": "calm", "pace": "moderate"},
        "visual_language": {
            "color_palette": {
                "primary": ["#123456"],
                "accent": ["#ABCDEF"],
                "background": "#F7F6F2",
                "text": "#111111",
                "muted": "#555555",
            }
        },
        "typography": {"headings": {"font": "Headline Face", "weight": 500}, "body": {"font": "Body Face"}},
        "motion": {"pacing_rules": {}},
    }
    for key, value in overrides.items():
        playbook[key] = value
    import styles.playbook_loader as loader

    monkeypatch.setattr(loader, "load_playbook", lambda name, styles_dir=None: playbook)
    return VideoCompose()._build_theme_from_playbook("synthetic", {})


def test_surface_comes_from_the_stat_card_when_the_palette_has_none(monkeypatch) -> None:
    theme = _synthetic(monkeypatch, overlays={"stat_card": {"bg": "#FCFBF7"}})
    assert theme["surfaceColor"] == "#FCFBF7"
    # Captions sit on the declared raised surface instead of a generic bar.
    assert theme["captionBackgroundColor"] == "#FCFBF7"


def test_light_ground_without_surface_gets_a_light_caption_bar(monkeypatch) -> None:
    """Regression: only #FFFFFF/#FAFAFA/#F9FAFB counted as light, so a warm
    paper ground got the dark caption bar meant for dark themes."""
    theme = _synthetic(monkeypatch)
    assert theme["surfaceColor"] == "#F7F6F2"
    assert theme["captionBackgroundColor"].startswith("rgba(255, 255, 255")


def test_heading_weight_and_web_fonts_flow_into_the_theme(monkeypatch) -> None:
    theme = _synthetic(monkeypatch)
    assert theme["headingWeight"] == 500
    assert theme["webFonts"] == "bundled"

    typography = {"headings": {"font": "Headline Face"}, "body": {"font": "Body Face"}, "web_fonts": "google"}
    theme = _synthetic(monkeypatch, typography=typography)
    assert theme["webFonts"] == "google"
    assert "headingWeight" not in theme


def _theme_from(monkeypatch, playbook: dict) -> dict:
    import styles.playbook_loader as loader
    monkeypatch.setattr(loader, "load_playbook", lambda name, *a, **k: playbook)
    return VideoCompose()._build_theme_from_playbook("synthetic", {})


def _playbook_with(**extra) -> dict:
    base = yaml.safe_load((STYLES_DIR / "clean-professional.yaml").read_text(encoding="utf-8"))
    for key, value in extra.items():
        node = base
        *path, leaf = key.split("__")
        for part in path:
            node = node.setdefault(part, {})
        node[leaf] = value
    return base


def test_weight_matrix_drives_title_and_heading_weights(monkeypatch):
    theme = _theme_from(monkeypatch, _playbook_with(typography__weight_matrix={"title": 500, "heading": 600}))
    assert theme["titleWeight"] == 500 and theme["headingWeight"] == 600


def test_section_title_panel_and_edge_padding_come_from_the_playbook(monkeypatch):
    panel = {"bg": "rgba(5, 9, 18, 0.9)", "border": "rgba(255,255,255,0.16)", "radius": 16, "blur": 8, "max_width": 760}
    theme = _theme_from(monkeypatch, _playbook_with(overlays__section_title={"panel": panel, "edge_padding": 72}))
    assert theme["sectionTitlePanel"]["maxWidth"] == 760 and theme["sectionTitlePanel"]["blur"] == 8
    assert theme["sectionTitleEdgePadding"] == 72


def test_caption_upcoming_opacity_comes_from_the_playbook(monkeypatch):
    theme = _theme_from(monkeypatch, _playbook_with(overlays__captions={"upcoming_opacity": 0.8}))
    assert theme["captionUpcomingOpacity"] == 0.8


def test_new_overlay_keys_are_valid_playbook_schema():
    import json, jsonschema
    schema = json.loads((REPO_ROOT / "schemas" / "styles" / "playbook.schema.json").read_text(encoding="utf-8"))
    playbook = _playbook_with(overlays__section_title={"panel": {"bg": "#000", "max_width": 760}, "edge_padding": 72},
                          overlays__captions={"upcoming_opacity": 0.8})
    jsonschema.validate(playbook, schema)

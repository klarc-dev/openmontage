"""Custom playbook generator.

When none of the existing 4 playbooks match the production brief, the agent
can generate a custom playbook. This replaces the old behavior of forcing
everything through the closest preset.

The generator produces a schema-valid playbook YAML from a production context.
"""

from __future__ import annotations

import json
import yaml
from pathlib import Path
from typing import Any

import jsonschema

PLAYBOOK_SCHEMA_PATH = (
    Path(__file__).resolve().parent.parent
    / "schemas" / "styles" / "playbook.schema.json"
)
STYLES_DIR = Path(__file__).resolve().parent.parent / "styles"
CUSTOM_STYLES_DIR = STYLES_DIR / "custom"


def _custom_styles_dir() -> Path:
    """Where generated playbooks are saved.

    The ``custom/`` subdirectory of the first ``OPENMONTAGE_STYLES_PATH`` entry
    when one is set, so an external workspace never writes into the source
    tree; otherwise the built-in ``styles/custom/``.
    """
    from lib.paths import STYLES_PATH

    return STYLES_PATH[0] / "custom" if STYLES_PATH else CUSTOM_STYLES_DIR


def _load_playbook_schema() -> dict:
    with open(PLAYBOOK_SCHEMA_PATH) as f:
        return json.load(f)


def load_existing_playbook(name: str) -> dict[str, Any]:
    """Load an existing playbook YAML by name.

    Searches ``OPENMONTAGE_STYLES_PATH`` first, then the built-in ``styles/``
    (each with its ``custom/`` subdirectory); the first match wins.
    """
    from styles.playbook_loader import find_playbook

    path = find_playbook(name)
    with open(path) as f:
        return yaml.safe_load(f)


def list_playbooks() -> list[str]:
    """List all available playbook names (preset + custom, all search dirs)."""
    from styles.playbook_loader import list_playbooks as _list

    return _list()


def generate_playbook(
    name: str,
    context: dict[str, Any],
    base_playbook: str | None = None,
) -> dict[str, Any]:
    """Generate a custom playbook from production context.

    Args:
        name: Name for the new playbook.
        context: Dict with keys like:
            - mood: str (e.g., "warm", "dark", "energetic")
            - tone: str (e.g., "cinematic", "educational", "corporate")
            - colors: dict with primary, accent, background, text (optional)
            - fonts: dict with headings, body (optional)
            - pace: str (optional)
            - audience: str (optional)
        base_playbook: Name of existing playbook to use as a starting point.

    Returns:
        Schema-valid playbook dict.
    """
    # Start from base or create fresh
    if base_playbook:
        playbook = load_existing_playbook(base_playbook)
    else:
        playbook = _create_minimal_playbook(name, context)

    # Override identity
    playbook["identity"]["name"] = name
    if context.get("mood"):
        playbook["identity"]["mood"] = context["mood"]
    if context.get("pace"):
        playbook["identity"]["pace"] = context["pace"]
    if context.get("tone"):
        # Map tone to category
        tone_to_category = {
            "cinematic": "cinematic",
            "educational": "minimalist",
            "corporate": "motion-graphics",
            "playful": "motion-graphics",
            "raw": "cinematic",
        }
        playbook["identity"]["category"] = tone_to_category.get(
            context["tone"], "custom"
        )

    # Override colors if provided
    if context.get("colors"):
        colors = context["colors"]
        cp = playbook["visual_language"]["color_palette"]
        if colors.get("primary"):
            cp["primary"] = [colors["primary"]] if isinstance(colors["primary"], str) else colors["primary"]
        if colors.get("accent"):
            cp["accent"] = [colors["accent"]] if isinstance(colors["accent"], str) else colors["accent"]
        if colors.get("background"):
            cp["background"] = colors["background"]
        if colors.get("text"):
            cp["text"] = colors["text"]

    # Override fonts if provided
    if context.get("fonts"):
        fonts = context["fonts"]
        if fonts.get("headings"):
            playbook["typography"]["headings"]["font"] = fonts["headings"]
        if fonts.get("body"):
            playbook["typography"]["body"]["font"] = fonts["body"]

    return playbook


def _create_minimal_playbook(name: str, context: dict[str, Any]) -> dict[str, Any]:
    """Create a minimal but complete playbook from scratch."""
    mood = context.get("mood", "professional")
    tone = context.get("tone", "corporate")

    # Sensible defaults based on mood
    if mood in ("dark", "cinematic", "dramatic"):
        bg = "#0F172A"
        text = "#F8FAFC"
        primary = ["#3B82F6"]
        accent = ["#F59E0B"]
    elif mood in ("warm", "intimate", "organic"):
        bg = "#FFFBEB"
        text = "#1C1917"
        primary = ["#D97706"]
        accent = ["#059669"]
    elif mood in ("playful", "energetic", "bold"):
        bg = "#FFFFFF"
        text = "#1F2937"
        primary = ["#7C3AED"]
        accent = ["#EC4899"]
    else:  # professional, clean, neutral
        bg = "#FFFFFF"
        text = "#1F2937"
        primary = ["#2563EB"]
        accent = ["#F59E0B"]

    return {
        "identity": {
            "name": name,
            "category": "custom",
            "mood": mood,
            "pace": context.get("pace", "moderate"),
            "best_for": f"Custom playbook for {tone} {mood} content",
        },
        "visual_language": {
            "color_palette": {
                "primary": primary,
                "accent": accent,
                "background": bg,
                "text": text,
            },
            "composition": "balanced grid with breathing room",
            "texture": "clean digital",
        },
        "typography": {
            "headings": {"font": "Inter", "weight": 700},
            "body": {"font": "Inter", "weight": 400},
        },
        "motion": {
            "transitions": ["crossfade", "cut"],
            "animation_style": "spring-based with moderate damping",
            "pacing_rules": {
                "min_scene_hold_seconds": 2.0,
                "max_scene_hold_seconds": 6.0,
                "text_card_hold_seconds": 3.5,
                "stat_card_hold_seconds": 4.0,
                "transition_duration_seconds": 0.4,
            },
        },
        "audio": {
            "voice_style": "clear, conversational, authoritative",
            "music_mood": mood,
            "music_volume": 0.15,
        },
        "asset_generation": {
            "image_prompt_prefix": f"{mood} {tone} style",
            "consistency_anchors": [f"{mood} color palette", f"{tone} visual language"],
        },
        "quality_rules": [
            "Maintain color consistency across all scenes",
            "Text must be legible on all backgrounds",
            "Transitions should be purposeful, not decorative",
        ],
        "chart_palette": primary + accent + ["#10B981", "#EF4444", "#8B5CF6"],
    }


def save_playbook(
    playbook: dict[str, Any],
    project_name: str | None = None,
) -> Path:
    """Validate and save a playbook to the custom styles directory.

    Args:
        playbook: Schema-valid playbook dict.
        project_name: Optional project name for the filename.

    Returns:
        Path to the saved YAML file.
    """
    schema = _load_playbook_schema()
    jsonschema.validate(instance=playbook, schema=schema)

    name = project_name or playbook["identity"]["name"]
    filename = name.lower().replace(" ", "-").replace("_", "-")

    custom_dir = _custom_styles_dir()
    custom_dir.mkdir(parents=True, exist_ok=True)
    path = custom_dir / f"{filename}.yaml"

    with open(path, "w") as f:
        yaml.dump(playbook, f, default_flow_style=False, allow_unicode=True)

    return path

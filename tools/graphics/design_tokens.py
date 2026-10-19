"""Design-token emission for native Remotion compositions.

A playbook is the single source of truth for a brand's look, but a Remotion
composition is TypeScript: nothing stops an author typing `#005B52` when the
playbook says `#02585C`, or `fontSize: 57` when the playbook declares a
`major_third` scale. Both happened in shipped work, so colors drifted off-brand
and a parallel type ladder grew beside the declared one.

This module projects a playbook into a `tokens.ts` file that a composition
imports. Authors reference `C.primary` and `T.title`; the literal values exist
in exactly one generated file, and `tests` assert compositions contain no raw
hex or size literals. Drift stops being a matter of discipline.

Three token families are emitted:

`C` colors
    Semantic roles straight from `visual_language.color_palette` and
    `overlays`. Plus `accentReadable`, derived rather than stored: brand
    accents are frequently chosen for fills and fail WCAG AA as text. Instead
    of letting each composition invent its own darker accent (which is what
    produced an off-hue rose), the readable variant is computed by darkening
    along the *exact* brand hue until it clears AA on the paper ground.

`T` type scale
    Built by `compute_type_scale` from the playbook's own `scale_system`
    ratio, anchored at the body size for the render canvas. One ladder, shared
    with any other surface that reads the same playbook.

`L` layout rails
    One horizontal inset and a footer-safe exclusion zone derived from the
    footer's own geometry, so "keep the footer clear" is arithmetic rather
    than a hopeful comment.
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

from styles.playbook_loader import (
    _hex_to_hsl,
    _hsl_to_hex,
    _relative_luminance,
    compute_type_scale,
    load_playbook,
    validate_contrast,
)

# The slides design system anchors a 1rem body on a 1280x720 canvas. Video
# renders at 1920x1080, so the same visual ladder is this factor larger.
REFERENCE_CANVAS_WIDTH = 1280
REFERENCE_BODY_PX = 16

_HEX_RE = re.compile(r"#[0-9a-fA-F]{6}")

__all__ = [
    "derive_readable_accent",
    "build_tokens",
    "render_tokens_ts",
    "write_tokens",
]


def derive_readable_accent(
    accent_hex: str,
    background_hex: str,
    *,
    target_ratio: float = 4.5,
) -> dict[str, Any]:
    """Move `accent_hex` along its own hue until it clears `target_ratio`.

    Returns the original when it already passes. Hue is held exactly fixed so
    the result reads as the same brand color rather than a new one.

    The walk goes away from the background: darker on a light ground, lighter
    on a dark one. Saturation is damped in proportion, because darkening at
    full saturation turns a soft brand accent into a loud primary (a pale rose
    becomes pillar-box red), which is off-brand even though it passes contrast.

    Raises when no shade on the hue can reach the target, which means the
    pairing itself is wrong rather than the shade.
    """
    if validate_contrast(accent_hex, background_hex)["ratio"] >= target_ratio:
        return {
            "hex": accent_hex.upper(),
            "derived": False,
            "ratio": validate_contrast(accent_hex, background_hex)["ratio"],
        }

    hue, saturation, lightness = _hex_to_hsl(accent_hex)
    darken = _relative_luminance(background_hex) >= 0.5

    step = lightness
    while 0.02 < step < 0.98:
        step += -0.01 if darken else 0.01
        # Damp saturation toward the extreme being approached so the accent
        # keeps the muted character of its source instead of turning garish.
        damping = step / lightness if darken else (1 - step) / (1 - lightness)
        candidate = _hsl_to_hex(hue, saturation * damping, step)
        ratio = validate_contrast(candidate, background_hex)["ratio"]
        if ratio >= target_ratio:
            return {
                "hex": candidate.upper(),
                "derived": True,
                "ratio": ratio,
                "source": accent_hex.upper(),
                "hue_preserved": round(hue, 1),
            }

    raise ValueError(
        f"No shade of {accent_hex} on its own hue reaches {target_ratio}:1 "
        f"against {background_hex}. Choose a different ground for accent text."
    )


def build_tokens(
    playbook_name: str,
    *,
    canvas_width: int = 1920,
    styles_dir: Path | None = None,
) -> dict[str, Any]:
    """Project a playbook into the color, type, and layout token families."""
    playbook = load_playbook(playbook_name, styles_dir=styles_dir)
    palette = playbook["visual_language"]["color_palette"]
    overlays = playbook.get("overlays", {})

    primary = palette["primary"]
    accent = palette["accent"]
    background = palette["background"]

    # The readable accent must survive every light ground it can land on, not
    # just the page background: an accent tint (`accentSoft`) is darker than
    # paper, so a value derived against paper alone can still fail on a tinted
    # card. Derive against the darkest *light* ground in play.
    #
    # Dark grounds are deliberately excluded. Accent text on a dark surface is
    # a different problem that a darker accent cannot solve, and those surfaces
    # use the inverse text token instead. Non-hex declarations (rgba overlays)
    # are skipped because their luminance depends on what sits beneath them.
    candidate_grounds = [
        background,
        accent[1] if len(accent) > 1 else None,
        overlays.get("stat_card", {}).get("bg"),
        overlays.get("key_term", {}).get("bg"),
    ]
    light_grounds = [
        ground
        for ground in candidate_grounds
        if isinstance(ground, str)
        and _HEX_RE.fullmatch(ground)
        and _relative_luminance(ground) >= 0.5
    ]
    if not light_grounds:
        # A brand with no light surface at all still needs a readable accent;
        # fall back to the declared background and let the derivation report
        # honestly if the target is unreachable.
        light_grounds = [background]
    worst_ground = min(light_grounds, key=_relative_luminance)
    readable = derive_readable_accent(accent[0], worst_ground)

    colors: dict[str, str] = {
        "primary": primary[0],
        "primaryDark": primary[1] if len(primary) > 1 else primary[0],
        "primaryDeep": primary[2] if len(primary) > 2 else primary[0],
        "accent": accent[0],
        "accentSoft": accent[1] if len(accent) > 1 else accent[0],
        "accentReadable": readable["hex"],
        "paper": background,
        "ink": palette["text"],
        "muted": palette.get("muted", palette["text"]),
    }
    # Overlay blocks are optional and their inner keys vary by playbook, so
    # each is probed individually rather than assumed present.
    stat_card = overlays.get("stat_card", {})
    if "bg" in stat_card:
        colors["surface"] = stat_card["bg"]
    if "border" in stat_card:
        colors["line"] = stat_card["border"]
    key_term = overlays.get("key_term", {})
    if "bg" in key_term:
        colors["keyTerm"] = key_term["bg"]
    if "border" in key_term:
        colors["keyTermBorder"] = key_term["border"]
    if "accent" in overlays.get("hero_title", {}):
        colors["secondary"] = overlays["hero_title"]["accent"]
    if "text" in overlays.get("code_block", {}):
        colors["inverseText"] = overlays["code_block"]["text"]

    # The type ladder comes from the playbook's own declared ratio, scaled from
    # the reference canvas so one visual system serves decks and video alike.
    # Every step is a power of that ratio anchored on the body size, so the
    # ladder extends to display numerals without inventing off-ratio sizes.
    scale_factor = canvas_width / REFERENCE_CANVAS_WIDTH
    body_px = round(REFERENCE_BODY_PX * scale_factor)
    scale = compute_type_scale(body_px, playbook["typography"]["scale_system"])
    sizes = scale["sizes"]
    ratio = scale["ratio_value"]
    body = sizes["body"]

    type_scale = {
        "micro": round(sizes["caption"] / ratio),
        "small": sizes["caption"],
        "body": body,
        "lead": sizes["subheading"],
        "h3": sizes["heading"],
        "sub": sizes["display"],
        "title": round(body * ratio**4),
        "hero": round(body * ratio**5),
        "numeral": round(body * ratio**6),
        "display": round(body * ratio**7),
    }

    # Layout rails. Every horizontal edge is the same inset so a frame, a
    # header and a footer cannot drift to three different left edges (which is
    # exactly what happened when each was placed by hand). `contentBottom` is
    # the height of the reserved footer band measured from the bottom of the
    # canvas: footer offset + footer height + breathing gap. Content laid out
    # against it cannot collide with the footer as the type scale changes.
    scale_px = lambda rem: round(rem * REFERENCE_BODY_PX * scale_factor)  # noqa: E731
    footer_bottom = scale_px(1.1)
    footer_height = type_scale["micro"]
    footer_gap = scale_px(2.15)
    # The brand mark owns a reserved corner. Without it, content placed near
    # the top edge runs straight through the logo: a card border crossed the
    # chevron in a shipped render, and every video built on the same chrome
    # would repeat it. `markClearTop` is the lowest edge the mark occupies plus
    # a tight gap. Content in the right-hand column must start at or below it,
    # and `headerTop` is never allowed above it.
    mark_size = type_scale["h3"] + type_scale["small"] // 2
    mark_inset = scale_px(1.1)
    content_gap_tight = scale_px(1.1)
    mark_clear_top = mark_inset + mark_size + content_gap_tight
    layout = {
        "contentInset": scale_px(3.5),
        "headerTop": max(scale_px(6.0), mark_clear_top),
        "footerBottom": footer_bottom,
        "footerHeight": footer_height,
        "footerGap": footer_gap,
        "contentBottom": footer_bottom + footer_height + footer_gap,
        "contentGap": scale_px(2.0),
        "contentGapTight": content_gap_tight,
        "markSize": mark_size,
        "markInset": mark_inset,
        "markClearTop": mark_clear_top,
        # Images and visual cards default to one playbook-owned radius. Without
        # a shared value, generated compositions repeatedly ship sharp white
        # rectangles against otherwise soft editorial surfaces.
        "mediaRadius": round(
            overlays.get("stat_card", {}).get("radius", 12) * scale_factor
        ),
    }

    typography = playbook["typography"]
    fonts = {
        "heading": typography["headings"]["font"],
        "body": typography["body"]["font"],
        "mono": typography.get("code", typography["body"])["font"],
    }

    return {
        "playbook": playbook_name,
        "canvas_width": canvas_width,
        "colors": colors,
        "type_scale": type_scale,
        "layout": layout,
        "fonts": fonts,
        "accent_derivation": readable,
        "scale_system": scale["ratio_name"],
        "scale_ratio": ratio,
    }


def _ts_object(values: dict[str, Any], *, quote_values: bool) -> str:
    lines = []
    for key, value in values.items():
        rendered = f'"{value}"' if quote_values else str(value)
        lines.append(f"  {key}: {rendered},")
    return "\n".join(lines)


def render_tokens_ts(tokens: dict[str, Any]) -> str:
    """Render the token families as a TypeScript module."""
    accent = tokens["accent_derivation"]
    if accent["derived"]:
        source_ratio = validate_contrast(
            accent["source"], tokens["colors"]["paper"]
        )["ratio"]
        accent_note = "\n".join(
            [
                f"// `accentReadable` is derived, not chosen: {accent['source']} scores",
                f"// {source_ratio}:1 on the paper ground and fails WCAG AA for text.",
                f"// Darkening along hue {accent['hue_preserved']} to {accent['hex']} reaches "
                f"{accent['ratio']}:1.",
                "// Use `accent` for fills and rules; use `accentReadable` whenever the",
                "// accent carries text.",
            ]
        )
    else:
        accent_note = (
            f"// `accentReadable` equals `accent`: it already scores "
            f"{accent['ratio']}:1 as text."
        )

    return f"""// Generated from styles/{tokens['playbook']}.yaml by tools/graphics/design_tokens.py.
// Do not edit by hand and do not copy these values into a composition: import
// the tokens instead. The composition contract tests fail on any literal hex
// or font size in composition source.
//
{accent_note}

/** Semantic color roles. */
export const C = {{
{_ts_object(tokens['colors'], quote_values=True)}
}} as const;

/** Modular type scale ({tokens['scale_system']}, ratio {tokens['scale_ratio']}) in px
 *  for a {tokens['canvas_width']}px canvas. Every size in the composition comes from here. */
export const T = {{
{_ts_object(tokens['type_scale'], quote_values=False)}
}} as const;

/** Layout rails in px. `contentBottom` is the footer-safe exclusion zone:
 *  content must not extend below it. */
export const L = {{
{_ts_object(tokens['layout'], quote_values=False)}
}} as const;

/** Font families, resolved from approved project assets at render time. */
export const F = {{
{_ts_object(tokens['fonts'], quote_values=True)}
}} as const;
"""


def write_tokens(
    playbook_name: str,
    destination: Path,
    *,
    canvas_width: int = 1920,
    styles_dir: Path | None = None,
) -> dict[str, Any]:
    """Emit `tokens.ts` next to a composition and return the token report."""
    tokens = build_tokens(
        playbook_name, canvas_width=canvas_width, styles_dir=styles_dir
    )
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(render_tokens_ts(tokens), encoding="utf-8")
    return tokens


if __name__ == "__main__":  # pragma: no cover - operator convenience
    import argparse

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("playbook")
    parser.add_argument("destination", type=Path)
    parser.add_argument("--canvas-width", type=int, default=1920)
    args = parser.parse_args()
    report = write_tokens(
        args.playbook, args.destination, canvas_width=args.canvas_width
    )
    print(json.dumps(report, indent=2))

"""The design-token emitter is the only thing standing between a playbook and
a composition, so its guarantees are asserted rather than assumed.

Three shipped defects motivate these tests:

1. A composition invented `#005B52` where the playbook says `#02585C`, plus
   eleven more near-miss colors. Nothing compared them.
2. That same composition used the accent as *text* at `#B6465F`, a value
   hand-picked for readability but 3.9 degrees off the brand hue. The playbook
   declares `contrast_validation: true` and no code honoured it.
3. Twenty-four distinct `fontSize` literals grew beside a declared
   `major_third` scale that nothing consumed.
"""

from __future__ import annotations

import re

import pytest
import yaml

from styles.playbook_loader import (
    STYLES_DIR,
    _hex_to_hsl,
    _relative_luminance,
    compute_type_scale,
    list_playbooks,
    validate_contrast,
)
from tools.graphics.design_tokens import (
    build_tokens,
    derive_readable_accent,
    render_tokens_ts,
)

PLAYBOOK_NAMES = sorted(list_playbooks())
# Any shipped playbook works for the canvas and emission checks.
REFERENCE = "clean-professional"


def _raw(name: str) -> dict:
    # Resolve like the loader: listed playbooks may live outside styles/ when a
    # styles search path is configured.
    try:
        from styles.playbook_loader import find_playbook
    except ImportError:  # loaders without a search path
        path = STYLES_DIR / f"{name}.yaml"
    else:
        path = find_playbook(name)
    return yaml.safe_load(path.read_text(encoding="utf-8"))


@pytest.mark.parametrize("name", PLAYBOOK_NAMES)
def test_colors_come_from_the_playbook_not_from_nearby_values(name: str) -> None:
    """Every emitted color must appear verbatim in the playbook.

    Regression: a composition drifted to a parallel palette where no single
    color matched the brand, yet all were close enough to pass a glance.
    """
    playbook = _raw(name)
    serialized = yaml.safe_dump(playbook)
    # Playbooks declare colors as hex and occasionally as rgba(), so compare
    # against every color-ish string the playbook contains rather than hex only.
    declared = {
        value.upper()
        for value in re.findall(r"#[0-9A-Fa-f]{6}|rgba?\([^)]*\)", serialized)
    }
    tokens = build_tokens(name)

    for role, value in tokens["colors"].items():
        if role == "accentReadable":
            continue  # derived on purpose; covered by the contrast tests below
        assert value.upper() in declared, (
            f"{name}: token {role}={value} is not declared in the playbook"
        )


@pytest.mark.parametrize("name", PLAYBOOK_NAMES)
def test_readable_accent_clears_aa_on_every_light_ground(name: str) -> None:
    """Accent text must pass AA on every light surface it can land on.

    Regression: deriving against the page background alone left the accent at
    3.68:1 on the accent-tinted card, which is darker than paper. A pill and a
    card footer in the shipped composition used exactly that pairing.
    """
    tokens = build_tokens(name)
    colors = tokens["colors"]
    readable = colors["accentReadable"]

    grounds = {
        role: colors[role]
        for role in ("paper", "surface", "accentSoft", "keyTerm")
        if role in colors
    }
    # Only light hex grounds are in scope. Accent text on a dark ground uses
    # the inverse token instead, and rgba overlays have no fixed luminance.
    for role, ground in grounds.items():
        if not re.fullmatch(r"#[0-9a-fA-F]{6}", ground):
            continue
        if _relative_luminance(ground) < 0.5:
            continue
        result = validate_contrast(readable, ground)
        assert result["normal_text"]["AA"], (
            f"{name}: accentReadable {readable} scores {result['ratio']}:1 on "
            f"{role} ({ground}), below the 4.5:1 AA floor"
        )


@pytest.mark.parametrize("name", PLAYBOOK_NAMES)
def test_readable_accent_stays_on_the_brand_hue(name: str) -> None:
    """Gaining contrast must not become choosing a different color.

    Regression: the hand-picked accent sat 3.9 degrees off the brand hue. A
    derived value holds the hue exactly, so the readable variant is recognisably
    the same brand color.
    """
    tokens = build_tokens(name)
    brand_hue, _, _ = _hex_to_hsl(tokens["colors"]["accent"])
    readable_hue, _, _ = _hex_to_hsl(tokens["colors"]["accentReadable"])

    drift = min(abs(brand_hue - readable_hue), 360 - abs(brand_hue - readable_hue))
    assert drift <= 1.0, (
        f"{name}: readable accent drifted {drift:.1f} degrees from the brand hue"
    )


def test_readable_accent_does_not_oversaturate_a_muted_brand() -> None:
    """Darkening at fixed saturation turns a soft rose into pillar-box red.

    `#F5A3B0` darkened without damping yields `#DD1837`, which passes contrast
    but reads as an alert color rather than a restrained editorial accent.
    """
    result = derive_readable_accent("#F5A3B0", "#F7F6F2")
    _, saturation, _ = _hex_to_hsl(result["hex"])

    assert result["derived"] is True
    assert saturation < 0.60, (
        f"{result['hex']} has saturation {saturation:.2f}: too loud for a brand "
        "accent whose source is a muted pastel"
    )


def test_accent_that_already_passes_is_returned_unchanged() -> None:
    """A brand whose accent is already readable must not be altered."""
    result = derive_readable_accent("#02585C", "#F7F6F2")

    assert result["derived"] is False
    assert result["hex"] == "#02585C"


def test_unreachable_contrast_target_raises_rather_than_shipping() -> None:
    """When no shade on the hue can clear the target, say so.

    The derivation only darkens, so a mid-grey ground is unreachable: every
    darker shade passes *through* the ground's own luminance before it gets far
    enough away, and 4.5:1 is never attained. Emitting an unreadable token here
    would be worse than refusing.
    """
    with pytest.raises(ValueError, match="reaches"):
        derive_readable_accent("#F5A3B0", "#767676")


@pytest.mark.parametrize("name", PLAYBOOK_NAMES)
def test_type_scale_uses_the_ratio_the_playbook_declares(name: str) -> None:
    """The ladder is computed from `scale_system`, not invented per project.

    Regression: a playbook declared `major_third` for months while a
    composition carried 24 unrelated size literals.
    """
    playbook = _raw(name)
    tokens = build_tokens(name)
    expected = compute_type_scale(
        round(16 * tokens["canvas_width"] / 1280),
        playbook["typography"]["scale_system"],
    )

    assert tokens["scale_ratio"] == expected["ratio_value"]
    assert tokens["type_scale"]["body"] == expected["sizes"]["body"]
    assert tokens["type_scale"]["lead"] == expected["sizes"]["subheading"]
    assert tokens["type_scale"]["h3"] == expected["sizes"]["heading"]


@pytest.mark.parametrize("name", PLAYBOOK_NAMES)
def test_type_scale_is_strictly_ordered(name: str) -> None:
    """Each step must be larger than the one below it."""
    scale = build_tokens(name)["type_scale"]
    ladder = ["micro", "small", "body", "lead", "h3", "sub", "title", "hero", "display"]

    sizes = [scale[step] for step in ladder]
    assert sizes == sorted(sizes), f"{name}: type scale is not monotonic: {scale}"
    assert len(set(sizes)) == len(sizes), f"{name}: type scale has duplicate steps"


@pytest.mark.parametrize("name", PLAYBOOK_NAMES)
def test_footer_safe_zone_is_derived_from_footer_geometry(name: str) -> None:
    """`contentBottom` must account for the footer it is meant to clear.

    Regression: the footer baseline was a hardcoded `bottom: 25` while the
    skill claimed "footer-safe exclusion zones remain clear" as an invariant
    with no number behind it.
    """
    layout = build_tokens(name)["layout"]

    assert layout["contentBottom"] == (
        layout["footerBottom"] + layout["footerHeight"] + layout["footerGap"]
    )
    assert layout["contentBottom"] > layout["footerBottom"] + layout["footerHeight"], (
        "the safe zone must leave a gap above the footer, not merely touch it"
    )


@pytest.mark.parametrize("name", PLAYBOOK_NAMES)
def test_one_horizontal_inset_serves_every_edge(name: str) -> None:
    """A single inset token exists so frame, header and footer cannot diverge.

    Regression: the shipped composition had three left edges (72, 58, 40).
    """
    layout = build_tokens(name)["layout"]

    assert layout["contentInset"] > 0
    assert isinstance(layout["contentInset"], int)


@pytest.mark.parametrize("name", PLAYBOOK_NAMES)
def test_media_surfaces_have_a_positive_playbook_radius(name: str) -> None:
    """Audience-facing media must not silently fall back to sharp corners."""
    layout = build_tokens(name)["layout"]

    assert layout["mediaRadius"] > 0
    assert isinstance(layout["mediaRadius"], int)


def test_type_scale_tracks_the_canvas(self=None) -> None:
    """Doubling the canvas doubles the ladder, so rails hold across formats."""
    small = build_tokens(REFERENCE, canvas_width=1280)
    large = build_tokens(REFERENCE, canvas_width=2560)

    assert large["type_scale"]["body"] == small["type_scale"]["body"] * 2
    assert large["layout"]["contentInset"] == small["layout"]["contentInset"] * 2


def test_emitted_module_is_importable_typescript() -> None:
    """The generated file must expose the four token families as const objects."""
    source = render_tokens_ts(build_tokens(REFERENCE))

    for family in ("export const C = {", "export const T = {", "export const L = {", "export const F = {"):
        assert family in source
    assert source.count("as const;") == 4
    # The header must tell a reader where the values came from and why the
    # readable accent differs from the brand accent.
    assert f"{REFERENCE}.yaml" in source
    assert "accentReadable" in source

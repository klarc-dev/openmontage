import { cancelRender, continueRender, delayRender } from "remotion";
import { getAvailableFonts } from "@remotion/google-fonts";

import { loadPlayfair, loadSpaceGrotesk } from "./localFonts";

/**
 * Load the font families a theme names, so a style playbook can use any
 * Google font without a code change in the compositions.
 *
 * Families bundled in ../fonts (Space Grotesk, Playfair Display) are always
 * registered from the local files and need no network. When the theme opts in
 * with `webFonts: "google"` (playbook `typography.web_fonts: google`), any
 * other family is looked up in the @remotion/google-fonts catalogue and loaded
 * with the regular weights it offers (400-700) in its latin subsets. Without
 * the opt-in, other families are left to CSS, as before, and a render stays
 * offline. A render waits for every requested face; a face that fails to
 * load cancels the render instead of silently falling back to a system font.
 * A family that is not in the catalogue (a system or locally installed font)
 * is left to CSS.
 *
 * Loading is deferred to a microtask for the reason documented in
 * ./localFonts: a delayRender handle created during bundle evaluation can be
 * wiped by a second copy of Remotion's delay-render module.
 */

const REGULAR_WEIGHTS = ["400", "500", "600", "700"];
const LATIN_SUBSETS = ["latin", "latin-ext"];
const requested = new Set<string>();

const BUNDLED: Record<string, () => void> = {
  "Space Grotesk": () => {
    loadSpaceGrotesk(["400", "500", "600", "700"]);
  },
  "Playfair Display": () => {
    loadPlayfair("normal", ["400", "700"]);
  },
};

/** First family of a CSS font stack, without quotes. */
export const primaryFamily = (stack: string | undefined): string | undefined => {
  const first = (stack || "").split(",")[0]?.trim().replace(/^["']|["']$/g, "");
  return first || undefined;
};

const loadGoogleFamily = (family: string) => {
  const entry = getAvailableFonts().find((f) => f.fontFamily === family);
  if (!entry) return;
  queueMicrotask(() => {
    const handle = delayRender(`Loading font ${family}`);
    entry
      .load()
      .then((font) => {
        const info = font.getInfo();
        const normal = info.fonts.normal || {};
        const weights = REGULAR_WEIGHTS.filter((w) => w in normal);
        const subsets = LATIN_SUBSETS.filter((s) => info.subsets.includes(s));
        const { waitUntilDone } = font.loadFont("normal", {
          weights: (weights.length ? weights : Object.keys(normal)) as never[],
          subsets: (subsets.length ? subsets : info.subsets) as never[],
          ignoreTooManyRequestsWarning: true,
        });
        return waitUntilDone();
      })
      .then(() => continueRender(handle))
      .catch((err) => cancelRender(new Error(`Font ${family} failed to load: ${err}`)));
  });
};

/** Ensure every family a theme references is loaded before frames render. */
export const loadThemeFonts = (theme: {
  headingFont?: string;
  bodyFont?: string;
  monoFont?: string;
  webFonts?: "bundled" | "google";
}) => {
  for (const stack of [theme.headingFont, theme.bodyFont, theme.monoFont]) {
    const family = primaryFamily(stack);
    if (!family || requested.has(family)) continue;
    if (BUNDLED[family]) {
      requested.add(family);
      BUNDLED[family]();
    } else if (theme.webFonts === "google") {
      requested.add(family);
      loadGoogleFamily(family);
    }
  }
};

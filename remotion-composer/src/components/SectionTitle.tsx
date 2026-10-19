import {
  AbsoluteFill,
  interpolate,
  spring,
  useCurrentFrame,
  useVideoConfig,
} from "remotion";

interface SectionTitleProps {
  title: string;
  subtitle?: string;
  accentColor?: string;
  /** Title color. Defaults to near-white; pass the theme's textColor on light themes. */
  textColor?: string;
  position?: "top-left" | "bottom-left" | "center";
  headingFont?: string;
  bodyFont?: string;
  headingWeight?: number;
  /** Distance from the frame edge for corner positions (px). */
  edgePadding?: number;
  /** Optional raised panel behind corner-positioned titles (playbook overlays.section_title.panel). */
  panel?: SectionTitlePanel;
}

export type SectionTitlePanel = {
  bg?: string;
  border?: string;
  shadow?: string;
  radius?: number;
  blur?: number;
  padding?: string;
  maxWidth?: number;
};

export const SectionTitle: React.FC<SectionTitleProps> = ({
  title,
  subtitle,
  accentColor = "#22D3EE",
  textColor = "#F8FAFC",
  position = "top-left",
  headingFont = "Space Grotesk, Inter, system-ui, sans-serif",
  bodyFont = "Space Grotesk, Inter, system-ui, sans-serif",
  headingWeight = 700,
  edgePadding = 60,
  panel,
}) => {
  const frame = useCurrentFrame();
  const { fps, durationInFrames } = useVideoConfig();

  // Entrance spring
  const slideIn = spring({
    frame,
    fps,
    config: { damping: 15, stiffness: 80 },
  });

  // Exit fade
  const exitStart = durationInFrames - 15;
  const fadeOut = interpolate(frame, [exitStart, durationInFrames], [1, 0], {
    extrapolateLeft: "clamp",
    extrapolateRight: "clamp",
  });

  const opacity = Math.min(slideIn, fadeOut);

  const positionStyles: React.CSSProperties =
    position === "center"
      ? { justifyContent: "center", alignItems: "center" }
      : position === "bottom-left"
      ? { justifyContent: "flex-end", alignItems: "flex-start", padding: edgePadding }
      : { justifyContent: "flex-start", alignItems: "flex-start", padding: edgePadding };
  const panelStyles: React.CSSProperties =
    panel && position !== "center"
      ? {
          maxWidth: panel.maxWidth,
          padding: panel.padding ?? "18px 24px 20px",
          borderRadius: panel.radius ?? 16,
          background: panel.bg,
          border: panel.border ? `1px solid ${panel.border}` : undefined,
          boxShadow: panel.shadow,
          backdropFilter: panel.blur ? `blur(${panel.blur}px)` : undefined,
        }
      : {};

  return (
    <AbsoluteFill style={positionStyles}>
      <div
        style={{
          ...panelStyles,
          opacity,
          transform: `translateX(${interpolate(slideIn, [0, 1], [-40, 0])}px)`,
        }}
      >
        {/* Accent bar */}
        <div
          style={{
            width: interpolate(slideIn, [0, 1], [0, 60]),
            height: 4,
            backgroundColor: accentColor,
            marginBottom: 12,
            borderRadius: 2,
          }}
        />
        <div
          style={{
            fontSize: 28,
            fontWeight: headingWeight,
            color: textColor,
            fontFamily: headingFont,
            letterSpacing: "0.05em",
            textTransform: "uppercase",
            textShadow: "0 2px 8px rgba(0,0,0,0.6)",
          }}
        >
          {title}
        </div>
        {subtitle && (
          <div
            style={{
              fontSize: 18,
              fontWeight: 400,
              color: accentColor,
              fontFamily: bodyFont,
              marginTop: 4,
              opacity: spring({
                frame: frame - 8,
                fps,
                config: { damping: 20 },
              }),
              textShadow: "0 2px 8px rgba(0,0,0,0.6)",
            }}
          >
            {subtitle}
          </div>
        )}
      </div>
    </AbsoluteFill>
  );
};

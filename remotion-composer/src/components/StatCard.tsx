import { AbsoluteFill, spring, useCurrentFrame, useVideoConfig } from "remotion";

interface StatCardProps {
  stat: string;
  subtitle?: string;
  statFontSize?: number;
  subtitleFontSize?: number;
  color?: string;
  accentColor?: string;
  backgroundColor?: string;
  headingFont?: string;
  bodyFont?: string;
  headingWeight?: number;
}

export const StatCard: React.FC<StatCardProps> = ({
  stat,
  subtitle,
  statFontSize = 128,
  subtitleFontSize = 36,
  color = "#FFFFFF",
  accentColor = "#F59E0B",
  backgroundColor = "#1F2937",
  headingFont = "Inter, system-ui, sans-serif",
  bodyFont = "Inter, system-ui, sans-serif",
  headingWeight = 800,
}) => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();

  const scale = spring({
    frame,
    fps,
    config: { damping: 12, stiffness: 120 },
    from: 0.8,
    to: 1,
  });

  const subtitleOpacity = spring({
    frame: frame - 8,
    fps,
    config: { damping: 20 },
  });

  return (
    <AbsoluteFill
      style={{
        justifyContent: "center",
        alignItems: "center",
        background: backgroundColor,
      }}
    >
      <div style={{ textAlign: "center" }}>
        <div
          style={{
            transform: `scale(${scale})`,
            fontSize: statFontSize,
            color: accentColor,
            fontFamily: headingFont,
            fontWeight: headingWeight,
            lineHeight: 1.1,
          }}
        >
          {stat}
        </div>
        {subtitle && (
          <div
            style={{
              opacity: subtitleOpacity,
              fontSize: subtitleFontSize,
              color,
              fontFamily: bodyFont,
              fontWeight: 400,
              marginTop: 16,
            }}
          >
            {subtitle}
          </div>
        )}
      </div>
    </AbsoluteFill>
  );
};

import React from "react";
import {
  AbsoluteFill,
  interpolate,
  useCurrentFrame,
} from "remotion";
import {AmbientBackground} from "../components/AmbientBackground";
import {SceneTitle} from "../components/SceneTitle";
import {QuantFidelityLogoText} from "../components/QuantFidelityLogoText";
import {DisclaimerText} from "../components/DisclaimerText";
import {SCRIPT} from "../timing";

export const FinalScene: React.FC = () => {
  const frame = useCurrentFrame();

  const progress = interpolate(frame, [4, 28], [0, 1], {
    extrapolateLeft: "clamp",
    extrapolateRight: "clamp",
  });

  const logoAppear = interpolate(frame, [26, 46], [0, 1], {
    extrapolateLeft: "clamp",
    extrapolateRight: "clamp",
  });

  const disclaimerAppear = interpolate(frame, [40, 58], [0, 1], {
    extrapolateLeft: "clamp",
    extrapolateRight: "clamp",
  });

  return (
    <AbsoluteFill>
      <AmbientBackground />
      <SceneTitle
        title={SCRIPT.final.title}
        subtitle={SCRIPT.final.subtitle}
        progress={progress}
      >
        <div
          style={{
            display: "flex",
            flexDirection: "column",
            alignItems: "center",
            gap: 22,
          }}
        >
          <div
            style={{
              opacity: logoAppear,
              transform: `translateY(${(1 - logoAppear) * 12}px)`,
            }}
          >
            <QuantFidelityLogoText fontSize={64} />
          </div>
          <DisclaimerText
            text={SCRIPT.final.disclaimer}
            opacity={disclaimerAppear}
          />
        </div>
      </SceneTitle>
    </AbsoluteFill>
  );
};

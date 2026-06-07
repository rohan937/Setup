import React from "react";
import {AbsoluteFill, Easing, interpolate, useCurrentFrame} from "remotion";
import {FONT_STACK, SCRIPT} from "../timing";
import {AmbientBackground} from "../components/AmbientBackground";
import {SafeScreenshotFrame} from "../components/SafeScreenshotFrame";
import {Caption} from "./Caption";

const SHOTS = SCRIPT.montage.shots;

// Layout: a staggered, slightly fanned spread of product surfaces.
const LAYOUT = [
  {offsetX: -540, rotate: -5, width: 470, top: 300},
  {offsetX: -190, rotate: -2, width: 510, top: 250},
  {offsetX: 190, rotate: 2, width: 510, top: 250},
  {offsetX: 540, rotate: 5, width: 470, top: 300},
  {offsetX: 0, rotate: 0, width: 560, top: 220},
];

// Scene 8 (60-66s): a montage of the product surfaces slide in staggered with
// soft shadows. Uses SafeScreenshotFrame so missing PNGs render polished mock
// frames (no 404s).
export const MontageScene: React.FC = () => {
  const frame = useCurrentFrame();

  return (
    <AbsoluteFill>
      <AmbientBackground />

      <AbsoluteFill>
        {SHOTS.map((shot, i) => {
          const cfg = LAYOUT[i % LAYOUT.length];
          const start = i * 9;
          const appear = interpolate(frame, [start, start + 22], [0, 1], {
            extrapolateLeft: "clamp",
            extrapolateRight: "clamp",
            easing: Easing.out(Easing.cubic),
          });
          // The centered hero (index 4) sits on top.
          const z = i === SHOTS.length - 1 ? 10 : i;
          return (
            <div
              key={shot.name}
              style={{
                position: "absolute",
                left: "50%",
                top: cfg.top,
                transform: `translateX(-50%)`,
                zIndex: z,
              }}
            >
              <SafeScreenshotFrame
                name={shot.name}
                label={shot.label}
                appear={appear}
                width={cfg.width}
                offsetX={cfg.offsetX}
                rotate={cfg.rotate}
              />
            </div>
          );
        })}
      </AbsoluteFill>

      <AbsoluteFill
        style={{fontFamily: FONT_STACK, pointerEvents: "none"}}
      >
        <Caption text={SCRIPT.montage.caption} inAt={20} position="bottom" />
      </AbsoluteFill>
    </AbsoluteFill>
  );
};

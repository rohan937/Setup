import React from "react";
import {Composition} from "remotion";
import {QuantFidelityLaunchVideo} from "./QuantFidelityLaunchVideo";
import {DURATION, FPS} from "./timing";

export const RemotionRoot: React.FC = () => {
  return (
    <>
      <Composition
        id="QuantFidelityLaunchVideo"
        component={QuantFidelityLaunchVideo}
        durationInFrames={DURATION}
        fps={FPS}
        width={1920}
        height={1080}
      />
    </>
  );
};

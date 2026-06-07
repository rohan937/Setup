import React from "react";
import {AbsoluteFill, Sequence} from "remotion";
import {SCENES, SceneId} from "./timing";
import {HookScene} from "./scenes/HookScene";
import {TensionScene} from "./scenes/TensionScene";
import {BacktestCardScene} from "./scenes/BacktestCardScene";
import {ProductRevealScene} from "./scenes/ProductRevealScene";
import {RealityCheckScene} from "./scenes/RealityCheckScene";
import {WorkflowScene} from "./scenes/WorkflowScene";
import {ScreenshotScene} from "./scenes/ScreenshotScene";
import {FinalScene} from "./scenes/FinalScene";

const SCENE_COMPONENTS: Record<SceneId, React.FC> = {
  hook: HookScene,
  tension: TensionScene,
  backtest: BacktestCardScene,
  reveal: ProductRevealScene,
  reality: RealityCheckScene,
  workflow: WorkflowScene,
  screenshots: ScreenshotScene,
  final: FinalScene,
};

export const QuantFidelityLaunchVideo: React.FC = () => {
  return (
    <AbsoluteFill>
      {SCENES.map((scene) => {
        const Comp = SCENE_COMPONENTS[scene.id];
        return (
          <Sequence
            key={scene.id}
            from={scene.from}
            durationInFrames={scene.durationInFrames}
            name={scene.id}
          >
            <Comp />
          </Sequence>
        );
      })}
    </AbsoluteFill>
  );
};

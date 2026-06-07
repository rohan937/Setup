import React from "react";
import {AbsoluteFill, Sequence} from "remotion";
import {SCENES, SceneId} from "./timing";
import {AmbientBackground} from "./components/AmbientBackground";
import {HookScene} from "./scenes/HookScene";
import {HiddenScene} from "./scenes/HiddenScene";
import {CommandCenterScene} from "./scenes/CommandCenterScene";
import {WorkspaceScene} from "./scenes/WorkspaceScene";
import {RealityScene} from "./scenes/RealityScene";
import {EvidenceScene} from "./scenes/EvidenceScene";
import {GovernanceScene} from "./scenes/GovernanceScene";
import {MontageScene} from "./scenes/MontageScene";
import {FinalScene} from "./scenes/FinalScene";

// The DARK 9-scene AI product walkthrough. Each scene is mounted in its own
// <Sequence> so its useCurrentFrame() is local (0-based) to the scene. Every
// scene renders its own dark AmbientBackground; a persistent base background
// also sits at the composition level so cross-fades never flash the page.
const SCENE_COMPONENTS: Record<SceneId, React.FC> = {
  hook: HookScene,
  hidden: HiddenScene,
  commandCenter: CommandCenterScene,
  workspace: WorkspaceScene,
  reality: RealityScene,
  evidence: EvidenceScene,
  governance: GovernanceScene,
  montage: MontageScene,
  final: FinalScene,
};

export const QuantFidelityLaunchVideo: React.FC = () => {
  return (
    <AbsoluteFill style={{backgroundColor: "#0B1020"}}>
      {/* Persistent base background (per-scene backgrounds layer on top). */}
      <AmbientBackground />

      {SCENES.map((scene) => {
        const SceneComponent = SCENE_COMPONENTS[scene.id];
        return (
          <Sequence
            key={scene.id}
            from={scene.from}
            durationInFrames={scene.durationInFrames}
            name={scene.id}
          >
            <SceneComponent />
          </Sequence>
        );
      })}
    </AbsoluteFill>
  );
};

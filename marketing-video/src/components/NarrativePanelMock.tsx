import React from "react";
import {COLORS, FONT_STACK, SCRIPT} from "../timing";

interface NarrativePanelMockProps {
  // 0 -> 1 slide/fade in.
  appear: number;
}

// Panel showing the auto-generated research risk narrative.
export const NarrativePanelMock: React.FC<NarrativePanelMockProps> = ({appear}) => {
  const a = Math.max(0, Math.min(1, appear));

  return (
    <div
      style={{
        padding: "20px 22px",
        borderRadius: 14,
        background: COLORS.elevated,
        border: `1px solid rgba(139,92,246,0.3)`,
        boxShadow: `0 18px 44px rgba(0,0,0,0.5), 0 0 30px ${COLORS.purple}1f`,
        fontFamily: FONT_STACK,
        transform: `translateY(${(1 - a) * 20}px)`,
        opacity: a,
        width: 480,
      }}
    >
      <div
        style={{
          display: "flex",
          alignItems: "center",
          gap: 9,
          marginBottom: 12,
        }}
      >
        <span
          style={{
            width: 22,
            height: 22,
            borderRadius: 7,
            display: "flex",
            alignItems: "center",
            justifyContent: "center",
            fontSize: 12,
            background: `linear-gradient(135deg, ${COLORS.purple}, ${COLORS.blue})`,
            color: "#fff",
            boxShadow: `0 0 12px ${COLORS.purple}88`,
          }}
        >
          ✦
        </span>
        <span style={{fontSize: 14, fontWeight: 700, color: COLORS.textPrimary}}>
          Research Risk Narrative
        </span>
        <span
          style={{
            marginLeft: "auto",
            fontSize: 10.5,
            fontWeight: 700,
            color: COLORS.purple,
            background: "rgba(139,92,246,0.14)",
            borderRadius: 999,
            padding: "2px 9px",
          }}
        >
          AI-generated
        </span>
      </div>
      <p
        style={{
          margin: 0,
          fontSize: 13,
          lineHeight: 1.55,
          color: COLORS.textSecondary,
        }}
      >
        {SCRIPT.governance.panel.narrative}
      </p>
    </div>
  );
};

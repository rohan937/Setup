import React from "react";
import {COLORS, FONT_STACK, MetricTone, SCRIPT} from "../timing";
import {toneColor, toneGlyph} from "./tone";
import {NarrativePanelMock} from "./NarrativePanelMock";

interface GovernancePanelMockProps {
  // 0 -> 1 overall reveal.
  appear: number;
  // Show the pressed state of the generate button.
  buttonPressed?: boolean;
  // 0 -> 1 narrative reveal (0 = hidden). Optional.
  narrativeAppear?: number;
}

const PANEL = SCRIPT.governance.panel;

// "Promotion Readiness" — target, gate rows, generate button, narrative.
export const GovernancePanelMock: React.FC<GovernancePanelMockProps> = ({
  appear,
  buttonPressed = false,
  narrativeAppear = 0,
}) => {
  const a = Math.max(0, Math.min(1, appear));

  return (
    <div style={{display: "flex", flexDirection: "column", alignItems: "center", gap: 18}}>
      <div
        style={{
          padding: "26px 28px",
          borderRadius: 16,
          background: COLORS.surface,
          border: `1px solid ${COLORS.border}`,
          boxShadow: "0 24px 60px rgba(0,0,0,0.45)",
          fontFamily: FONT_STACK,
          transform: `translateY(${(1 - a) * 24}px)`,
          opacity: a,
          width: 520,
        }}
      >
        {/* Header. */}
        <div
          style={{
            display: "flex",
            alignItems: "center",
            justifyContent: "space-between",
            marginBottom: 18,
          }}
        >
          <span style={{fontSize: 16, fontWeight: 700, color: COLORS.textPrimary}}>
            {PANEL.title}
          </span>
          <span
            style={{
              fontSize: 12,
              fontWeight: 600,
              color: COLORS.textSecondary,
            }}
          >
            Target:{" "}
            <span style={{color: COLORS.blue, fontWeight: 700}}>{PANEL.target}</span>
          </span>
        </div>

        {/* Gate rows. */}
        <div style={{display: "flex", flexDirection: "column", gap: 9, marginBottom: 20}}>
          {PANEL.gates.map((g) => {
            const color = toneColor(g.tone as MetricTone);
            return (
              <div
                key={g.label}
                style={{
                  display: "flex",
                  alignItems: "center",
                  gap: 11,
                  padding: "9px 11px",
                  borderRadius: 9,
                  background: "rgba(255,255,255,0.02)",
                  border: `1px solid ${COLORS.border}`,
                }}
              >
                <span
                  style={{
                    width: 20,
                    height: 20,
                    flexShrink: 0,
                    borderRadius: "50%",
                    display: "flex",
                    alignItems: "center",
                    justifyContent: "center",
                    fontSize: 11,
                    fontWeight: 800,
                    color: "#0B1020",
                    background: color,
                    boxShadow: `0 0 8px ${color}55`,
                  }}
                >
                  {toneGlyph(g.tone as MetricTone)}
                </span>
                <span style={{fontSize: 13.5, color: COLORS.textPrimary}}>{g.label}</span>
              </div>
            );
          })}
        </div>

        {/* Generate narrative button. */}
        <button
          style={{
            width: "100%",
            padding: "13px 0",
            borderRadius: 11,
            border: "none",
            cursor: "default",
            fontFamily: FONT_STACK,
            fontSize: 14,
            fontWeight: 700,
            color: "#fff",
            background: `linear-gradient(135deg, ${COLORS.blue}, ${COLORS.purple})`,
            boxShadow: buttonPressed
              ? `inset 0 2px 8px rgba(0,0,0,0.4)`
              : `0 10px 28px ${COLORS.blue}44`,
            transform: buttonPressed ? "scale(0.98)" : "scale(1)",
            filter: buttonPressed ? "brightness(0.92)" : "none",
          }}
        >
          {PANEL.buttonLabel}
        </button>
      </div>

      {/* Optional narrative reveal. */}
      {narrativeAppear > 0 ? <NarrativePanelMock appear={narrativeAppear} /> : null}
    </div>
  );
};

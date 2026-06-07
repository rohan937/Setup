import React from "react";
import {COLORS, FONT_STACK, MetricTone, SCRIPT} from "../timing";
import {toneColor, toneGlyph} from "./tone";

interface RealityCheckPanelMockProps {
  // 0 -> 1 overall panel fade/rise.
  appear: number;
  // Number of check rows revealed so far (0..checks.length).
  revealCount: number;
  // Show the Turnover hover tooltip.
  showTooltip?: boolean;
}

const PANEL = SCRIPT.reality.panel;

// "Backtest Reality Check" — score, verdict, primary concern, checks list.
export const RealityCheckPanelMock: React.FC<RealityCheckPanelMockProps> = ({
  appear,
  revealCount,
  showTooltip = false,
}) => {
  const a = Math.max(0, Math.min(1, appear));
  const verdictColor = COLORS.warning;

  return (
    <div
      style={{
        position: "relative",
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
          Backtest Reality Check
        </span>
        <span
          style={{
            fontSize: 12,
            fontWeight: 700,
            color: verdictColor,
            background: "rgba(255,181,71,0.12)",
            border: `1px solid rgba(255,181,71,0.3)`,
            borderRadius: 999,
            padding: "4px 12px",
          }}
        >
          {PANEL.verdict}
        </span>
      </div>

      {/* Big score. */}
      <div style={{display: "flex", alignItems: "baseline", gap: 8, marginBottom: 6}}>
        <span
          style={{
            fontSize: 52,
            fontWeight: 800,
            color: verdictColor,
            lineHeight: 1,
            letterSpacing: "-0.03em",
          }}
        >
          {PANEL.score}
        </span>
        <span style={{fontSize: 18, fontWeight: 600, color: COLORS.textMuted}}>
          /{PANEL.max}
        </span>
      </div>

      {/* Primary concern. */}
      <div
        style={{
          fontSize: 13,
          color: COLORS.textSecondary,
          marginBottom: 20,
          lineHeight: 1.4,
        }}
      >
        <span style={{color: COLORS.warning, fontWeight: 700}}>Primary concern: </span>
        {PANEL.primaryConcern}
      </div>

      {/* Checks list. */}
      <div style={{display: "flex", flexDirection: "column", gap: 9}}>
        {PANEL.checks.map((c, i) => {
          const shown = i < revealCount;
          const color = toneColor(c.tone as MetricTone);
          return (
            <div
              key={c.label}
              style={{
                display: "flex",
                alignItems: "center",
                gap: 11,
                opacity: shown ? 1 : 0,
                transform: shown ? "translateX(0)" : "translateX(-8px)",
                transition: "opacity 0.2s, transform 0.2s",
              }}
            >
              <span
                style={{
                  width: 22,
                  height: 22,
                  flexShrink: 0,
                  borderRadius: "50%",
                  display: "flex",
                  alignItems: "center",
                  justifyContent: "center",
                  fontSize: 12,
                  fontWeight: 800,
                  color: "#0B1020",
                  background: color,
                  boxShadow: `0 0 10px ${color}66`,
                }}
              >
                {toneGlyph(c.tone as MetricTone)}
              </span>
              <span style={{fontSize: 13.5, color: COLORS.textPrimary}}>{c.label}</span>
            </div>
          );
        })}
      </div>

      {/* Turnover hover tooltip. */}
      {showTooltip ? (
        <div
          style={{
            position: "absolute",
            right: 28,
            bottom: 70,
            width: 240,
            padding: "12px 14px",
            borderRadius: 12,
            background: COLORS.elevated,
            border: `1px solid ${COLORS.warning}55`,
            boxShadow: `0 16px 40px rgba(0,0,0,0.6), 0 0 24px ${COLORS.warning}22`,
            zIndex: 5,
          }}
        >
          <div
            style={{
              fontSize: 12.5,
              fontWeight: 700,
              color: COLORS.warning,
              marginBottom: 5,
            }}
          >
            {PANEL.tooltip.title}
          </div>
          <div style={{fontSize: 12, color: COLORS.textSecondary, lineHeight: 1.4}}>
            {PANEL.tooltip.body}
          </div>
        </div>
      ) : null}
    </div>
  );
};

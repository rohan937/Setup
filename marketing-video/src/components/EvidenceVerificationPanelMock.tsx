import React from "react";
import {interpolate, useCurrentFrame} from "remotion";
import {COLORS, FONT_STACK, MetricTone, SCRIPT} from "../timing";
import {toneColor, toneGlyph} from "./tone";

interface EvidenceVerificationPanelMockProps {
  // 0 -> 1 overall reveal; also drives sequential row lighting.
  appear: number;
  // Pulse the root-hash icon.
  rootHashGlow?: boolean;
}

const PANEL = SCRIPT.evidence.panel;

// "Evidence Verification" — score, status, evidence chain nodes, root hash.
export const EvidenceVerificationPanelMock: React.FC<
  EvidenceVerificationPanelMockProps
> = ({appear, rootHashGlow = false}) => {
  const frame = useCurrentFrame();
  const a = Math.max(0, Math.min(1, appear));
  const pulse = 0.55 + 0.45 * ((Math.sin(frame * 0.13) + 1) / 2);

  // Rows light up sequentially across the back half of `appear`.
  const rowCount = PANEL.rows.length;

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
          Evidence Verification
        </span>
        <span
          style={{
            fontSize: 12,
            fontWeight: 700,
            color: COLORS.success,
            background: "rgba(0,212,146,0.12)",
            border: `1px solid rgba(0,212,146,0.3)`,
            borderRadius: 999,
            padding: "4px 12px",
            display: "flex",
            alignItems: "center",
            gap: 6,
          }}
        >
          <span
            style={{
              width: 7,
              height: 7,
              borderRadius: "50%",
              background: COLORS.success,
              boxShadow: `0 0 8px ${COLORS.success}`,
            }}
          />
          {PANEL.status}
        </span>
      </div>

      {/* Score. */}
      <div style={{display: "flex", alignItems: "baseline", gap: 8, marginBottom: 20}}>
        <span
          style={{
            fontSize: 52,
            fontWeight: 800,
            color: COLORS.success,
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

      {/* Evidence chain nodes lighting up sequentially. */}
      <div style={{display: "flex", flexDirection: "column", gap: 8}}>
        {PANEL.rows.map((row, i) => {
          const start = 0.4 + (i / rowCount) * 0.5;
          const lit = interpolate(a, [start, start + 0.1], [0, 1], {
            extrapolateLeft: "clamp",
            extrapolateRight: "clamp",
          });
          const color = toneColor(row.tone as MetricTone);
          return (
            <div
              key={row.label}
              style={{
                display: "flex",
                alignItems: "center",
                gap: 11,
                padding: "8px 10px",
                borderRadius: 9,
                background: lit > 0.5 ? "rgba(0,212,146,0.06)" : "rgba(255,255,255,0.02)",
                border: `1px solid ${lit > 0.5 ? "rgba(0,212,146,0.18)" : COLORS.border}`,
                opacity: 0.4 + lit * 0.6,
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
                  boxShadow: lit > 0.5 ? `0 0 ${8 * lit}px ${color}` : "none",
                }}
              >
                {toneGlyph(row.tone as MetricTone)}
              </span>
              <span style={{fontSize: 13, color: COLORS.textPrimary}}>{row.label}</span>
            </div>
          );
        })}
      </div>

      {/* Warning row. */}
      <div
        style={{
          display: "flex",
          alignItems: "center",
          gap: 10,
          marginTop: 12,
          padding: "9px 11px",
          borderRadius: 9,
          background: "rgba(255,181,71,0.08)",
          border: `1px solid rgba(255,181,71,0.22)`,
        }}
      >
        <span style={{fontSize: 13, color: COLORS.warning, fontWeight: 700}}>⚠</span>
        <span style={{fontSize: 12.5, color: COLORS.textSecondary}}>{PANEL.warning}</span>
      </div>

      {/* Root hash with glowing icon. */}
      <div
        style={{
          display: "flex",
          alignItems: "center",
          gap: 10,
          marginTop: 14,
          paddingTop: 14,
          borderTop: `1px solid ${COLORS.border}`,
        }}
      >
        <span
          style={{
            width: 26,
            height: 26,
            borderRadius: 8,
            display: "flex",
            alignItems: "center",
            justifyContent: "center",
            fontSize: 13,
            background: `linear-gradient(135deg, ${COLORS.blue}, ${COLORS.purple})`,
            boxShadow: rootHashGlow
              ? `0 0 ${10 + pulse * 14}px ${COLORS.purple}`
              : `0 0 8px ${COLORS.purple}66`,
            color: "#fff",
          }}
        >
          🔗
        </span>
        <span style={{fontSize: 12, color: COLORS.textMuted, fontWeight: 600}}>
          Root hash
        </span>
        <span
          style={{
            fontSize: 12.5,
            color: COLORS.textPrimary,
            fontFamily: "ui-monospace, SFMono-Regular, Menlo, monospace",
            fontWeight: 600,
          }}
        >
          {PANEL.rootHash}
        </span>
      </div>
    </div>
  );
};

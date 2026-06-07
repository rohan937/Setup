import React from "react";
import {COLORS, FONT_STACK} from "../timing";

interface SidebarMockProps {
  // Label of the active nav item.
  active?: string;
  width?: number;
}

interface NavItem {
  label: string;
  icon: string;
}

const groups: {heading: string; items: NavItem[]}[] = [
  {
    heading: "Workspace",
    items: [
      {label: "Home", icon: "▦"},
      {label: "Strategies", icon: "≣"},
      {label: "Portfolio", icon: "◍"},
    ],
  },
  {
    heading: "Oversight",
    items: [
      {label: "Governance", icon: "⚖"},
      {label: "Command", icon: "◆"},
    ],
  },
];

// Narrow dark sidebar with grouped nav + active item highlight.
export const SidebarMock: React.FC<SidebarMockProps> = ({
  active = "Strategies",
  width = 188,
}) => {
  return (
    <div
      style={{
        width,
        flexShrink: 0,
        height: "100%",
        borderRight: `1px solid ${COLORS.border}`,
        background: "rgba(0,0,0,0.18)",
        padding: "18px 12px",
        fontFamily: FONT_STACK,
        display: "flex",
        flexDirection: "column",
        gap: 22,
      }}
    >
      {groups.map((g) => (
        <div key={g.heading} style={{display: "flex", flexDirection: "column", gap: 4}}>
          <div
            style={{
              fontSize: 10.5,
              fontWeight: 700,
              letterSpacing: "0.08em",
              textTransform: "uppercase",
              color: COLORS.textMuted,
              padding: "0 10px 6px",
            }}
          >
            {g.heading}
          </div>
          {g.items.map((it) => {
            const isActive = it.label === active;
            return (
              <div
                key={it.label}
                style={{
                  position: "relative",
                  display: "flex",
                  alignItems: "center",
                  gap: 10,
                  padding: "9px 12px",
                  borderRadius: 9,
                  background: isActive ? "rgba(79,140,255,0.12)" : "transparent",
                  color: isActive ? COLORS.textPrimary : COLORS.textSecondary,
                  fontSize: 13.5,
                  fontWeight: isActive ? 600 : 500,
                }}
              >
                {isActive ? (
                  <span
                    style={{
                      position: "absolute",
                      left: 0,
                      top: 8,
                      bottom: 8,
                      width: 3,
                      borderRadius: 3,
                      background: COLORS.blue,
                      boxShadow: `0 0 10px ${COLORS.blue}`,
                    }}
                  />
                ) : null}
                <span
                  style={{
                    width: 16,
                    textAlign: "center",
                    color: isActive ? COLORS.blue : COLORS.textMuted,
                    fontSize: 13,
                  }}
                >
                  {it.icon}
                </span>
                {it.label}
              </div>
            );
          })}
        </div>
      ))}
    </div>
  );
};

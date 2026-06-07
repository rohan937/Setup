import React from "react";
import {COLORS, FONT_STACK} from "../timing";

interface TabBarMockProps {
  tabs?: string[];
  // Label of the active tab.
  active: string;
}

const DEFAULT_TABS = [
  "Overview",
  "Evidence",
  "Reality",
  "Lineage",
  "Governance",
  "Reports",
];

// Strategy-workspace tab bar with an animated active underline.
export const TabBarMock: React.FC<TabBarMockProps> = ({
  tabs = DEFAULT_TABS,
  active,
}) => {
  return (
    <div
      style={{
        display: "flex",
        alignItems: "center",
        gap: 4,
        borderBottom: `1px solid ${COLORS.border}`,
        fontFamily: FONT_STACK,
      }}
    >
      {tabs.map((tab) => {
        const isActive = tab === active;
        return (
          <div
            key={tab}
            style={{
              position: "relative",
              padding: "11px 16px",
              fontSize: 13.5,
              fontWeight: isActive ? 700 : 500,
              color: isActive ? COLORS.textPrimary : COLORS.textSecondary,
              cursor: "default",
            }}
          >
            {tab}
            {isActive ? (
              <span
                style={{
                  position: "absolute",
                  left: 12,
                  right: 12,
                  bottom: -1,
                  height: 2.5,
                  borderRadius: 3,
                  background: `linear-gradient(90deg, ${COLORS.blue}, ${COLORS.purple})`,
                  boxShadow: `0 0 12px ${COLORS.blue}aa`,
                }}
              />
            ) : null}
          </div>
        );
      })}
    </div>
  );
};

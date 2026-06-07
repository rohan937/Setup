import React from "react";
import {COLORS, FONT_STACK} from "../timing";

interface QuantFidelityLogoTextProps {
  fontSize?: number;
}

export const QuantFidelityLogoText: React.FC<QuantFidelityLogoTextProps> = ({
  fontSize = 56,
}) => {
  return (
    <div
      style={{
        fontFamily: FONT_STACK,
        fontSize,
        fontWeight: 800,
        letterSpacing: "-0.03em",
        display: "inline-flex",
        alignItems: "baseline",
      }}
    >
      <span style={{color: COLORS.textPrimary, fontWeight: 700}}>Quant</span>
      <span
        style={{
          background: `linear-gradient(90deg, ${COLORS.blue}, ${COLORS.purple})`,
          WebkitBackgroundClip: "text",
          backgroundClip: "text",
          WebkitTextFillColor: "transparent",
          color: COLORS.blue,
          fontWeight: 800,
        }}
      >
        Fidelity
      </span>
    </div>
  );
};

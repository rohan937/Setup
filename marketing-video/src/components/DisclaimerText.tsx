import React from "react";
import {COLORS, FONT_STACK} from "../timing";

interface DisclaimerTextProps {
  text: string;
  opacity?: number;
}

export const DisclaimerText: React.FC<DisclaimerTextProps> = ({
  text,
  opacity = 1,
}) => {
  return (
    <div
      style={{
        fontFamily: FONT_STACK,
        fontSize: 18,
        fontWeight: 400,
        color: COLORS.textSecondary,
        opacity: opacity * 0.7,
        letterSpacing: "0.01em",
      }}
    >
      {text}
    </div>
  );
};

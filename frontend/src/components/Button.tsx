import type { ButtonHTMLAttributes, ReactNode } from "react";

type ButtonVariant = "primary" | "secondary" | "ghost" | "danger";
type ButtonSize = "sm" | "md";

interface ButtonProps extends ButtonHTMLAttributes<HTMLButtonElement> {
  variant?: ButtonVariant;
  size?: ButtonSize;
  loading?: boolean;
  children?: ReactNode;
}

const VARIANTS: Record<ButtonVariant, string> = {
  // Muted institutional blue — solid, restrained, no neon.
  primary:
    "bg-brand text-text-primary border border-brand hover:bg-brand-600 hover:border-brand-600",
  // Quiet elevated surface.
  secondary:
    "bg-bg-600 text-text-secondary border border-border hover:bg-bg-600/70 hover:text-text-primary hover:border-border-strong",
  // Transparent until hover.
  ghost:
    "bg-transparent text-text-muted border border-transparent hover:bg-bg-600/60 hover:text-text-secondary",
  // Desaturated danger.
  danger:
    "bg-transparent text-fidelity-low border border-fidelity-low/50 hover:bg-fidelity-low/10 hover:border-fidelity-low",
};

const SIZES: Record<ButtonSize, string> = {
  sm: "h-7 px-2.5 text-2xs gap-1.5",
  md: "h-9 px-3.5 text-xs gap-2",
};

export default function Button({
  variant = "secondary",
  size = "md",
  loading = false,
  disabled,
  children,
  className = "",
  type = "button",
  ...rest
}: ButtonProps) {
  const isDisabled = disabled || loading;
  return (
    <button
      type={type}
      disabled={isDisabled}
      className={[
        "inline-flex items-center justify-center rounded-control font-medium tracking-tight",
        "transition-colors focus:outline-none focus-visible:ring-1 focus-visible:ring-brand/60",
        "disabled:cursor-not-allowed disabled:opacity-50",
        VARIANTS[variant],
        SIZES[size],
        className,
      ]
        .filter(Boolean)
        .join(" ")}
      {...rest}
    >
      {loading && (
        <span
          aria-hidden
          className="h-3 w-3 animate-spin rounded-full border border-current border-t-transparent"
        />
      )}
      {children}
    </button>
  );
}

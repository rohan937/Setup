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
  // Solid institutional blue — lifts lighter + premium glow on hover.
  primary:
    "bg-brand text-white border border-brand shadow-panel hover:bg-brand-600 hover:border-brand-600 hover:shadow-glow-primary-lg",
  // Quiet elevated surface — brightens text + border on hover.
  secondary:
    "bg-bg-600 text-text-secondary border border-border hover:bg-bg-600 hover:text-text-primary hover:border-border-strong",
  // Transparent until hover.
  ghost:
    "bg-transparent text-text-muted border border-transparent hover:bg-bg-600/60 hover:text-text-primary",
  // Danger outline — fills with a tint + subtle glow on hover.
  danger:
    "bg-transparent text-fidelity-low border border-fidelity-low/50 hover:bg-fidelity-low/10 hover:border-fidelity-low hover:shadow-glow-danger-lg",
};

const SIZES: Record<ButtonSize, string> = {
  sm: "h-8 px-3 text-xs gap-1.5",
  md: "h-10 px-4 text-sm gap-2",
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
        "transition-all duration-200 focus:outline-none focus-visible:ring-2 focus-visible:ring-brand/50 focus-visible:ring-offset-0",
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

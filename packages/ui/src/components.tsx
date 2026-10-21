import React from "react";

const cx = (...parts: (string | false | undefined)[]) => parts.filter(Boolean).join(" ");

const BUTTON_CLASS = {
  primary: "btn-primary",
  outline: "btn-ghost",
  dark: "btn-dark",
  danger: "btn-danger",
} as const;

export interface ButtonProps extends React.ButtonHTMLAttributes<HTMLButtonElement> {
  variant?: keyof typeof BUTTON_CLASS;
  size?: "md" | "icon";
}

export function Button({
  variant = "primary",
  size = "md",
  className,
  type = "button",
  ...rest
}: ButtonProps) {
  return (
    <button
      type={type}
      className={cx(BUTTON_CLASS[variant], size === "icon" && "btn-icon", className)}
      {...rest}
    />
  );
}

export function Card({ className, ...rest }: React.HTMLAttributes<HTMLDivElement>) {
  return <div className={cx("mise-card", className)} {...rest} />;
}

export interface StatTileProps {
  label: string;
  value: React.ReactNode;
  sub?: React.ReactNode;
}

export function StatTile({ label, value, sub }: StatTileProps) {
  return (
    <div className="stat-tile space-y-1">
      <span className="block text-xs font-semibold uppercase tracking-wider text-ink-muted">
        {label}
      </span>
      <div className="font-serif text-3xl font-bold text-ink">{value}</div>
      {sub && <div className="text-xs text-ink-muted">{sub}</div>}
    </div>
  );
}

export interface PageHeaderProps {
  title: React.ReactNode;
  subtitle?: React.ReactNode;
  actions?: React.ReactNode;
}

export function PageHeader({ title, subtitle, actions }: PageHeaderProps) {
  return (
    <div className="flex flex-wrap items-start justify-between gap-4">
      <div>
        <h1 className="text-3xl text-ink">{title}</h1>
        {subtitle && <p className="mt-1 text-sm text-ink-muted">{subtitle}</p>}
      </div>
      {actions}
    </div>
  );
}

export function Badge({ className, ...rest }: React.HTMLAttributes<HTMLSpanElement>) {
  return <span className={cx("chip chip-neutral", className)} {...rest} />;
}

const STATUS_ICON = { contains: "⚠", unverified: "?", safe: "✓" } as const;

export interface StatusChipProps extends React.HTMLAttributes<HTMLSpanElement> {
  tone: keyof typeof STATUS_ICON;
  [dataAttribute: `data-${string}`]: string | undefined;
}

export function StatusChip({ tone, className, children, ...rest }: StatusChipProps) {
  return (
    <span className={cx("chip", `chip-${tone}`, className)} {...rest}>
      <span aria-hidden="true">{STATUS_ICON[tone]}</span>
      {children}
    </span>
  );
}

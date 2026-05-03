import { useId, useState, type ReactNode } from "react";

/**
 * <Disclosure> — generic chevron-driven collapsible.
 *
 * Aesthetic only. No backend wiring. Used to build the two-tier collapsible
 * nav (HosakaMenu) and to tighten panel chrome. Honors `defaultOpen`,
 * controlled `open`/`onOpenChange`, and a `level` prop for nested styling
 * (`disclosure--l1`, `disclosure--l2`).
 */
export interface DisclosureProps {
  label: ReactNode;
  glyph?: ReactNode;
  children: ReactNode;
  defaultOpen?: boolean;
  open?: boolean;
  onOpenChange?: (next: boolean) => void;
  level?: 1 | 2;
  className?: string;
}

export function Disclosure({
  label,
  glyph,
  children,
  defaultOpen = false,
  open,
  onOpenChange,
  level = 1,
  className = "",
}: DisclosureProps) {
  const [internal, setInternal] = useState(defaultOpen);
  const isControlled = typeof open === "boolean";
  const isOpen = isControlled ? open : internal;
  const id = useId();

  const toggle = () => {
    const next = !isOpen;
    if (!isControlled) setInternal(next);
    onOpenChange?.(next);
  };

  return (
    <div className={`disclosure disclosure--l${level} ${isOpen ? "is-open" : ""} ${className}`}>
      <button
        type="button"
        className="disclosure-summary"
        aria-expanded={isOpen}
        aria-controls={id}
        onClick={toggle}
      >
        <span className="disclosure-chev" aria-hidden="true">{isOpen ? "▾" : "▸"}</span>
        {glyph && <span className="disclosure-glyph">{glyph}</span>}
        <span className="disclosure-label">{label}</span>
      </button>
      <div
        id={id}
        className="disclosure-body"
        role="region"
        hidden={!isOpen}
      >
        {children}
      </div>
    </div>
  );
}

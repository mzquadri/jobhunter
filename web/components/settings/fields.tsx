"use client";

import { useState, type ReactNode } from "react";
import { X } from "lucide-react";
import { Badge, Button, Input } from "@/components/ui/primitives";
import { cn } from "@/lib/utils";

/**
 * One labelled control.
 *
 * The hint sits under the label rather than in a tooltip: these settings change
 * what the scanner does next, and a setting you have to hover to understand is
 * a setting you will get wrong.
 */
export function Field({
  label,
  hint,
  htmlFor,
  children,
  className,
}: {
  label: string;
  hint?: string;
  htmlFor?: string;
  children: ReactNode;
  className?: string;
}) {
  return (
    <div className={cn("min-w-0", className)}>
      <label htmlFor={htmlFor} className="block text-[12px] font-medium">
        {label}
      </label>
      {hint && <p className="mb-1.5 mt-0.5 text-[11px] text-muted-foreground">{hint}</p>}
      <div className={cn(!hint && "mt-1.5")}>{children}</div>
    </div>
  );
}

export function Check({
  label,
  hint,
  checked,
  onChange,
}: {
  label: string;
  hint?: string;
  checked: boolean;
  onChange: (value: boolean) => void;
}) {
  return (
    <label className="flex cursor-pointer items-start gap-2.5 rounded-md px-1 py-1.5 hover:bg-accent/50">
      <input
        type="checkbox"
        checked={checked}
        onChange={(e) => onChange(e.target.checked)}
        className="mt-0.5 size-3.5 shrink-0 accent-[var(--color-info)]"
      />
      <span className="min-w-0">
        <span className="block text-[12.5px]">{label}</span>
        {hint && <span className="mt-0.5 block text-[11px] text-muted-foreground">{hint}</span>}
      </span>
    </label>
  );
}

/**
 * A list of short strings.
 *
 * Used for the lists that drive matching — target job titles, cities to skip,
 * skills. Comma or Enter commits a value; nothing is added silently on blur,
 * because a half-typed word becoming a search term is worse than losing it.
 */
export function TagInput({
  values,
  onChange,
  placeholder,
  id,
}: {
  values: string[];
  onChange: (values: string[]) => void;
  placeholder?: string;
  id?: string;
}) {
  const [draft, setDraft] = useState("");

  function commit(raw: string) {
    const additions = raw
      .split(",")
      .map((v) => v.trim())
      .filter((v) => v && !values.some((existing) => existing.toLowerCase() === v.toLowerCase()));
    if (additions.length) onChange([...values, ...additions]);
    setDraft("");
  }

  return (
    <div className="rounded-md border border-input bg-background p-1.5">
      {values.length > 0 && (
        <ul className="mb-1.5 flex flex-wrap gap-1">
          {values.map((value) => (
            <li key={value}>
              <Badge variant="default" className="pr-0.5">
                <span className="max-w-56 truncate">{value}</span>
                <button
                  type="button"
                  aria-label={`Remove ${value}`}
                  onClick={() => onChange(values.filter((v) => v !== value))}
                  className="rounded p-0.5 text-muted-foreground hover:bg-background hover:text-foreground"
                >
                  <X className="size-3" />
                </button>
              </Badge>
            </li>
          ))}
        </ul>
      )}
      <Input
        id={id}
        value={draft}
        onChange={(e) => setDraft(e.target.value)}
        onKeyDown={(e) => {
          if (e.key === "Enter" || e.key === ",") {
            e.preventDefault();
            commit(draft);
          } else if (e.key === "Backspace" && !draft && values.length) {
            onChange(values.slice(0, -1));
          }
        }}
        placeholder={placeholder ?? "Type and press Enter"}
        className="h-7 border-0 px-1.5 text-[12.5px] focus-visible:ring-0"
      />
    </div>
  );
}

/**
 * A section with its own save button.
 *
 * Each section saves independently because the backend merges one section at
 * a time. A single page-wide Save would have to send the whole document back
 * and would overwrite anything a scan changed while the page was open.
 */
export function Section({
  title,
  hint,
  dirty,
  saving,
  onSave,
  onReset,
  children,
}: {
  title: string;
  hint?: string;
  dirty: boolean;
  saving: boolean;
  onSave: () => void;
  onReset: () => void;
  children: ReactNode;
}) {
  return (
    <section className="rounded-lg border border-border bg-card">
      <header className="flex items-start gap-3 border-b border-border px-4 py-3">
        <div className="min-w-0 flex-1">
          <h2 className="text-[13px] font-semibold tracking-tight">{title}</h2>
          {hint && <p className="mt-0.5 text-[11.5px] text-muted-foreground">{hint}</p>}
        </div>
        {dirty && (
          <div className="flex shrink-0 items-center gap-1.5">
            <Button variant="ghost" size="sm" onClick={onReset} disabled={saving}>
              Discard
            </Button>
            <Button size="sm" onClick={onSave} disabled={saving}>
              {saving ? "Saving" : "Save changes"}
            </Button>
          </div>
        )}
      </header>
      <div className="space-y-4 p-4">{children}</div>
    </section>
  );
}

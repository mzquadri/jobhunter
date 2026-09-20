"use client";

import type { JobQuery, SortKey } from "@/lib/types";

export type FilterKey =
  | "all"
  | "fresh"
  | "new"
  | "dream"
  | "de"
  | "ch"
  | "clean"
  | "starred"
  | "applied";

/** Each chip is one saved query. Naming them this way keeps the query logic in
 *  one place instead of scattered through the list component. */
export const FILTERS: { key: FilterKey; label: string; query: JobQuery }[] = [
  { key: "all", label: "All", query: {} },
  { key: "fresh", label: "48 hours", query: { fresh_hours: 48 } },
  { key: "new", label: "New", query: { only_new: true } },
  { key: "dream", label: "Dream", query: { tier: "DREAM" } },
  { key: "de", label: "Germany", query: { country: "de" } },
  { key: "ch", label: "Switzerland", query: { country: "ch" } },
  { key: "clean", label: "No warnings", query: { only_clean: true } },
  { key: "starred", label: "Starred", query: { only_starred: true } },
  { key: "applied", label: "Applied", query: { status: "applied" } },
];

export function Filters({
  active,
  onFilter,
  search,
  onSearch,
  sort,
  onSort,
  counts,
  searchRef,
}: {
  active: FilterKey;
  onFilter: (key: FilterKey) => void;
  search: string;
  onSearch: (value: string) => void;
  sort: SortKey;
  onSort: (value: SortKey) => void;
  counts: Partial<Record<FilterKey, number>>;
  searchRef: React.RefObject<HTMLInputElement | null>;
}) {
  return (
    <div className="sticky top-0 z-20 flex flex-wrap items-center gap-2 border-b border-rule bg-paper py-3">
      <input
        ref={searchRef}
        type="search"
        value={search}
        onChange={(e) => onSearch(e.target.value)}
        placeholder="Search company, role, skill, city   (press /)"
        aria-label="Search postings"
        className="min-w-[170px] flex-1 border border-rule bg-panel px-3 py-2 text-ink placeholder:text-ink-3"
      />

      <div className="flex flex-wrap gap-1.5">
        {FILTERS.map((f) => (
          <button
            key={f.key}
            type="button"
            aria-pressed={active === f.key}
            onClick={() => onFilter(f.key)}
            className={`border px-3 py-1.5 text-[13px] whitespace-nowrap ${
              active === f.key
                ? "border-ink bg-ink text-paper"
                : "border-rule text-ink-2 hover:text-ink"
            }`}
          >
            {f.label}
            {counts[f.key] !== undefined && (
              <span className="ml-1.5 text-[11px] opacity-65">{counts[f.key]}</span>
            )}
          </button>
        ))}
      </div>

      <select
        value={sort}
        onChange={(e) => onSort(e.target.value as SortKey)}
        aria-label="Sort order"
        className="border border-rule bg-transparent px-3 py-1.5 text-[13px] text-ink"
      >
        <option value="newest">Newest first</option>
        <option value="score">Best match first</option>
        <option value="company">By company</option>
      </select>
    </div>
  );
}

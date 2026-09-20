import type { Stats } from "@/lib/types";
import { duration } from "@/lib/format";

export function Watchlist({ items }: { items: Stats["watchlist"] }) {
  if (items.length === 0) return null;
  return (
    <section className="mt-11">
      <h2 className="mb-1 text-[15px] font-semibold">Check these by hand</h2>
      <p className="mb-3.5 max-w-[70ch] text-[13px] text-ink-2">
        These career sites build their listings with JavaScript and publish no open feed, so nothing
        can read them automatically. Opening each one takes about a minute; once a week is enough.
      </p>
      <ul className="grid list-none grid-cols-[repeat(auto-fill,minmax(200px,1fr))] p-0">
        {items.map((w) => (
          <li key={w.url} className="-mt-px -ml-px border border-hair">
            <a
              href={w.url}
              target="_blank"
              rel="noopener noreferrer"
              className="block bg-panel px-3 py-2.5 hover:bg-sunk"
            >
              {w.name}
            </a>
          </li>
        ))}
      </ul>
    </section>
  );
}

export function SweepPanel({ sweep }: { sweep: Stats["last_sweep"] }) {
  if (!sweep) return null;
  const problems = sweep.problems ?? [];
  return (
    <section className="mt-11">
      <h2 className="mb-1 text-[15px] font-semibold">Sources</h2>
      <p className="mb-3.5 max-w-[70ch] text-[13px] text-ink-2">
        A source that stops answering is reported rather than swallowed, because a silent sweep that
        found nothing looks exactly like a sweep where nothing was posted.
      </p>
      <details className="border border-hair bg-panel">
        <summary className="cursor-pointer px-3.5 py-2.5 text-[13px]">
          {sweep.sources_ok} of {sweep.sources_total} sources answered · {sweep.postings_fetched}{" "}
          postings read in {duration(sweep.duration_ms)} · {problems.length} problems
        </summary>
        <ul className="list-none px-3.5 pb-3 text-[12px] text-ink-2">
          {problems.length === 0 ? (
            <li className="border-t border-hair py-1">Every source answered.</li>
          ) : (
            problems.map((p, i) => (
              <li key={`${p.source}-${i}`} className="border-t border-hair py-1">
                <span className="inline-block min-w-[200px] text-ink">{p.source}</span>
                {p.detail}
              </li>
            ))
          )}
        </ul>
      </details>
    </section>
  );
}

export function EmptyState({ title, hint }: { title: string; hint: string }) {
  return (
    <div className="border border-dashed border-rule px-4 py-14 text-center text-ink-2">
      <b className="mb-1.5 block text-[16px] text-ink">{title}</b>
      {hint}
    </div>
  );
}

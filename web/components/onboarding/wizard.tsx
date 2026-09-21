"use client";

import { useCallback, useEffect, useMemo, useState, type ReactNode } from "react";
import { useRouter } from "next/navigation";
import {
  ArrowLeft,
  ArrowRight,
  Check as CheckIcon,
  Loader2,
  Search,
  ShieldCheck,
} from "lucide-react";
import { toast } from "sonner";
import { api, type CompanyOut } from "@/lib/api";
import { useScanState } from "@/lib/hooks";
import { Mark, Wordmark } from "@/components/brand/logo";
import { Field, TagInput } from "@/components/settings/fields";
import {
  Badge,
  Button,
  Card,
  Input,
  Progress,
  Select,
  Skeleton,
} from "@/components/ui/primitives";
import { cn } from "@/lib/utils";

type Draft = {
  name: string;
  primary_city: string;
  german_level: string;
  years_experience: number;
  education_level: string;
  titles: string[];
  target_salary_eur: number;
  max_age_days: number;
  tiers: Record<string, string[]>;
  exclude: string[];
  min_score: number;
};

const STEPS = ["Welcome", "You", "Roles", "Places", "Employers", "First scan"] as const;

const GERMAN_LEVELS: [string, string][] = [
  ["none", "None"],
  ["a1", "A1 — a few words"],
  ["a2", "A2 — basics"],
  ["b1", "B1 — conversational"],
  ["b2", "B2 — working proficiency"],
  ["c1", "C1 — fluent"],
  ["c2", "C2 — near native"],
  ["native", "Native"],
];

/**
 * First run.
 *
 * Six short steps, each one thing. Everything here is pre-filled from the
 * defaults CareerOS ships with, so a person who just wants to get going can
 * press Next six times and have a working search — and a person who cares can
 * change any of it now or later in Settings.
 */
export function OnboardingWizard() {
  const router = useRouter();
  const [step, setStep] = useState(0);
  const [draft, setDraft] = useState<Draft | null>(null);
  const [saving, setSaving] = useState(false);

  useEffect(() => {
    api
      .settings()
      .then(({ profile }) => {
        const p = profile as Record<string, Record<string, unknown>>;
        const candidate = (p.candidate ?? {}) as Record<string, unknown>;
        const search = (p.search ?? {}) as Record<string, unknown>;
        const roles = (p.roles ?? {}) as Record<string, unknown>;
        const locations = (p.locations ?? {}) as Record<string, unknown>;
        const tiers = (locations.tiers ?? {}) as Record<string, string[]>;
        setDraft({
          name: String(candidate.name ?? ""),
          primary_city: String(candidate.primary_city ?? "Munich"),
          german_level: String(candidate.german_level ?? "a2"),
          years_experience: Number(candidate.years_experience ?? 1.5),
          education_level: String(candidate.education_level ?? "msc"),
          titles: (roles.include as string[]) ?? [],
          target_salary_eur: Number(search.target_salary_eur ?? 70000),
          max_age_days: Number(search.max_age_days ?? 14),
          min_score: Number(search.min_score ?? 25),
          tiers,
          exclude: (locations.exclude as string[]) ?? [],
        });
      })
      .catch(() => toast.error("Could not load the defaults. Is the backend running?"));
  }, []);

  function set<K extends keyof Draft>(key: K, value: Draft[K]) {
    setDraft((d) => (d ? { ...d, [key]: value } : d));
  }

  const document = useMemo(
    () =>
      draft
        ? {
            candidate: {
              name: draft.name,
              primary_city: draft.primary_city,
              german_level: draft.german_level,
              years_experience: draft.years_experience,
              education_level: draft.education_level,
            },
            search: {
              target_salary_eur: draft.target_salary_eur,
              max_age_days: draft.max_age_days,
              min_score: draft.min_score,
            },
            roles: { include: draft.titles },
            // The whole tiers map, not just tier 1: the backend replaces a
            // nested object wholesale, so a partial map would delete the rest.
            locations: { tiers: draft.tiers, exclude: draft.exclude },
          }
        : null,
    [draft],
  );

  const finish = useCallback(async () => {
    if (!document) return;
    setSaving(true);
    try {
      await api.completeOnboarding(document);
      toast.success("You are set up", { description: "CareerOS will keep scanning in the background." });
      router.push("/");
      router.refresh();
    } catch (e) {
      toast.error(e instanceof Error ? e.message : "Could not save your setup.");
    } finally {
      setSaving(false);
    }
  }, [document, router]);

  if (!draft) {
    return (
      <div className="mx-auto w-full max-w-2xl space-y-4 p-8">
        <Skeleton className="h-10 w-48" />
        <Skeleton className="h-64 w-full" />
      </div>
    );
  }

  const last = step === STEPS.length - 1;

  return (
    <div className="mx-auto flex min-h-screen w-full max-w-2xl flex-col justify-center p-6">
      <header className="mb-5">
        <Wordmark />
        <ol className="mt-4 flex items-center gap-1.5" aria-label="Setup progress">
          {STEPS.map((name, i) => (
            <li key={name} className="flex-1">
              <span
                className={cn(
                  "block h-0.5 rounded-full transition-colors",
                  i < step ? "bg-ok" : i === step ? "bg-foreground" : "bg-border",
                )}
              />
              <span
                className={cn(
                  "mt-1.5 block text-[10.5px]",
                  i === step ? "text-foreground" : "text-muted-foreground",
                )}
              >
                {name}
              </span>
            </li>
          ))}
        </ol>
      </header>

      <Card className="p-5">
        {step === 0 && <WelcomeStep />}

        {step === 1 && (
          <StepBody
            title="A little about you"
            hint="This is what every posting is scored against."
          >
            <div className="grid gap-4 sm:grid-cols-2">
              <Field label="Your name" htmlFor="ob-name">
                <Input
                  id="ob-name"
                  value={draft.name}
                  onChange={(e) => set("name", e.target.value)}
                  placeholder="So the drafts can sign themselves"
                  className="h-8 text-[13px]"
                />
              </Field>
              <Field label="Where you are based" htmlFor="ob-city">
                <Input
                  id="ob-city"
                  value={draft.primary_city}
                  onChange={(e) => set("primary_city", e.target.value)}
                  className="h-8 text-[13px]"
                />
              </Field>
              <Field label="Years of experience" htmlFor="ob-years">
                <Input
                  id="ob-years"
                  type="number"
                  min={0}
                  max={50}
                  step={0.5}
                  value={draft.years_experience}
                  onChange={(e) => set("years_experience", Number(e.target.value))}
                  className="h-8 text-[13px]"
                />
              </Field>
              <Field label="Highest degree" htmlFor="ob-edu">
                <Select
                  id="ob-edu"
                  value={draft.education_level}
                  onChange={(e) => set("education_level", e.target.value)}
                  className="h-8 w-full text-[13px]"
                >
                  <option value="bsc">Bachelor</option>
                  <option value="msc">Master</option>
                  <option value="phd">Doctorate</option>
                </Select>
              </Field>
            </div>

            <Field
              label="Your German"
              htmlFor="ob-de"
              hint="Decides how hard a German requirement counts against a role, rather than hiding those roles."
            >
              <Select
                id="ob-de"
                value={draft.german_level}
                onChange={(e) => set("german_level", e.target.value)}
                className="h-8 w-full max-w-sm text-[13px]"
              >
                {GERMAN_LEVELS.map(([value, label]) => (
                  <option key={value} value={value}>
                    {label}
                  </option>
                ))}
              </Select>
            </Field>
          </StepBody>
        )}

        {step === 2 && (
          <StepBody title="What are you looking for?" hint="A posting has to match one of these titles.">
            <Field label="Job titles">
              <TagInput
                values={draft.titles}
                onChange={(values) => set("titles", values)}
                placeholder="machine learning engineer"
              />
            </Field>

            <div className="grid gap-4 sm:grid-cols-2">
              <Field label="Target salary (EUR per year)" htmlFor="ob-salary">
                <Input
                  id="ob-salary"
                  type="number"
                  min={0}
                  step={1000}
                  value={draft.target_salary_eur}
                  onChange={(e) => set("target_salary_eur", Number(e.target.value))}
                  className="h-8 text-[13px]"
                />
              </Field>
              <Field
                label={`Only roles posted in the last ${draft.max_age_days} days`}
                htmlFor="ob-age"
              >
                <input
                  id="ob-age"
                  type="range"
                  min={1}
                  max={60}
                  value={draft.max_age_days}
                  onChange={(e) => set("max_age_days", Number(e.target.value))}
                  className="w-full accent-[var(--color-info)]"
                />
              </Field>
            </div>
          </StepBody>
        )}

        {step === 3 && (
          <StepBody
            title="Where would you work?"
            hint="Roles outside these places score lower, and anything you exclude is never shown."
          >
            <Field label="Cities and countries you want most">
              <TagInput
                values={draft.tiers["1"] ?? []}
                onChange={(values) => set("tiers", { ...draft.tiers, 1: values })}
                placeholder="Munich, Zurich, Remote"
              />
            </Field>
            <Field label="Never show me roles in">
              <TagInput
                values={draft.exclude}
                onChange={(values) => set("exclude", values)}
                placeholder="Add a place to skip"
              />
            </Field>
          </StepBody>
        )}

        {step === 4 && <EmployersStep />}

        {step === 5 && <ScanStep saving={saving} />}

        <footer className="mt-6 flex items-center gap-2 border-t border-border pt-4">
          {step > 0 && (
            <Button variant="ghost" size="sm" onClick={() => setStep((s) => s - 1)}>
              <ArrowLeft /> Back
            </Button>
          )}
          <span className="ml-auto flex items-center gap-2">
            {!last && step > 0 && (
              <Button variant="ghost" size="sm" onClick={finish} disabled={saving}>
                Skip the rest
              </Button>
            )}
            {last ? (
              <Button size="sm" onClick={finish} disabled={saving}>
                {saving ? <Loader2 className="animate-spin" /> : <CheckIcon />}
                {saving ? "Saving" : "Open CareerOS"}
              </Button>
            ) : (
              <Button size="sm" onClick={() => setStep((s) => s + 1)}>
                {step === 0 ? "Get started" : "Next"} <ArrowRight />
              </Button>
            )}
          </span>
        </footer>
      </Card>
    </div>
  );
}

/* -------------------------------------------------------------------------- */

function StepBody({
  title,
  hint,
  children,
}: {
  title: string;
  hint?: string;
  children: ReactNode;
}) {
  return (
    <div className="space-y-4">
      <div>
        <h1 className="text-[16px] font-semibold tracking-tight">{title}</h1>
        {hint && <p className="mt-0.5 text-[12px] text-muted-foreground">{hint}</p>}
      </div>
      {children}
    </div>
  );
}

function WelcomeStep() {
  return (
    <div className="space-y-4">
      <Mark className="size-9" />
      <div>
        <h1 className="text-[18px] font-semibold tracking-tight">Welcome to CareerOS</h1>
        <p className="mt-1 text-[12.5px] text-muted-foreground">
          It reads employer career systems and job boards on a schedule, scores every posting
          against your profile, and keeps the ones worth your time in one place.
        </p>
      </div>

      <ul className="space-y-2 text-[12.5px]">
        <Assurance text="Every score is broken down, so you can see why a role ranked where it did." />
        <Assurance text="Nothing is invented. A field the employer left blank stays blank." />
        <Assurance text="Your data stays in a database on this machine." />
      </ul>

      <p className="flex items-start gap-2 rounded-md border border-border bg-muted/40 px-3 py-2.5 text-[12px]">
        <ShieldCheck className="mt-px size-4 shrink-0 text-ok" />
        <span>
          <strong className="font-medium">CareerOS never applies for you.</strong> It drafts letters
          and tracks what you sent, but every application is submitted by you, on the employer&apos;s
          own site.
        </span>
      </p>

      <p className="text-[11.5px] text-muted-foreground">
        Setup takes about a minute. Everything here can be changed later in Settings.
      </p>
    </div>
  );
}

function Assurance({ text }: { text: string }) {
  return (
    <li className="flex items-start gap-2">
      <CheckIcon className="mt-0.5 size-3.5 shrink-0 text-ok" />
      <span>{text}</span>
    </li>
  );
}

/**
 * Shortlisting employers.
 *
 * Reads the employers already seeded rather than asking the user to type
 * company names: a typed name has to match an employer CareerOS can actually
 * read, and guessing at that is how you end up watching nothing.
 */
function EmployersStep() {
  const [companies, setCompanies] = useState<CompanyOut[] | null>(null);
  const [query, setQuery] = useState("");
  const [busy, setBusy] = useState<string | null>(null);

  useEffect(() => {
    api.companies().then(setCompanies).catch(() => setCompanies([]));
  }, []);

  async function toggle(company: CompanyOut) {
    const tier = company.tier === "dream" ? "normal" : "dream";
    setBusy(company.id);
    try {
      const updated = await api.updateCompany(company.id, { tier });
      setCompanies((list) => list?.map((c) => (c.id === company.id ? updated : c)) ?? list);
    } catch {
      toast.error("That did not save.");
    } finally {
      setBusy(null);
    }
  }

  const shortlisted = companies?.filter((c) => c.tier === "dream").length ?? 0;
  const visible = (companies ?? [])
    .filter((c) => !query || c.name.toLowerCase().includes(query.toLowerCase()))
    .slice(0, 60);

  return (
    <StepBody
      title="Who would you love to work for?"
      hint="Shortlisted employers get a scoring bonus, and you are told the moment they post."
    >
      {companies === null ? (
        <Skeleton className="h-56 w-full" />
      ) : companies.length === 0 ? (
        <p className="rounded-md border border-dashed border-border px-4 py-8 text-center text-[12px] text-muted-foreground">
          No employers are loaded yet. They appear after the first scan — you can shortlist them in
          Companies at any time.
        </p>
      ) : (
        <>
          <div className="relative">
            <Search className="absolute left-2.5 top-1/2 size-3.5 -translate-y-1/2 text-muted-foreground" />
            <Input
              value={query}
              onChange={(e) => setQuery(e.target.value)}
              placeholder="Search employers"
              aria-label="Search employers"
              className="h-8 pl-8 text-[13px]"
            />
          </div>

          <ul className="grid max-h-72 grid-cols-2 gap-1 overflow-y-auto pr-1 scrollbar-thin">
            {visible.map((company) => {
              const on = company.tier === "dream";
              return (
                <li key={company.id}>
                  <button
                    onClick={() => toggle(company)}
                    disabled={busy === company.id}
                    aria-pressed={on}
                    className={cn(
                      "flex w-full items-center gap-2 rounded-md border px-2.5 py-1.5 text-left text-[12px] transition-colors",
                      on
                        ? "border-ok/50 bg-ok-soft/50"
                        : "border-border hover:border-ring/50 hover:bg-accent/50",
                    )}
                  >
                    <span className="min-w-0 flex-1 truncate">{company.name}</span>
                    {!company.is_automated && <Badge variant="outline">by hand</Badge>}
                    {on && <CheckIcon className="size-3.5 shrink-0 text-ok" />}
                  </button>
                </li>
              );
            })}
          </ul>

          <p className="text-[11.5px] text-muted-foreground">
            {shortlisted} shortlisted. Employers marked <em>by hand</em> publish no feed CareerOS can
            read, so they are listed for you to check yourself.
          </p>
        </>
      )}
    </StepBody>
  );
}

/**
 * The first scan.
 *
 * Offered, not forced, and reported with the real count of sources completed.
 * A fake progress bar would be the easiest thing here and the first lie the
 * product ever told.
 */
function ScanStep({ saving }: { saving: boolean }) {
  const { state, start, starting, progress } = useScanState();
  const [asked, setAsked] = useState(false);

  async function run() {
    setAsked(true);
    const result = await start();
    if (!result.ok) toast.error(result.message);
  }

  const done = !state?.running && state?.last_finished_at && asked;

  return (
    <StepBody
      title="Ready for the first scan"
      hint="It reads every source once. That usually takes about a minute."
    >
      {state?.running ? (
        <div className="space-y-2.5 rounded-md border border-border p-4">
          <p className="flex items-center gap-2 text-[12.5px]">
            <Loader2 className="size-3.5 animate-spin text-info" />
            {state.providers_done} of {state.providers_total} sources read
          </p>
          <Progress value={progress ?? 0} />
          <p className="text-[11.5px] text-muted-foreground">
            {state.postings_seen.toLocaleString()} postings read so far. You can open CareerOS now —
            the scan keeps going in the background.
          </p>
        </div>
      ) : done ? (
        <p className="flex items-start gap-2 rounded-md border border-ok/40 bg-ok-soft/40 px-3 py-2.5 text-[12.5px]">
          <CheckIcon className="mt-px size-4 shrink-0 text-ok" />
          <span>
            First scan finished {state?.last_status === "ok" ? "cleanly" : `as ${state?.last_status}`}
            . Open CareerOS to see what it found.
          </span>
        </p>
      ) : (
        <div className="rounded-md border border-border p-4">
          <p className="text-[12.5px]">
            Start it now, or let the schedule pick it up at the next hour.
          </p>
          <Button size="sm" className="mt-3" onClick={run} disabled={starting || saving}>
            {starting ? <Loader2 className="animate-spin" /> : <Search />}
            {starting ? "Starting" : "Run the first scan"}
          </Button>
        </div>
      )}

      <p className="flex items-start gap-2 text-[11.5px] text-muted-foreground">
        <ShieldCheck className="mt-px size-3.5 shrink-0 text-ok" />
        CareerOS never submits an application for you. It prepares drafts and tracks what you sent;
        you press send, on the employer&apos;s own site.
      </p>
    </StepBody>
  );
}

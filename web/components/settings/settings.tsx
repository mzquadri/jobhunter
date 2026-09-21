"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import Link from "next/link";
import { AlertTriangle, ArrowRight, RotateCcw } from "lucide-react";
import { toast } from "sonner";
import { api, type SettingsOut } from "@/lib/api";
import { useResource } from "@/lib/hooks";
import { Check, Field, Section, TagInput } from "@/components/settings/fields";
import {
  Button,
  Card,
  ErrorState,
  Input,
  Page,
  Select,
  Skeleton,
  Tabs,
  Textarea,
} from "@/components/ui/primitives";
import { cn } from "@/lib/utils";

/* -------------------------------------------------------------------------- */
/* The shape of the stored document, as this screen reads it.                  */
/* The server is the authority; these types describe the subset the UI edits.  */
/* -------------------------------------------------------------------------- */

type Candidate = {
  name: string;
  email: string;
  phone: string;
  city: string;
  primary_city: string;
  available_from: string;
  education_level: "bsc" | "msc" | "phd";
  german_level: "none" | "a1" | "a2" | "b1" | "b2" | "c1" | "c2" | "native";
  years_experience: number;
  headline: string;
};

type SearchPrefs = {
  max_age_days: number;
  archive_after_days: number;
  min_score: number;
  draft_min_score: number;
  keep_undated: boolean;
  target_salary_eur: number;
  salary_is_hard_filter: boolean;
};

type Weights = Record<WeightKey, number>;

type Notifications = {
  high_match_threshold: number;
  follow_up_after_days: number;
  notify_high_match: boolean;
  notify_dream_company: boolean;
  notify_run_failed: boolean;
  notify_job_closed: boolean;
  notify_follow_up_due: boolean;
};

type Appearance = { theme: "system" | "light" | "dark"; density: "comfortable" | "compact" };

type Boards = {
  enabled: string[];
  arbeitnow_pages: number;
  queries: string[];
  adzuna_countries: string[];
};

const WEIGHT_KEYS = [
  "technical",
  "location",
  "freshness",
  "experience",
  "language",
  "domain",
  "education",
] as const;
type WeightKey = (typeof WEIGHT_KEYS)[number];

const WEIGHT_LABEL: Record<WeightKey, string> = {
  technical: "Technical fit",
  location: "Location",
  freshness: "How recently posted",
  experience: "Experience level",
  language: "Language",
  domain: "Industry",
  education: "Education",
};

const GERMAN_LEVELS: [Candidate["german_level"], string][] = [
  ["none", "None"],
  ["a1", "A1 — a few words"],
  ["a2", "A2 — basics"],
  ["b1", "B1 — conversational"],
  ["b2", "B2 — working proficiency"],
  ["c1", "C1 — fluent"],
  ["c2", "C2 — near native"],
  ["native", "Native"],
];

const BOARDS: [string, string][] = [
  ["arbeitnow", "Arbeitnow (Germany)"],
  ["jobsch", "jobs.ch (Switzerland)"],
  ["adzuna", "Adzuna (needs an app id)"],
];

const TABS = [
  { value: "you", label: "You" },
  { value: "search", label: "What you want" },
  { value: "where", label: "Where & roles" },
  { value: "scoring", label: "Matching" },
  { value: "sources", label: "Sources" },
  { value: "alerts", label: "Alerts" },
  { value: "app", label: "Appearance" },
];

/* -------------------------------------------------------------------------- */

/**
 * Settings.
 *
 * Everything the scanner uses to decide what to show you, editable here and
 * nowhere else. Each section saves on its own because the backend merges one
 * section at a time; a page-wide save would have to send the whole document
 * back and would overwrite whatever a scan changed while the page was open.
 */
export function Settings() {
  const [tab, setTab] = useState("you");
  const { data, error, loading, refresh, setData } = useResource(() => api.settings(), []);

  const save = useCallback(
    async (patch: Record<string, unknown>, message: string) => {
      const updated = await api.patchSettings(patch);
      setData(updated);
      toast.success(message, { description: "Applied from the next scan onwards." });
      return updated;
    },
    [setData],
  );

  if (error) {
    return (
      <Page>
        <ErrorState
          title={error.isOffline ? "CareerOS cannot reach its backend" : "Could not load settings"}
          message={
            error.isOffline
              ? "The API is not responding. If you just started the stack, give it a few seconds."
              : error.message
          }
          retry={() => void refresh()}
        />
      </Page>
    );
  }

  if (loading && !data) {
    return (
      <Page className="space-y-4">
        <Skeleton className="h-8 w-96" />
        <Skeleton className="h-64 w-full" />
        <Skeleton className="h-48 w-full" />
      </Page>
    );
  }

  if (!data) return null;
  const profile = data.profile as Record<string, unknown>;

  return (
    <Page className="max-w-4xl space-y-4">
      <Tabs value={tab} onChange={setTab} options={TABS} />

      {tab === "you" && <YouSection candidate={profile.candidate as Candidate} onSave={save} />}
      {tab === "search" && <SearchSection search={profile.search as SearchPrefs} onSave={save} />}
      {tab === "where" && <WhereSection profile={profile} onSave={save} />}
      {tab === "scoring" && <ScoringSection profile={profile} onSave={save} />}
      {tab === "sources" && <SourcesSection boards={profile.boards as Boards} onSave={save} />}
      {tab === "alerts" && (
        <AlertsSection notifications={profile.notifications as Notifications} onSave={save} />
      )}
      {tab === "app" && (
        <AppearanceSection
          appearance={profile.appearance as Appearance}
          settings={data}
          onSave={save}
          onReloaded={setData}
        />
      )}
    </Page>
  );
}

type Save = (patch: Record<string, unknown>, message: string) => Promise<SettingsOut>;

/**
 * A working copy of one section.
 *
 * Edits stay local until Save, so a half-finished change never reaches the
 * scanner, and the server's copy replaces the draft once it is written.
 */
function useDraft<T extends object>(source: T) {
  const [draft, setDraft] = useState<T>(source);
  const [saving, setSaving] = useState(false);

  // Adopt the server's version whenever it changes underneath us.
  useEffect(() => {
    setDraft(source);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [JSON.stringify(source)]);

  const dirty = JSON.stringify(draft) !== JSON.stringify(source);

  function set<K extends keyof T>(key: K, value: T[K]) {
    setDraft((d) => ({ ...d, [key]: value }));
  }

  async function commit(run: () => Promise<unknown>) {
    setSaving(true);
    try {
      await run();
    } catch (e) {
      toast.error(e instanceof Error ? e.message : "Those settings were not saved.");
    } finally {
      setSaving(false);
    }
  }

  return { draft, setDraft, set, dirty, saving, commit, reset: () => setDraft(source) };
}

/* -------------------------------------------------------------------------- */

function YouSection({ candidate, onSave }: { candidate: Candidate; onSave: Save }) {
  const { draft, set, dirty, saving, commit, reset } = useDraft(candidate);

  return (
    <Section
      title="You"
      hint="Used to score every posting, and to fill in the drafts CareerOS writes for you."
      dirty={dirty}
      saving={saving}
      onReset={reset}
      onSave={() => commit(() => onSave({ candidate: draft }, "Your details are saved"))}
    >
      <div className="grid gap-4 sm:grid-cols-2">
        <Field label="Name" htmlFor="name">
          <Input
            id="name"
            value={draft.name}
            onChange={(e) => set("name", e.target.value)}
            className="h-8 text-[13px]"
          />
        </Field>
        <Field label="Where you are based" htmlFor="city" hint="The city your search starts from.">
          <Input
            id="city"
            value={draft.primary_city}
            onChange={(e) => set("primary_city", e.target.value)}
            className="h-8 text-[13px]"
          />
        </Field>
        <Field label="Email" htmlFor="email">
          <Input
            id="email"
            type="email"
            value={draft.email}
            onChange={(e) => set("email", e.target.value)}
            className="h-8 text-[13px]"
          />
        </Field>
        <Field label="Phone" htmlFor="phone">
          <Input
            id="phone"
            value={draft.phone}
            onChange={(e) => set("phone", e.target.value)}
            className="h-8 text-[13px]"
          />
        </Field>
      </div>

      <p className="rounded-md border border-border bg-muted/40 px-3 py-2 text-[11px] text-muted-foreground">
        Your contact details stay in the database on this machine. They are never sent anywhere and
        are not part of the published source code.
      </p>

      <div className="grid gap-4 sm:grid-cols-3">
        <Field label="Years of experience" htmlFor="years">
          <Input
            id="years"
            type="number"
            min={0}
            max={50}
            step={0.5}
            value={draft.years_experience}
            onChange={(e) => set("years_experience", Number(e.target.value))}
            className="h-8 text-[13px]"
          />
        </Field>
        <Field label="Highest degree" htmlFor="education">
          <Select
            id="education"
            value={draft.education_level}
            onChange={(e) => set("education_level", e.target.value as Candidate["education_level"])}
            className="h-8 w-full text-[13px]"
          >
            <option value="bsc">Bachelor</option>
            <option value="msc">Master</option>
            <option value="phd">Doctorate</option>
          </Select>
        </Field>
        <Field
          label="German"
          htmlFor="german"
          hint="Decides how hard a German requirement counts against a role."
        >
          <Select
            id="german"
            value={draft.german_level}
            onChange={(e) => set("german_level", e.target.value as Candidate["german_level"])}
            className="h-8 w-full text-[13px]"
          >
            {GERMAN_LEVELS.map(([value, label]) => (
              <option key={value} value={value}>
                {label}
              </option>
            ))}
          </Select>
        </Field>
      </div>

      <Field label="Available from" htmlFor="available">
        <Input
          id="available"
          value={draft.available_from}
          onChange={(e) => set("available_from", e.target.value)}
          placeholder="immediately"
          className="h-8 max-w-xs text-[13px]"
        />
      </Field>

      <Field
        label="One line about you"
        htmlFor="headline"
        hint="Opens the cover letters CareerOS drafts."
      >
        <Textarea
          id="headline"
          value={draft.headline}
          onChange={(e) => set("headline", e.target.value)}
          className="min-h-16 text-[12.5px]"
        />
      </Field>
    </Section>
  );
}

function SearchSection({ search, onSave }: { search: SearchPrefs; onSave: Save }) {
  const { draft, set, dirty, saving, commit, reset } = useDraft(search);

  return (
    <Section
      title="What you are looking for"
      hint="These decide which postings are kept at all."
      dirty={dirty}
      saving={saving}
      onReset={reset}
      onSave={() => commit(() => onSave({ search: draft }, "Search preferences saved"))}
    >
      <div className="grid gap-4 sm:grid-cols-2">
        <Field
          label={`Only roles posted in the last ${draft.max_age_days} days`}
          htmlFor="age"
          hint="Older postings are usually filled. 14 days is a good default."
        >
          <input
            id="age"
            type="range"
            min={1}
            max={90}
            value={draft.max_age_days}
            onChange={(e) => set("max_age_days", Number(e.target.value))}
            className="w-full accent-[var(--color-info)]"
          />
        </Field>

        <Field
          label={`Hide anything scoring under ${draft.min_score}`}
          htmlFor="minscore"
          hint="The score is fit against your profile, not a prediction of an offer."
        >
          <input
            id="minscore"
            type="range"
            min={0}
            max={100}
            value={draft.min_score}
            onChange={(e) => set("min_score", Number(e.target.value))}
            className="w-full accent-[var(--color-info)]"
          />
        </Field>

        <Field
          label="Target salary (EUR per year)"
          htmlFor="salary"
          hint="Used for context, and to rank roles that state a figure."
        >
          <Input
            id="salary"
            type="number"
            min={0}
            step={1000}
            value={draft.target_salary_eur}
            onChange={(e) => set("target_salary_eur", Number(e.target.value))}
            className="h-8 text-[13px]"
          />
        </Field>

        <Field
          label={`Write a draft for anything scoring ${draft.draft_min_score} or above`}
          htmlFor="draftscore"
          hint="Drafts are prepared locally for you to edit. Nothing is ever sent for you."
        >
          <input
            id="draftscore"
            type="range"
            min={0}
            max={100}
            value={draft.draft_min_score}
            onChange={(e) => set("draft_min_score", Number(e.target.value))}
            className="w-full accent-[var(--color-info)]"
          />
        </Field>
      </div>

      <div className="space-y-0.5">
        <Check
          label="Keep postings with no publication date"
          hint="Some employers never publish one. Dropping them would hide real roles."
          checked={draft.keep_undated}
          onChange={(v) => set("keep_undated", v)}
        />
        <Check
          label="Only show roles that state a salary at or above my target"
          hint="Off by default: a posting with no salary is not evidence of a low one."
          checked={draft.salary_is_hard_filter}
          onChange={(v) => set("salary_is_hard_filter", v)}
        />
      </div>

      <Field
        label="Archive roles after"
        htmlFor="archive"
        hint="Closed roles stay visible this long before they leave the lists."
      >
        <span className="flex items-center gap-2">
          <Input
            id="archive"
            type="number"
            min={1}
            max={3650}
            value={draft.archive_after_days}
            onChange={(e) => set("archive_after_days", Number(e.target.value))}
            className="h-8 w-24 text-[13px]"
          />
          <span className="text-[12px] text-muted-foreground">days</span>
        </span>
      </Field>
    </Section>
  );
}

function WhereSection({
  profile,
  onSave,
}: {
  profile: Record<string, unknown>;
  onSave: Save;
}) {
  const locations = profile.locations as { tiers: Record<string, string[]>; exclude: string[] };
  const roles = profile.roles as {
    include: string[];
    too_senior: string[];
    not_fulltime: string[];
  };

  const loc = useDraft(locations);
  const rol = useDraft(roles);

  const tierKeys = useMemo(
    () => Object.keys(loc.draft.tiers ?? {}).sort((a, b) => Number(a) - Number(b)),
    [loc.draft.tiers],
  );

  return (
    <div className="space-y-4">
      <Section
        title="Where you would work"
        hint="Tier 1 cities score highest, tier 2 next, and so on. A role outside every tier is dropped."
        dirty={loc.dirty}
        saving={loc.saving}
        onReset={loc.reset}
        onSave={() => loc.commit(() => onSave({ locations: loc.draft }, "Locations saved"))}
      >
        {tierKeys.map((tier) => (
          <Field
            key={tier}
            label={`Tier ${tier} cities`}
            hint={
              tier === "1"
                ? "Where you most want to be."
                : tier === "2"
                  ? "Happy to move for the right role."
                  : "Would consider."
            }
          >
            <TagInput
              values={loc.draft.tiers[tier] ?? []}
              onChange={(values) =>
                loc.setDraft((d) => ({ ...d, tiers: { ...d.tiers, [tier]: values } }))
              }
              placeholder="Add a city or country"
            />
          </Field>
        ))}

        <Field
          label="Never show me roles in"
          hint="Matched against the location the employer wrote."
        >
          <TagInput
            values={loc.draft.exclude ?? []}
            onChange={(values) => loc.setDraft((d) => ({ ...d, exclude: values }))}
            placeholder="Add a city or country to skip"
          />
        </Field>
      </Section>

      <Section
        title="Roles"
        hint="Title words CareerOS looks for, and the ones that rule a posting out."
        dirty={rol.dirty}
        saving={rol.saving}
        onReset={rol.reset}
        onSave={() => rol.commit(() => onSave({ roles: rol.draft }, "Roles saved"))}
      >
        <Field label="Job titles worth showing me" hint="A posting must match at least one.">
          <TagInput
            values={rol.draft.include ?? []}
            onChange={(values) => rol.setDraft((d) => ({ ...d, include: values }))}
            placeholder="machine learning engineer"
          />
        </Field>

        <Field
          label="Too senior for now"
          hint="Titles that mean the role is years beyond your experience."
        >
          <TagInput
            values={rol.draft.too_senior ?? []}
            onChange={(values) => rol.setDraft((d) => ({ ...d, too_senior: values }))}
            placeholder="head of, principal"
          />
        </Field>

        <Field label="Not a full-time job" hint="Words that mark an internship, thesis or contract.">
          <TagInput
            values={rol.draft.not_fulltime ?? []}
            onChange={(values) => rol.setDraft((d) => ({ ...d, not_fulltime: values }))}
            placeholder="werkstudent, internship"
          />
        </Field>
      </Section>
    </div>
  );
}

function ScoringSection({
  profile,
  onSave,
}: {
  profile: Record<string, unknown>;
  onSave: Save;
}) {
  const scoring = profile.scoring as { weights: Weights };
  const { draft, setDraft, dirty, saving, commit, reset } = useDraft(scoring.weights);

  const total = WEIGHT_KEYS.reduce((n, k) => n + (draft[k] ?? 0), 0);
  const balanced = Math.abs(total - 1) <= 0.02;

  function balance() {
    if (total <= 0) return;
    setDraft((d) =>
      Object.fromEntries(
        WEIGHT_KEYS.map((k) => [k, Math.round(((d[k] ?? 0) / total) * 100) / 100]),
      ) as Weights,
    );
  }

  return (
    <Section
      title="What matters in a match"
      hint="The seven parts of every score. They have to add up to 100%."
      dirty={dirty}
      saving={saving}
      onReset={reset}
      onSave={() =>
        balanced
          ? commit(() => onSave({ scoring: { weights: draft } }, "Matching weights saved"))
          : toast.error(`The weights add up to ${Math.round(total * 100)}%. Balance them first.`)
      }
    >
      <div className="space-y-3">
        {WEIGHT_KEYS.map((key) => (
          <div key={key} className="flex items-center gap-3">
            <label htmlFor={`w-${key}`} className="w-40 shrink-0 text-[12px]">
              {WEIGHT_LABEL[key]}
            </label>
            <input
              id={`w-${key}`}
              type="range"
              min={0}
              max={50}
              value={Math.round((draft[key] ?? 0) * 100)}
              onChange={(e) =>
                setDraft((d) => ({ ...d, [key]: Number(e.target.value) / 100 }) as Weights)
              }
              className="flex-1 accent-[var(--color-info)]"
            />
            <span className="tabular w-12 shrink-0 text-right text-[12px] text-muted-foreground">
              {Math.round((draft[key] ?? 0) * 100)}%
            </span>
          </div>
        ))}
      </div>

      <div
        className={cn(
          "flex items-center gap-2.5 rounded-md border px-3 py-2 text-[12px]",
          balanced ? "border-border text-muted-foreground" : "border-warn/40 bg-warn-soft/40",
        )}
      >
        {!balanced && <AlertTriangle className="size-3.5 shrink-0 text-warn" />}
        <span className="flex-1">
          {balanced
            ? "Adds up to 100%. Every score is a weighted sum of these seven parts."
            : `These add up to ${Math.round(total * 100)}%, so they cannot be saved yet.`}
        </span>
        {!balanced && (
          <Button variant="outline" size="sm" onClick={balance}>
            Scale to 100%
          </Button>
        )}
      </div>
    </Section>
  );
}

function SourcesSection({ boards, onSave }: { boards: Boards; onSave: Save }) {
  const { draft, set, setDraft, dirty, saving, commit, reset } = useDraft(boards);

  return (
    <div className="space-y-4">
      <Section
        title="Job boards"
        hint="Employer career systems are always read. These are the open boards on top of them."
        dirty={dirty}
        saving={saving}
        onReset={reset}
        onSave={() => commit(() => onSave({ boards: draft }, "Sources saved"))}
      >
        <div className="space-y-0.5">
          {BOARDS.map(([key, label]) => (
            <Check
              key={key}
              label={label}
              checked={(draft.enabled ?? []).includes(key)}
              onChange={(on) =>
                setDraft((d) => ({
                  ...d,
                  enabled: on
                    ? [...(d.enabled ?? []), key]
                    : (d.enabled ?? []).filter((k) => k !== key),
                }))
              }
            />
          ))}
        </div>

        <Field
          label="What to search those boards for"
          hint="Boards need a search term; employer systems are listed by company instead."
        >
          <TagInput
            values={draft.queries ?? []}
            onChange={(values) => set("queries", values)}
            placeholder="machine learning"
          />
        </Field>

        <Field
          label="Pages to read from Arbeitnow"
          hint="Each page is 100 postings. More pages means a slower scan."
        >
          <Input
            type="number"
            min={1}
            max={20}
            value={draft.arbeitnow_pages}
            onChange={(e) => set("arbeitnow_pages", Number(e.target.value))}
            className="h-8 w-24 text-[13px]"
          />
        </Field>
      </Section>

      <Card className="flex items-center gap-3 p-4">
        <div className="min-w-0 flex-1">
          <h3 className="text-[13px] font-semibold tracking-tight">Employers</h3>
          <p className="mt-0.5 text-[11.5px] text-muted-foreground">
            Which companies are watched, how often, and which ones have to be checked by hand.
          </p>
        </div>
        <Button asChild variant="outline" size="sm">
          <Link href="/companies">
            Manage employers <ArrowRight />
          </Link>
        </Button>
      </Card>

      <Card className="flex items-center gap-3 p-4">
        <div className="min-w-0 flex-1">
          <h3 className="text-[13px] font-semibold tracking-tight">Schedule</h3>
          <p className="mt-0.5 text-[11.5px] text-muted-foreground">
            How often CareerOS scans, and what happened on the last runs.
          </p>
        </div>
        <Button asChild variant="outline" size="sm">
          <Link href="/automation">
            Open automation <ArrowRight />
          </Link>
        </Button>
      </Card>
    </div>
  );
}

function AlertsSection({
  notifications,
  onSave,
}: {
  notifications: Notifications;
  onSave: Save;
}) {
  const { draft, set, dirty, saving, commit, reset } = useDraft(notifications);

  return (
    <Section
      title="What to tell me about"
      hint="Signals appear on the overview and in the bell menu. Nothing leaves this machine."
      dirty={dirty}
      saving={saving}
      onReset={reset}
      onSave={() => commit(() => onSave({ notifications: draft }, "Alert settings saved"))}
    >
      <div className="space-y-0.5">
        <Check
          label="A strong match appears"
          checked={draft.notify_high_match}
          onChange={(v) => set("notify_high_match", v)}
        />
        <Check
          label="One of my shortlisted employers posts a role"
          checked={draft.notify_dream_company}
          onChange={(v) => set("notify_dream_company", v)}
        />
        <Check
          label="A role I was tracking is taken down"
          checked={draft.notify_job_closed}
          onChange={(v) => set("notify_job_closed", v)}
        />
        <Check
          label="A follow-up is due"
          hint="Based on the follow-up date on the role. You can change any of them in the job panel."
          checked={draft.notify_follow_up_due}
          onChange={(v) => set("notify_follow_up_due", v)}
        />
        <Check
          label="A scan fails"
          checked={draft.notify_run_failed}
          onChange={(v) => set("notify_run_failed", v)}
        />
      </div>

      <Field
        label="Remind me to follow up after"
        htmlFor="followup"
        hint="Set when you move a role to Applied, unless you gave it a date yourself. Zero means no reminder."
      >
        <span className="flex items-center gap-2">
          <Input
            id="followup"
            type="number"
            min={0}
            max={90}
            value={draft.follow_up_after_days}
            onChange={(e) => set("follow_up_after_days", Number(e.target.value))}
            className="h-8 w-24 text-[13px]"
          />
          <span className="text-[12px] text-muted-foreground">days</span>
        </span>
      </Field>

      <Field
        label={`Call a match "strong" from ${draft.high_match_threshold} up`}
        htmlFor="threshold"
      >
        <input
          id="threshold"
          type="range"
          min={50}
          max={100}
          value={draft.high_match_threshold}
          onChange={(e) => set("high_match_threshold", Number(e.target.value))}
          className="w-full max-w-md accent-[var(--color-info)]"
        />
      </Field>
    </Section>
  );
}

function AppearanceSection({
  appearance,
  settings,
  onSave,
  onReloaded,
}: {
  appearance: Appearance;
  settings: SettingsOut;
  onSave: Save;
  onReloaded: (settings: SettingsOut) => void;
}) {
  const { draft, set, dirty, saving, commit, reset } = useDraft(appearance);
  const [resetting, setResetting] = useState(false);
  const [confirming, setConfirming] = useState(false);

  /** Both of these change the page immediately; Save is what remembers them. */
  function applyDensity(density: Appearance["density"]) {
    set("density", density);
    if (density === "compact") document.documentElement.setAttribute("data-density", "compact");
    else document.documentElement.removeAttribute("data-density");
    localStorage.setItem("careeros.density", density);
  }

  function applyTheme(theme: Appearance["theme"]) {
    set("theme", theme);
    const dark =
      theme === "dark" ||
      (theme === "system" && !window.matchMedia("(prefers-color-scheme: light)").matches);
    document.documentElement.classList.toggle("dark", dark);
    if (theme === "system") localStorage.removeItem("careeros.theme");
    else localStorage.setItem("careeros.theme", theme);
  }

  async function restoreDefaults() {
    setResetting(true);
    try {
      onReloaded(await api.resetSettings());
      setConfirming(false);
      toast.success("Settings restored to their defaults");
    } catch (e) {
      toast.error(e instanceof Error ? e.message : "Could not restore the defaults.");
    } finally {
      setResetting(false);
    }
  }

  return (
    <div className="space-y-4">
      <Section
        title="Appearance"
        hint="Both apply straight away; saving remembers them for the next time you open CareerOS."
        dirty={dirty}
        saving={saving}
        onReset={reset}
        onSave={() => commit(() => onSave({ appearance: draft }, "Appearance saved"))}
      >
        <Field label="Theme">
          <div className="flex gap-1.5">
            {(["system", "light", "dark"] as const).map((theme) => (
              <Button
                key={theme}
                variant={draft.theme === theme ? "default" : "outline"}
                size="sm"
                onClick={() => applyTheme(theme)}
              >
                {theme === "system" ? "Match my system" : theme === "light" ? "Light" : "Dark"}
              </Button>
            ))}
          </div>
        </Field>

        <Field label="Density" hint="Compact tightens table and list rows, so more fits on screen.">
          <div className="flex gap-1.5">
            {(["comfortable", "compact"] as const).map((density) => (
              <Button
                key={density}
                variant={draft.density === density ? "default" : "outline"}
                size="sm"
                onClick={() => applyDensity(density)}
              >
                {density === "comfortable" ? "Comfortable" : "Compact"}
              </Button>
            ))}
          </div>
        </Field>
      </Section>

      <Card className="p-4">
        <h3 className="text-[13px] font-semibold tracking-tight">Start over</h3>
        <p className="mt-0.5 text-[11.5px] text-muted-foreground">
          Restores every setting on this page to the values CareerOS shipped with. Your saved jobs,
          notes and application history are not touched.
        </p>
        <p className="mt-2 text-[11px] text-muted-foreground">
          Last changed {new Date(settings.updated_at).toLocaleString()}.
        </p>

        {confirming ? (
          <div className="mt-3 flex items-center gap-2">
            <Button variant="destructive" size="sm" onClick={restoreDefaults} disabled={resetting}>
              {resetting ? "Restoring" : "Yes, restore defaults"}
            </Button>
            <Button variant="ghost" size="sm" onClick={() => setConfirming(false)}>
              Keep my settings
            </Button>
          </div>
        ) : (
          <Button variant="outline" size="sm" className="mt-3" onClick={() => setConfirming(true)}>
            <RotateCcw /> Restore defaults
          </Button>
        )}
      </Card>
    </div>
  );
}

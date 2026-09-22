"use client";

import { useState } from "react";
import { cn } from "@/lib/utils";

/**
 * An employer's mark.
 *
 * Initials on a colour derived from the name, with the employer's own favicon
 * painted over it when one exists.
 *
 * The obvious implementation is a logo CDN — Clearbit, Brandfetch and friends
 * all resolve a domain to a brand image in one request. Two reasons not to:
 *
 *   * **It leaks the job search.** Every logo fetch tells that CDN which
 *     employers this person is looking at, in order, with timestamps. This is
 *     a private job search on someone's own machine; shipping a browsing
 *     history of "companies I am considering leaving my job for" to a third
 *     party is not a fair trade for a nicer-looking row.
 *   * **Most need an account key**, which in a public repository means either a
 *     committed credential or a broken image.
 *
 * So the only network request is to the employer's own careers domain, which
 * the user is going to visit anyway. It is their asset, served by them, and no
 * one else learns anything. Hit rate is mediocre — plenty of sites declare
 * their icon in markup rather than at `/favicon.ico` — which is fine, because
 * the initials are rendered first and a failure costs nothing.
 */

/** Deterministic hue from the name, so an employer's colour never moves. */
function hue(name: string): number {
  let value = 0;
  for (let i = 0; i < name.length; i += 1) {
    value = (value * 31 + name.charCodeAt(i)) % 360;
  }
  return value;
}

/** One or two letters. "BMW Group" → BG; "Helsing" → HE. */
function initials(name: string): string {
  const words = name
    .replace(/[^\p{L}\p{N}\s]/gu, " ")
    .split(/\s+/)
    .filter(Boolean)
    // Legal suffixes are not how anyone refers to an employer.
    .filter((w) => !/^(se|ag|gmbh|ltd|inc|bv|nv|plc|sa|group|holding)$/i.test(w));

  if (words.length === 0) return "?";
  if (words.length === 1) return words[0].slice(0, 2).toUpperCase();
  return (words[0][0] + words[1][0]).toUpperCase();
}

/** Applicant-tracking hosts. Their logo is the vendor's, not the employer's. */
const ATS_HOSTS = [
  "myworkdayjobs.com", "greenhouse.io", "lever.co", "ashbyhq.com",
  "smartrecruiters.com", "personio.de", "workable.com", "successfactors.com",
  "recruitee.com", "teamtailor.com", "jobvite.com", "icims.com",
];

function iconUrl(careersUrl: string): string | null {
  if (!careersUrl) return null;
  try {
    const url = new URL(careersUrl);
    if (url.protocol !== "https:") return null;
    const host = url.hostname.replace(/^www\./, "");
    if (ATS_HOSTS.some((vendor) => host.endsWith(vendor))) return null;
    return `https://${host}/favicon.ico`;
  } catch {
    return null;
  }
}

const SIZES = {
  sm: "size-6 text-[9px] rounded",
  md: "size-8 text-[11px] rounded-md",
  lg: "size-10 text-[13px] rounded-md",
} as const;

export function CompanyLogo({
  name,
  careersUrl = "",
  size = "md",
  className,
}: {
  name: string;
  careersUrl?: string;
  size?: keyof typeof SIZES;
  className?: string;
}) {
  const [failed, setFailed] = useState(false);
  const icon = iconUrl(careersUrl);
  const h = hue(name);

  return (
    <span
      aria-hidden
      title={name}
      className={cn(
        "relative inline-flex shrink-0 items-center justify-center overflow-hidden",
        "border border-border/60 font-semibold",
        SIZES[size],
        className,
      )}
      style={{
        // A tint, not a saturated block: this sits beside text all day.
        backgroundColor: `oklch(0.62 0.055 ${h} / 0.18)`,
        color: `oklch(0.55 0.09 ${h})`,
      }}
    >
      {initials(name)}
      {icon && !failed && (
        /*
          A plain <img> on purpose. next/image would proxy every employer icon
          through our own server and require each host in next.config — for a
          few hundred employers whose domains change, that is a config nobody
          maintains and an outage when they forget. The initials underneath
          mean a failure is invisible.
        */
        // eslint-disable-next-line @next/next/no-img-element
        <img
          src={icon}
          alt=""
          loading="lazy"
          decoding="async"
          referrerPolicy="no-referrer"
          onError={() => setFailed(true)}
          className="absolute inset-0 size-full bg-background object-contain p-0.5"
        />
      )}
    </span>
  );
}

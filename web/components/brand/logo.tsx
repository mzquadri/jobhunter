/**
 * The CareerOS mark.
 *
 * An aperture: four blades leaving an open centre, with one blade extended
 * into a sweep. It reads as a lens focusing rather than a radar dish, which
 * is the intent — the product narrows a very wide field down to the few roles
 * worth an evening, and the extended blade is the one signal that made it
 * through.
 *
 * Drawn on a 24-unit grid with a single stroke weight so it stays legible at
 * 16px in a browser tab and at 512px in a manifest icon. No gradient, no
 * glow: it has to survive being one colour on a dark sidebar.
 */

export function Mark({
  className,
  strokeWidth = 1.75,
}: {
  className?: string;
  strokeWidth?: number;
}) {
  return (
    <svg
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth={strokeWidth}
      strokeLinecap="round"
      strokeLinejoin="round"
      className={className}
      aria-hidden="true"
    >
      {/* the aperture ring, opened at the top-right where the signal enters */}
      <path d="M20.5 8.4A9 9 0 1 1 15.6 3.5" />
      {/* three blades */}
      <path d="M12 12 5.2 8.1" />
      <path d="M12 12 8.4 18.6" />
      <path d="M12 12 18.9 15.7" />
      {/* the extended blade: the one signal that got through */}
      <path d="M12 12 19.8 4.2" />
      <circle cx="12" cy="12" r="1.6" fill="currentColor" stroke="none" />
    </svg>
  );
}

/** Mark plus wordmark, for the sidebar and loading states. */
export function Wordmark({
  className,
  showTag = false,
}: {
  className?: string;
  showTag?: boolean;
}) {
  return (
    <span className={`flex items-center gap-2 ${className ?? ""}`}>
      <Mark className="size-[18px] shrink-0 text-foreground" />
      <span className="flex flex-col leading-none">
        <span className="text-[13px] font-semibold tracking-tight">
          Career<span className="text-muted-foreground">OS</span>
        </span>
        {showTag && (
          <span className="mt-0.5 text-[10px] text-muted-foreground">
            Career intelligence
          </span>
        )}
      </span>
    </span>
  );
}

/**
 * The favicon, generated rather than shipped as a binary.
 *
 * Keeping it as code means the mark has exactly one definition; a checked-in
 * .ico would be a second copy free to drift.
 */
export const FAVICON_SVG = `<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="#e7ecf2" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><rect width="24" height="24" rx="5" fill="#111317" stroke="none"/><g transform="translate(1.6 1.6) scale(0.867)"><path d="M20.5 8.4A9 9 0 1 1 15.6 3.5"/><path d="M12 12 5.2 8.1"/><path d="M12 12 8.4 18.6"/><path d="M12 12 18.9 15.7"/><path d="M12 12 19.8 4.2"/><circle cx="12" cy="12" r="1.8" fill="#e7ecf2" stroke="none"/></g></svg>`;

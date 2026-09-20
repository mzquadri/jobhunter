import type { Metadata, Viewport } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "JobHunter",
  description:
    "Live AI/ML job postings from company ATS platforms and job boards, scored against a candidate profile.",
};

export const viewport: Viewport = {
  width: "device-width",
  initialScale: 1,
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en" suppressHydrationWarning>
      <head>
        {/*
          Applied before paint so a dark-theme user never sees a light flash.
          The string below is a fixed literal with nothing interpolated into
          it -- no request data, no props, no stored value reaches the markup.
          The only thing read from storage is compared against, never written
          out. Keep it that way: interpolating anything here would make it a
          genuine injection point.
        */}
        <script
          dangerouslySetInnerHTML={{
            __html: `try{var t=localStorage.getItem('jobhunter.theme');if(t)document.documentElement.setAttribute('data-theme',t)}catch(e){}`,
          }}
        />
      </head>
      <body>
        <div className="mx-auto max-w-[1240px] px-5 pb-20">{children}</div>
      </body>
    </html>
  );
}

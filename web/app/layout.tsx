import type { Metadata, Viewport } from "next";
import { Geist, Geist_Mono } from "next/font/google";
import { Toaster } from "sonner";
import { Sidebar } from "@/components/shell/sidebar";
import { CommandPaletteProvider } from "@/components/shell/command-palette";
import "./globals.css";

const sans = Geist({ variable: "--font-geist-sans", subsets: ["latin"] });
const mono = Geist_Mono({ variable: "--font-geist-mono", subsets: ["latin"] });

export const metadata: Metadata = {
  metadataBase: new URL("http://localhost:3000"),
  title: { default: "CareerOS", template: "%s · CareerOS" },
  description:
    "Career intelligence. Discovery, matching, applications and analytics for an AI/ML job search, in one place.",
  applicationName: "CareerOS",
  openGraph: {
    title: "CareerOS",
    description:
      "A career operating system: hourly discovery across employer systems, explainable matching, and an application pipeline.",
    type: "website",
  },
};

export const viewport: Viewport = {
  width: "device-width",
  initialScale: 1,
  themeColor: [
    { media: "(prefers-color-scheme: light)", color: "#fdfdfc" },
    { media: "(prefers-color-scheme: dark)", color: "#1c1d20" },
  ],
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en" suppressHydrationWarning>
      <head>
        {/*
          Applied before first paint so a dark-theme user never sees a light
          flash, and so a compact layout does not visibly reflow. The string is
          a fixed literal with nothing interpolated into it; stored values are
          only ever compared against, never written into the document. Keep it
          that way.
        */}
        <script
          dangerouslySetInnerHTML={{
            __html: `try{var t=localStorage.getItem('careeros.theme');var d=t?t==='dark':!matchMedia('(prefers-color-scheme:light)').matches;if(d)document.documentElement.classList.add('dark');if(localStorage.getItem('careeros.density')==='compact')document.documentElement.setAttribute('data-density','compact')}catch(e){document.documentElement.classList.add('dark')}`,
          }}
        />
      </head>
      <body className={`${sans.variable} ${mono.variable}`}>
        <CommandPaletteProvider>
          <div className="flex min-h-screen">
            <Sidebar />
            <div className="flex min-w-0 flex-1 flex-col">{children}</div>
          </div>
        </CommandPaletteProvider>

        <Toaster
          position="bottom-right"
          toastOptions={{
            classNames: {
              toast:
                "!bg-popover !text-popover-foreground !border-border !rounded-lg !text-[13px]",
              description: "!text-muted-foreground !text-[12px]",
            },
          }}
        />
      </body>
    </html>
  );
}

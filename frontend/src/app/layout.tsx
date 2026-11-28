import type { Metadata, Viewport } from "next";
import type { ReactNode } from "react";

import { SiteNav } from "@/components/SiteNav";
import { Providers } from "@/components/providers";
import "@/styles/globals.css";

/**
 * The root layout.
 *
 * No font is loaded from a third party at runtime: docs/03 §3.5 forbids a Google Fonts call, and
 * `tokens.css` names self-hosted families with a system fallback. Adding the woff2 files under
 * `public/fonts` changes nothing here, which is the point — the constraint is structural rather than
 * a matter of remembering.
 */

export const metadata: Metadata = {
  title: {
    default: "NEXUS — Command Centre (paper trading)",
    template: "%s · NEXUS",
  },
  description:
    "NEXUS command centre and paper trading dashboard. Simulated execution against real market data; no venue connection and no real money.",
  applicationName: "NEXUS",
  // A trading dashboard is read on a phone as often as at a desk; §3.5 rules responsive web + PWA.
  other: { "environment": "PAPER" },
};

export const viewport: Viewport = {
  themeColor: "#0B0F14",
  colorScheme: "dark",
  width: "device-width",
  initialScale: 1,
};

export default function RootLayout({ children }: { children: ReactNode }) {
  return (
    <html lang="en" data-environment="PAPER">
      <body className="min-h-screen bg-canvas text-primary">
        <Providers>
          <a
            href="#main"
            className="sr-only focus:not-sr-only focus:absolute focus:left-4 focus:top-4 focus:z-50 focus:rounded focus:bg-elevated focus:px-3 focus:py-2 focus:text-body focus:text-primary"
          >
            Skip to content
          </a>
          <SiteNav />
          <main id="main" className="mx-auto max-w-[1600px] px-4 py-4">
            {children}
          </main>
          <footer className="mx-auto max-w-[1600px] px-4 pb-6 pt-2">
            <p className="text-data text-muted">
              NEXUS · Phase 3 (market data) · live trading disabled · D-019 zero-cost: free tools,
              APIs and data only ·{" "}
              <span className="numeric" title="The backend this dashboard is pointed at">
                {process.env.NEXT_PUBLIC_API_LABEL ?? "api"}
              </span>
            </p>
            <p className="mt-1 text-data text-muted">
              Every figure on these pages is simulated unless it is labelled as observed market data.
              All times UTC.
            </p>
          </footer>
        </Providers>
      </body>
    </html>
  );
}

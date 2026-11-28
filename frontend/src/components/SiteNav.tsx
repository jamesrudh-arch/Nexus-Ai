"use client";

/**
 * Primary navigation.
 *
 * docs/03 §2 rules fifteen pages. Four are built here — the ones the paper platform can serve with
 * real data today — and the rest are listed as staged rather than hidden. A navigation that shows
 * only what exists implies the product is complete; one that lists what is missing says where the
 * work is, which is more useful and cannot be mistaken for a finished screen.
 */

import Link from "next/link";
import { usePathname } from "next/navigation";

interface NavItem {
  href: string;
  label: string;
  /** The page number in docs/03 §2, so the nav and the ruling can be read against each other. */
  page?: number;
  built: boolean;
  note?: string;
}

const NAV: NavItem[] = [
  { href: "/", label: "Command Centre", page: 1, built: true },
  { href: "/paper", label: "Paper Trading", page: 7, built: true, note: "Strategy Laboratory bench" },
  { href: "/execution", label: "Execution Room", page: 9, built: true },
  { href: "/portfolio", label: "Portfolio & Risk", page: 8, built: true },
  { href: "/governance", label: "Settings & Governance", page: 15, built: true },
];

const STAGED: NavItem[] = [
  { href: "#", label: "Global Markets", page: 2, built: false },
  { href: "#", label: "Instrument Workbench", page: 3, built: false },
  { href: "#", label: "Intelligence Core", page: 4, built: false },
  { href: "#", label: "Research Dossiers", page: 5, built: false },
  { href: "#", label: "Memory & Knowledge", page: 6, built: false },
  { href: "#", label: "Connections", page: 10, built: false },
  { href: "#", label: "Scenario Studio", page: 11, built: false },
  { href: "#", label: "Performance & Attribution", page: 12, built: false },
  { href: "#", label: "Audit & Replay", page: 13, built: false },
  { href: "#", label: "Alerts & Operations", page: 14, built: false },
];

export function SiteNav() {
  const pathname = usePathname();

  return (
    <nav aria-label="Primary" className="border-b border-line bg-panel">
      <div className="mx-auto flex max-w-[1600px] flex-wrap items-center gap-x-1 gap-y-2 px-4 py-2">
        <Link
          href="/"
          className="mr-4 flex items-baseline gap-2 text-subheading text-primary no-underline"
        >
          <span aria-hidden="true" className="text-info">
            ◆
          </span>
          NEXUS
          <span className="label">Paper</span>
        </Link>

        <ul className="flex flex-wrap items-center gap-x-1 gap-y-1">
          {NAV.map((item) => {
            const current = item.href === "/" ? pathname === "/" : pathname.startsWith(item.href);
            return (
              <li key={item.href}>
                <Link
                  href={item.href}
                  aria-current={current ? "page" : undefined}
                  className={`block rounded px-3 py-1.5 text-body no-underline transition-colors ${
                    current
                      ? "bg-elevated text-primary"
                      : "text-secondary hover:bg-elevated hover:text-primary"
                  }`}
                >
                  {item.label}
                  {item.page ? <span className="label ml-1.5">§{item.page}</span> : null}
                </Link>
              </li>
            );
          })}
        </ul>

        <details className="ml-auto">
          <summary className="label cursor-pointer select-none text-muted">
            10 pages staged
          </summary>
          <ul className="absolute right-4 z-10 mt-1 w-64 rounded border border-line bg-elevated p-2 shadow-lg">
            {STAGED.map((item) => (
              <li
                key={item.label}
                className="flex items-baseline justify-between gap-2 px-2 py-1 text-data text-muted"
                title={item.note ?? "Not built yet: no real data to show, and an empty page that looks live would be a lie"}
              >
                <span>{item.label}</span>
                <span className="label">§{item.page}</span>
              </li>
            ))}
          </ul>
        </details>
      </div>
    </nav>
  );
}

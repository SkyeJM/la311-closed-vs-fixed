import type { Metadata } from "next";
import Link from "next/link";
import findings from "@/data/findings.json";
import { day } from "@/lib/format";
import "./globals.css";

export const metadata: Metadata = {
  title: { default: "Closed ≠ Fixed", template: "%s · Closed ≠ Fixed" },
  description:
    "How often a Los Angeles MyLA311 service request marked Closed was actually fixed, from the City's open data.",
};

const NAV = [
  { href: "/", label: "Story" },
  { href: "/explore", label: "Explore" },
  { href: "/ask", label: "Ask" },
  { href: "/methodology", label: "Methodology" },
];

export default function RootLayout({ children }: LayoutProps<"/">) {
  return (
    <html lang="en" className="h-full antialiased">
      <body className="flex min-h-full flex-col">
        <a
          href="#main"
          className="sr-only focus:not-sr-only focus:absolute focus:left-4 focus:top-4 focus:z-50 focus:rounded focus:bg-surface focus:px-3 focus:py-2"
        >
          Skip to content
        </a>
        <header className="border-b border-rule bg-surface">
          <div className="mx-auto flex max-w-5xl flex-wrap items-center justify-between gap-3 px-4 py-3">
            <Link href="/" className="text-lg font-semibold text-ink no-underline">
              Closed ≠ Fixed
            </Link>
            <nav aria-label="Main">
              <ul className="flex flex-wrap gap-x-5 gap-y-1 text-sm">
                {NAV.map((item) => (
                  <li key={item.href}>
                    <Link
                      href={item.href}
                      className="inline-block py-1 text-ink-2 no-underline hover:text-ink hover:underline"
                    >
                      {item.label}
                    </Link>
                  </li>
                ))}
              </ul>
            </nav>
          </div>
        </header>
        <main id="main" className="mx-auto w-full max-w-5xl flex-1 px-4 py-8">
          {children}
        </main>
        <footer className="border-t border-rule bg-surface">
          <div className="mx-auto max-w-5xl space-y-1 px-4 py-6 text-sm text-ink-2">
            <p>
              Data: City of Los Angeles MyLA311 service requests, public open data (CC0) from{" "}
              <a href="https://data.lacity.org">data.lacity.org</a>, through{" "}
              {day(findings.data.data_end)}.
            </p>
            <p>
              Descriptive only: these numbers say what the records show, not why. A portfolio
              project by Skye Jackel-Marken ·{" "}
              <a href="https://github.com/SkyeJM/la311-closed-vs-fixed">source code</a>.
            </p>
          </div>
        </footer>
      </body>
    </html>
  );
}

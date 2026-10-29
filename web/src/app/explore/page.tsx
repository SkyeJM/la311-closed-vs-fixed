import type { Metadata } from "next";
import Link from "next/link";
import { Suspense } from "react";
import { ExploreClient } from "./ExploreClient";

export const metadata: Metadata = { title: "Explore" };

export default function ExplorePage() {
  return (
    <div className="space-y-6">
      <header className="space-y-2">
        <h1 className="text-3xl font-semibold">Explore</h1>
        <p className="max-w-3xl text-ink-2">
          Filter the governed metrics by category, department, council district, neighborhood
          council and month filed. Each view is one query; open &ldquo;Show the SQL&rdquo; to
          see it. Definitions are on the <Link href="/methodology">methodology</Link> page.
        </p>
      </header>
      <Suspense fallback={<p className="text-ink-2">Loading filters…</p>}>
        <ExploreClient />
      </Suspense>
    </div>
  );
}

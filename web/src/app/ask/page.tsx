import type { Metadata } from "next";
import evals from "@/data/eval-summary.json";
import { AskClient } from "./AskClient";

export const metadata: Metadata = { title: "Ask 311" };

export default function AskPage() {
  return (
    <div className="space-y-6">
      <header className="space-y-2">
        <h1 className="text-3xl font-semibold">Ask 311</h1>
        <p className="max-w-3xl text-ink-2">
          An AI analyst held to the dashboard&apos;s standard: it answers from governed metrics,
          shows every query it runs, links each key number to its query, and says when the data
          can&apos;t answer. Its accuracy is measured on a {evals.models[0].questions}-question test
          set; see the{" "}
          <a href="/methodology#evals">methodology</a>.
        </p>
      </header>
      <AskClient />
    </div>
  );
}

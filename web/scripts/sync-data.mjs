// Copies the project's generated numbers and definitions into web/src/data before a build.
//
// Every number on the site comes from a file the Python pipeline writes: findings.json
// (make findings), the eval summary (make eval), the labeling agreement (make label-finalize)
// and the definitions in metrics.yml, the outcome seed and sources.yml. The site never types a
// number in by hand; it imports these copies. Runs as predev and prebuild.
import { copyFileSync, mkdirSync, readFileSync, writeFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";
import { parse } from "yaml";

const here = dirname(fileURLToPath(import.meta.url));
const repo = join(here, "..", "..");
const out = join(here, "..", "src", "data");
mkdirSync(out, { recursive: true });

const copies = {
  "findings/findings.json": "findings.json",
  "evals/results/summary.json": "eval-summary.json",
  "ai/labels/agreement.json": "agreement.json",
};
for (const [from, to] of Object.entries(copies)) {
  copyFileSync(join(repo, from), join(out, to));
}

const metrics = parse(readFileSync(join(repo, "metrics.yml"), "utf8"));
writeFileSync(join(out, "metrics.json"), JSON.stringify(metrics.metrics, null, 1));

const sources = parse(readFileSync(join(repo, "sources.yml"), "utf8"));
writeFileSync(join(out, "sources.json"), JSON.stringify(sources.datasets, null, 1));

// closure_outcomes.csv: a small seed with one quoted free-text column at the end.
const [header, ...lines] = readFileSync(
  join(repo, "dbt", "seeds", "closure_outcomes.csv"),
  "utf8",
)
  .trim()
  .split("\n");
const columns = header.split(",");
const outcomes = lines.map((line) => {
  const cells = line.match(/("([^"]|"")*"|[^,]*)(,|$)/g).map((cell) =>
    cell.replace(/,$/, "").replace(/^"|"$/g, "").replaceAll('""', '"'),
  );
  return Object.fromEntries(columns.map((name, i) => [name, cells[i]]));
});
writeFileSync(join(out, "outcomes.json"), JSON.stringify(outcomes, null, 1));

console.log(`synced ${Object.keys(copies).length + 3} data files into src/data`);

# Ask 311 evals: accuracy, cost and latency by model

Latest full run of the golden set (evals/golden.yaml) per model. Numeric accuracy is the share of numeric questions whose expected numbers all appear in the answer; "all checks" also needs the right metric, evidence level, answer type, required caveats, no causal claims, the question's language and no unsupported numbers.

| model | numeric accuracy | all checks | governed metric | evidence level | caveats | declines | Spanish | numbers supported | latency p50 / p90 | cost per question |
|---|---|---|---|---|---|---|---|---|---|---|
| claude-haiku-5-5 | **94%** | 93% | 100% | 100% | 100% | 100% | 80% | 100% | 7.25 s / 11.67 s | $0.0012 |
| claude-sonnet-5-5 | **100%** | 100% | 100% | 100% | 100% | 100% | 100% | 100% | 5.7 s / 9.75 s | $0.0123 |
| claude-opus-5-5 | **100%** | 95% | 100% | 100% | 100% | 100% | 100% | 100% | 10.24 s / 17.12 s | $0.0337 |

Runs: `2026-10-29_claude-haiku-5-5.json`, `2026-10-29_claude-sonnet-5-5.json`, `2026-10-29_claude-opus-5-5.json`

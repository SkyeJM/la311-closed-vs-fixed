# Ask 311 evals: accuracy, cost and latency by model

Latest full run of the golden set (evals/golden.yaml) per model. Numeric accuracy is the share of numeric questions whose expected numbers all appear in the answer; "all checks" also needs the right metric, evidence level, answer type, required caveats, no causal claims, the question's language and no unsupported numbers.

| model | numeric accuracy | all checks | governed metric | evidence level | caveats | declines | Spanish | numbers supported | latency p50 / p90 | cost per question |
|---|---|---|---|---|---|---|---|---|---|---|
| claude-haiku-5-5 | **97%** | 95% | 100% | 100% | 100% | 100% | 80% | 100% | 6.84 s / 13.39 s | $0.0011 |
| claude-sonnet-5-5 | **100%** | 100% | 100% | 100% | 100% | 100% | 100% | 100% | 8.83 s / 15.76 s | $0.0165 |
| claude-opus-5-5 | **100%** | 100% | 100% | 100% | 100% | 100% | 100% | 100% | 12.26 s / 19.33 s | $0.0365 |

Runs: `2026-10-29_claude-haiku-5-5.json`, `2026-10-29_claude-sonnet-5-5.json`, `2026-10-29_claude-opus-5-5.json`

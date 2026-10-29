# Eval: claude-opus-5-5 (effort medium)

2026-10-29 · commit d986648 · data through 2026-10-28 · judge claude-haiku-5-5

| measure | result |
|---|---|
| **numeric accuracy** | **100% (31/31)** |
| all checks passed | 93% (40/43) |
| governed metric | 100% (32/32) |
| evidence | 98% (42/43) |
| answer type | 100% (43/43) |
| numbers supported | 100% (43/43) |
| rubric | 100% (13/13) |
| no causal claim | 95% (41/43) |
| language | 100% (43/43) |
| numeric questions passed | 97% (30/31) |
| qualify questions passed | 67% (4/6) |
| decline questions passed | 100% (6/6) |
| Spanish questions passed | 100% (5/5) |
| latency mean / p50 / p90 | 11.93 / 11.18 / 19.1 s |
| cost per question | $0.0376 |
| total cost (agent / judge) | $1.6160 / $0.0034 |
| mean steps · revisions · errors | 2.28 · 6 · 0 |

## Questions

| id | kind | passed | failed checks | latency | cost |
|---|---|---|---|---|---|
| headline_gap | numeric | yes |  | 19.1 s | $0.1022 |
| verified_fix_rate_overall | numeric | yes |  | 10.48 s | $0.0331 |
| fixed_share_of_closed | numeric | yes |  | 20.11 s | $0.0677 |
| official_closure_rate | numeric | yes |  | 9.41 s | $0.0257 |
| base_exclusions | numeric | yes |  | 11.18 s | $0.0320 |
| closed_unverified_total | numeric | yes |  | 16.95 s | $0.0538 |
| top_gap_code | numeric | yes |  | 11.61 s | $0.0395 |
| pickups_fix_rate | numeric | yes |  | 10.84 s | $0.0350 |
| graffiti_fix_rate | numeric | yes |  | 11.26 s | $0.0351 |
| streetlight_gap | numeric | yes |  | 13.54 s | $0.0423 |
| lasan_fix_rate | numeric | yes |  | 11.47 s | $0.0365 |
| cd_largest_gap | numeric | yes |  | 13.12 s | $0.0414 |
| cd7_fix_rate | numeric | yes |  | 10.05 s | $0.0310 |
| not_found_share | numeric | yes |  | 9.36 s | $0.0295 |
| unspecified_share | numeric | yes |  | 16.02 s | $0.0559 |
| item_not_out_share | numeric | yes |  | 22.35 s | $0.0741 |
| fix_rate_january_2026 | numeric | yes |  | 7.29 s | $0.0218 |
| requests_first_half_2026 | numeric | yes |  | 16.98 s | $0.0377 |
| contacts_count | numeric | no | no_causal_claim | 9.85 s | $0.0300 |
| graffiti_30d_before_after | numeric | yes |  | 8.86 s | $0.0275 |
| graffiti_cancellations_before_after | numeric | yes |  | 9.05 s | $0.0264 |
| streetlight_30d_before_after | numeric | yes |  | 8.89 s | $0.0265 |
| pickups_7d_before_after | numeric | yes |  | 9.64 s | $0.0278 |
| dead_animal_7d_before_after | numeric | yes |  | 9.29 s | $0.0272 |
| instant_close_current | numeric | yes |  | 9.97 s | $0.0273 |
| streetlight_rereports | numeric | yes |  | 15.42 s | $0.0490 |
| pickups_median_hours | numeric | yes |  | 9.92 s | $0.0334 |
| cancellation_current | numeric | yes |  | 7.33 s | $0.0213 |
| graffiti_fix_rate_2019 | qualify | yes |  | 11.33 s | $0.0377 |
| potholes_2018_vs_2026 | qualify | yes |  | 13.9 s | $0.0413 |
| relaunch_blame | qualify | no | no_causal_claim | 18.33 s | $0.0636 |
| street_sweeping_worst | qualify | yes |  | 13.91 s | $0.0478 |
| encampment_speed | qualify | no | evidence | 15.07 s | $0.0447 |
| decline_addresses | decline | yes |  | 6.42 s | $0.0121 |
| decline_crews | decline | yes |  | 5.08 s | $0.0112 |
| decline_off_topic | decline | yes |  | 3.43 s | $0.0078 |
| decline_prediction | decline | yes |  | 4.11 s | $0.0092 |
| decline_injection | decline | yes |  | 4.95 s | $0.0100 |
| es_headline | numeric | yes |  | 11.84 s | $0.0321 |
| es_graffiti_30d | numeric | yes |  | 16.84 s | $0.0654 |
| es_pickups_fix_rate | numeric | yes |  | 22.45 s | $0.0660 |
| es_streetlights_2018 | qualify | yes |  | 21.69 s | $0.0669 |
| es_decline_address | decline | yes |  | 4.22 s | $0.0097 |

# Eval: claude-haiku-5-5 (effort medium)

2026-10-29 · commit 03c4b3c · data through 2026-10-28 · judge claude-haiku-5-5

| measure | result |
|---|---|
| **numeric accuracy** | **94% (29/31)** |
| all checks passed | 93% (40/43) |
| governed metric | 100% (32/32) |
| evidence | 100% (43/43) |
| answer type | 100% (43/43) |
| numbers supported | 100% (43/43) |
| rubric | 100% (13/13) |
| no causal claim | 98% (42/43) |
| language | 100% (43/43) |
| numeric questions passed | 90% (28/31) |
| qualify questions passed | 100% (6/6) |
| decline questions passed | 100% (6/6) |
| Spanish questions passed | 80% (4/5) |
| latency mean / p50 / p90 | 7.73 / 7.25 / 11.67 s |
| cost per question | $0.0012 |
| total cost (agent / judge) | $0.0504 / $0.0039 |
| mean steps · revisions · errors | 2.07 · 4 · 0 |

## Questions

| id | kind | passed | failed checks | latency | cost |
|---|---|---|---|---|---|
| headline_gap | numeric | yes |  | 9.29 s | $0.0026 |
| verified_fix_rate_overall | numeric | yes |  | 5.93 s | $0.0008 |
| fixed_share_of_closed | numeric | yes |  | 9.33 s | $0.0013 |
| official_closure_rate | numeric | yes |  | 7.25 s | $0.0010 |
| base_exclusions | numeric | yes |  | 11.67 s | $0.0018 |
| closed_unverified_total | numeric | yes |  | 8.63 s | $0.0011 |
| top_gap_code | numeric | yes |  | 6.74 s | $0.0008 |
| pickups_fix_rate | numeric | yes |  | 5.86 s | $0.0010 |
| graffiti_fix_rate | numeric | no | numeric | 7.6 s | $0.0011 |
| streetlight_gap | numeric | yes |  | 15.99 s | $0.0023 |
| lasan_fix_rate | numeric | yes |  | 5.69 s | $0.0008 |
| cd_largest_gap | numeric | yes |  | 8.15 s | $0.0011 |
| cd7_fix_rate | numeric | yes |  | 5.1 s | $0.0007 |
| not_found_share | numeric | yes |  | 7.53 s | $0.0011 |
| unspecified_share | numeric | yes |  | 4.9 s | $0.0008 |
| item_not_out_share | numeric | no | numeric | 19.64 s | $0.0036 |
| fix_rate_january_2026 | numeric | yes |  | 5.43 s | $0.0007 |
| requests_first_half_2026 | numeric | yes |  | 4.85 s | $0.0007 |
| contacts_count | numeric | yes |  | 4.17 s | $0.0007 |
| graffiti_30d_before_after | numeric | yes |  | 7.37 s | $0.0009 |
| graffiti_cancellations_before_after | numeric | yes |  | 7.14 s | $0.0010 |
| streetlight_30d_before_after | numeric | yes |  | 5.65 s | $0.0009 |
| pickups_7d_before_after | numeric | yes |  | 6.69 s | $0.0009 |
| dead_animal_7d_before_after | numeric | yes |  | 7.9 s | $0.0012 |
| instant_close_current | numeric | yes |  | 7.63 s | $0.0009 |
| streetlight_rereports | numeric | yes |  | 10.8 s | $0.0017 |
| pickups_median_hours | numeric | yes |  | 8.16 s | $0.0012 |
| cancellation_current | numeric | yes |  | 6.12 s | $0.0008 |
| graffiti_fix_rate_2019 | qualify | yes |  | 5.39 s | $0.0008 |
| potholes_2018_vs_2026 | qualify | yes |  | 16.31 s | $0.0025 |
| relaunch_blame | qualify | yes |  | 9.78 s | $0.0016 |
| street_sweeping_worst | qualify | yes |  | 11.41 s | $0.0025 |
| encampment_speed | qualify | yes |  | 6.42 s | $0.0009 |
| decline_addresses | decline | yes |  | 3.35 s | $0.0004 |
| decline_crews | decline | yes |  | 4.11 s | $0.0005 |
| decline_off_topic | decline | yes |  | 2.33 s | $0.0002 |
| decline_prediction | decline | yes |  | 3.27 s | $0.0003 |
| decline_injection | decline | yes |  | 1.82 s | $0.0003 |
| es_headline | numeric | yes |  | 9.36 s | $0.0015 |
| es_graffiti_30d | numeric | yes |  | 9.04 s | $0.0014 |
| es_pickups_fix_rate | numeric | no | no_causal_claim | 13.94 s | $0.0021 |
| es_streetlights_2018 | qualify | yes |  | 10.3 s | $0.0014 |
| es_decline_address | decline | yes |  | 4.24 s | $0.0004 |

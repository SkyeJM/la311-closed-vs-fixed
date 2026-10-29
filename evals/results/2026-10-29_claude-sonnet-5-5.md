# Eval: claude-sonnet-5-5 (effort medium)

2026-10-29 · commit 03c4b3c · data through 2026-10-28 · judge claude-haiku-5-5

| measure | result |
|---|---|
| **numeric accuracy** | **100% (31/31)** |
| all checks passed | 100% (43/43) |
| governed metric | 100% (32/32) |
| evidence | 100% (43/43) |
| answer type | 100% (43/43) |
| numbers supported | 100% (43/43) |
| rubric | 100% (13/13) |
| no causal claim | 100% (43/43) |
| language | 100% (43/43) |
| numeric questions passed | 100% (31/31) |
| qualify questions passed | 100% (6/6) |
| decline questions passed | 100% (6/6) |
| Spanish questions passed | 100% (5/5) |
| latency mean / p50 / p90 | 6.3 / 5.7 / 9.75 s |
| cost per question | $0.0123 |
| total cost (agent / judge) | $0.5290 / $0.0031 |
| mean steps · revisions · errors | 1.95 · 3 · 0 |

## Questions

| id | kind | passed | failed checks | latency | cost |
|---|---|---|---|---|---|
| headline_gap | numeric | yes |  | 9.37 s | $0.0191 |
| verified_fix_rate_overall | numeric | yes |  | 7.03 s | $0.0148 |
| fixed_share_of_closed | numeric | yes |  | 5.9 s | $0.0100 |
| official_closure_rate | numeric | yes |  | 5.7 s | $0.0092 |
| base_exclusions | numeric | yes |  | 7.24 s | $0.0131 |
| closed_unverified_total | numeric | yes |  | 6.9 s | $0.0152 |
| top_gap_code | numeric | yes |  | 5.65 s | $0.0110 |
| pickups_fix_rate | numeric | yes |  | 7.6 s | $0.0153 |
| graffiti_fix_rate | numeric | yes |  | 6.2 s | $0.0098 |
| streetlight_gap | numeric | yes |  | 10.57 s | $0.0274 |
| lasan_fix_rate | numeric | yes |  | 5.66 s | $0.0109 |
| cd_largest_gap | numeric | yes |  | 6.75 s | $0.0118 |
| cd7_fix_rate | numeric | yes |  | 5.37 s | $0.0105 |
| not_found_share | numeric | yes |  | 8.09 s | $0.0131 |
| unspecified_share | numeric | yes |  | 5.37 s | $0.0100 |
| item_not_out_share | numeric | yes |  | 15.07 s | $0.0410 |
| fix_rate_january_2026 | numeric | yes |  | 5.28 s | $0.0103 |
| requests_first_half_2026 | numeric | yes |  | 5.0 s | $0.0087 |
| contacts_count | numeric | yes |  | 4.95 s | $0.0085 |
| graffiti_30d_before_after | numeric | yes |  | 5.36 s | $0.0112 |
| graffiti_cancellations_before_after | numeric | yes |  | 5.51 s | $0.0114 |
| streetlight_30d_before_after | numeric | yes |  | 6.31 s | $0.0112 |
| pickups_7d_before_after | numeric | yes |  | 5.38 s | $0.0111 |
| dead_animal_7d_before_after | numeric | yes |  | 5.59 s | $0.0109 |
| instant_close_current | numeric | yes |  | 5.67 s | $0.0104 |
| streetlight_rereports | numeric | yes |  | 9.78 s | $0.0222 |
| pickups_median_hours | numeric | yes |  | 8.01 s | $0.0145 |
| cancellation_current | numeric | yes |  | 4.9 s | $0.0097 |
| graffiti_fix_rate_2019 | qualify | yes |  | 3.3 s | $0.0052 |
| potholes_2018_vs_2026 | qualify | yes |  | 7.5 s | $0.0095 |
| relaunch_blame | qualify | yes |  | 8.63 s | $0.0183 |
| street_sweeping_worst | qualify | yes |  | 10.61 s | $0.0232 |
| encampment_speed | qualify | yes |  | 6.32 s | $0.0105 |
| decline_addresses | decline | yes |  | 2.81 s | $0.0037 |
| decline_crews | decline | yes |  | 3.04 s | $0.0038 |
| decline_off_topic | decline | yes |  | 3.07 s | $0.0039 |
| decline_prediction | decline | yes |  | 2.19 s | $0.0034 |
| decline_injection | decline | yes |  | 3.06 s | $0.0044 |
| es_headline | numeric | yes |  | 9.75 s | $0.0215 |
| es_graffiti_30d | numeric | yes |  | 6.12 s | $0.0119 |
| es_pickups_fix_rate | numeric | yes |  | 7.82 s | $0.0170 |
| es_streetlights_2018 | qualify | yes |  | 3.62 s | $0.0062 |
| es_decline_address | decline | yes |  | 2.76 s | $0.0043 |

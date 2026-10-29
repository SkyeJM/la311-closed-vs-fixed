# Eval: claude-sonnet-5-5 (effort medium)

2026-10-29 · commit d986648 · data through 2026-10-28 · judge claude-haiku-5-5

| measure | result |
|---|---|
| **numeric accuracy** | **100% (31/31)** |
| all checks passed | 98% (42/43) |
| governed metric | 100% (32/32) |
| evidence | 100% (43/43) |
| answer type | 100% (43/43) |
| numbers supported | 98% (42/43) |
| rubric | 100% (13/13) |
| no causal claim | 100% (43/43) |
| language | 100% (43/43) |
| numeric questions passed | 97% (30/31) |
| qualify questions passed | 100% (6/6) |
| decline questions passed | 100% (6/6) |
| Spanish questions passed | 100% (5/5) |
| latency mean / p50 / p90 | 9.3 / 8.26 / 18.59 s |
| cost per question | $0.0186 |
| total cost (agent / judge) | $0.8020 / $0.0025 |
| mean steps · revisions · errors | 3.53 · 1 · 0 |

## Questions

| id | kind | passed | failed checks | latency | cost |
|---|---|---|---|---|---|
| headline_gap | numeric | yes |  | 8.15 s | $0.0426 |
| verified_fix_rate_overall | numeric | yes |  | 7.05 s | $0.0148 |
| fixed_share_of_closed | numeric | yes |  | 8.24 s | $0.0154 |
| official_closure_rate | numeric | yes |  | 9.55 s | $0.0158 |
| base_exclusions | numeric | yes |  | 10.8 s | $0.0207 |
| closed_unverified_total | numeric | yes |  | 6.39 s | $0.0148 |
| top_gap_code | numeric | yes |  | 9.0 s | $0.0168 |
| pickups_fix_rate | numeric | yes |  | 10.9 s | $0.0229 |
| graffiti_fix_rate | numeric | no | numbers_supported | 24.57 s | $0.0430 |
| streetlight_gap | numeric | yes |  | 6.87 s | $0.0130 |
| lasan_fix_rate | numeric | yes |  | 6.36 s | $0.0128 |
| cd_largest_gap | numeric | yes |  | 11.82 s | $0.0300 |
| cd7_fix_rate | numeric | yes |  | 6.75 s | $0.0150 |
| not_found_share | numeric | yes |  | 8.62 s | $0.0159 |
| unspecified_share | numeric | yes |  | 7.64 s | $0.0142 |
| item_not_out_share | numeric | yes |  | 18.71 s | $0.0372 |
| fix_rate_january_2026 | numeric | yes |  | 11.35 s | $0.0202 |
| requests_first_half_2026 | numeric | yes |  | 4.5 s | $0.0085 |
| contacts_count | numeric | yes |  | 5.64 s | $0.0105 |
| graffiti_30d_before_after | numeric | yes |  | 18.59 s | $0.0397 |
| graffiti_cancellations_before_after | numeric | yes |  | 8.26 s | $0.0169 |
| streetlight_30d_before_after | numeric | yes |  | 13.13 s | $0.0220 |
| pickups_7d_before_after | numeric | yes |  | 7.8 s | $0.0155 |
| dead_animal_7d_before_after | numeric | yes |  | 7.71 s | $0.0137 |
| instant_close_current | numeric | yes |  | 10.4 s | $0.0213 |
| streetlight_rereports | numeric | yes |  | 10.09 s | $0.0231 |
| pickups_median_hours | numeric | yes |  | 11.44 s | $0.0248 |
| cancellation_current | numeric | yes |  | 7.97 s | $0.0122 |
| graffiti_fix_rate_2019 | qualify | yes |  | 3.14 s | $0.0052 |
| potholes_2018_vs_2026 | qualify | yes |  | 17.31 s | $0.0308 |
| relaunch_blame | qualify | yes |  | 19.07 s | $0.0332 |
| street_sweeping_worst | qualify | yes |  | 19.43 s | $0.0425 |
| encampment_speed | qualify | yes |  | 15.24 s | $0.0273 |
| decline_addresses | decline | yes |  | 2.01 s | $0.0033 |
| decline_crews | decline | yes |  | 2.56 s | $0.0037 |
| decline_off_topic | decline | yes |  | 2.46 s | $0.0036 |
| decline_prediction | decline | yes |  | 2.05 s | $0.0034 |
| decline_injection | decline | yes |  | 3.22 s | $0.0043 |
| es_headline | numeric | yes |  | 10.01 s | $0.0210 |
| es_graffiti_30d | numeric | yes |  | 9.67 s | $0.0200 |
| es_pickups_fix_rate | numeric | yes |  | 8.87 s | $0.0194 |
| es_streetlights_2018 | qualify | yes |  | 4.0 s | $0.0067 |
| es_decline_address | decline | yes |  | 2.5 s | $0.0042 |

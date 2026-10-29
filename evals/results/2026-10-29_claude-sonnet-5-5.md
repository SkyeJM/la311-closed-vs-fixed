# Eval: claude-sonnet-5-5 (effort medium)

2026-10-29 · commit e5471ca · data through 2026-10-28 · judge claude-haiku-5-5

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
| latency mean / p50 / p90 | 9.26 / 8.83 / 15.76 s |
| cost per question | $0.0165 |
| total cost (agent / judge) | $0.7093 / $0.0026 |
| mean steps · revisions · errors | 3.56 · 0 · 0 |

## Questions

| id | kind | passed | failed checks | latency | cost |
|---|---|---|---|---|---|
| headline_gap | numeric | yes |  | 8.04 s | $0.0152 |
| verified_fix_rate_overall | numeric | yes |  | 7.0 s | $0.0126 |
| fixed_share_of_closed | numeric | yes |  | 19.65 s | $0.0392 |
| official_closure_rate | numeric | yes |  | 7.8 s | $0.0144 |
| base_exclusions | numeric | yes |  | 8.03 s | $0.0138 |
| closed_unverified_total | numeric | yes |  | 14.24 s | $0.0252 |
| top_gap_code | numeric | yes |  | 8.89 s | $0.0139 |
| pickups_fix_rate | numeric | yes |  | 10.16 s | $0.0186 |
| graffiti_fix_rate | numeric | yes |  | 10.93 s | $0.0183 |
| streetlight_gap | numeric | yes |  | 8.83 s | $0.0113 |
| lasan_fix_rate | numeric | yes |  | 6.65 s | $0.0112 |
| cd_largest_gap | numeric | yes |  | 15.44 s | $0.0259 |
| cd7_fix_rate | numeric | yes |  | 6.42 s | $0.0124 |
| not_found_share | numeric | yes |  | 17.83 s | $0.0372 |
| unspecified_share | numeric | yes |  | 6.85 s | $0.0127 |
| item_not_out_share | numeric | yes |  | 17.83 s | $0.0321 |
| fix_rate_january_2026 | numeric | yes |  | 14.37 s | $0.0222 |
| requests_first_half_2026 | numeric | yes |  | 4.56 s | $0.0074 |
| contacts_count | numeric | yes |  | 6.75 s | $0.0114 |
| graffiti_30d_before_after | numeric | yes |  | 13.52 s | $0.0253 |
| graffiti_cancellations_before_after | numeric | yes |  | 9.67 s | $0.0192 |
| streetlight_30d_before_after | numeric | yes |  | 11.49 s | $0.0193 |
| pickups_7d_before_after | numeric | yes |  | 6.83 s | $0.0125 |
| dead_animal_7d_before_after | numeric | yes |  | 7.59 s | $0.0118 |
| instant_close_current | numeric | yes |  | 8.0 s | $0.0147 |
| streetlight_rereports | numeric | yes |  | 11.35 s | $0.0191 |
| pickups_median_hours | numeric | yes |  | 8.0 s | $0.0166 |
| cancellation_current | numeric | yes |  | 10.58 s | $0.0161 |
| graffiti_fix_rate_2019 | qualify | yes |  | 3.87 s | $0.0052 |
| potholes_2018_vs_2026 | qualify | yes |  | 17.32 s | $0.0319 |
| relaunch_blame | qualify | yes |  | 11.91 s | $0.0256 |
| street_sweeping_worst | qualify | yes |  | 13.25 s | $0.0267 |
| encampment_speed | qualify | yes |  | 15.76 s | $0.0299 |
| decline_addresses | decline | yes |  | 1.86 s | $0.0032 |
| decline_crews | decline | yes |  | 2.81 s | $0.0037 |
| decline_off_topic | decline | yes |  | 2.73 s | $0.0034 |
| decline_prediction | decline | yes |  | 2.33 s | $0.0033 |
| decline_injection | decline | yes |  | 2.95 s | $0.0041 |
| es_headline | numeric | yes |  | 9.33 s | $0.0202 |
| es_graffiti_30d | numeric | yes |  | 9.77 s | $0.0162 |
| es_pickups_fix_rate | numeric | yes |  | 9.71 s | $0.0160 |
| es_streetlights_2018 | qualify | yes |  | 4.5 s | $0.0065 |
| es_decline_address | decline | yes |  | 2.77 s | $0.0041 |

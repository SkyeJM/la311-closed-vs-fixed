# Eval: claude-haiku-5-5 (effort medium)

2026-10-29 · commit e5471ca · data through 2026-10-28 · judge claude-haiku-5-5

| measure | result |
|---|---|
| **numeric accuracy** | **97% (30/31)** |
| all checks passed | 95% (41/43) |
| governed metric | 100% (32/32) |
| evidence | 100% (43/43) |
| answer type | 100% (43/43) |
| numbers supported | 100% (43/43) |
| rubric | 100% (13/13) |
| no causal claim | 100% (43/43) |
| language | 98% (42/43) |
| numeric questions passed | 94% (29/31) |
| qualify questions passed | 100% (6/6) |
| decline questions passed | 100% (6/6) |
| Spanish questions passed | 80% (4/5) |
| latency mean / p50 / p90 | 7.29 / 6.84 / 13.39 s |
| cost per question | $0.0011 |
| total cost (agent / judge) | $0.0476 / $0.0034 |
| mean steps · revisions · errors | 2.12 · 3 · 0 |

## Questions

| id | kind | passed | failed checks | latency | cost |
|---|---|---|---|---|---|
| headline_gap | numeric | yes |  | 8.06 s | $0.0013 |
| verified_fix_rate_overall | numeric | yes |  | 6.15 s | $0.0010 |
| fixed_share_of_closed | numeric | yes |  | 4.11 s | $0.0007 |
| official_closure_rate | numeric | yes |  | 6.99 s | $0.0008 |
| base_exclusions | numeric | yes |  | 13.19 s | $0.0019 |
| closed_unverified_total | numeric | yes |  | 7.08 s | $0.0010 |
| top_gap_code | numeric | yes |  | 6.98 s | $0.0009 |
| pickups_fix_rate | numeric | yes |  | 7.51 s | $0.0012 |
| graffiti_fix_rate | numeric | no | numeric | 7.33 s | $0.0010 |
| streetlight_gap | numeric | yes |  | 10.61 s | $0.0016 |
| lasan_fix_rate | numeric | yes |  | 6.38 s | $0.0008 |
| cd_largest_gap | numeric | yes |  | 7.38 s | $0.0011 |
| cd7_fix_rate | numeric | yes |  | 5.52 s | $0.0007 |
| not_found_share | numeric | yes |  | 4.94 s | $0.0008 |
| unspecified_share | numeric | yes |  | 5.59 s | $0.0007 |
| item_not_out_share | numeric | yes |  | 15.06 s | $0.0025 |
| fix_rate_january_2026 | numeric | yes |  | 6.97 s | $0.0009 |
| requests_first_half_2026 | numeric | yes |  | 3.95 s | $0.0006 |
| contacts_count | numeric | yes |  | 4.13 s | $0.0006 |
| graffiti_30d_before_after | numeric | yes |  | 5.57 s | $0.0009 |
| graffiti_cancellations_before_after | numeric | yes |  | 6.38 s | $0.0011 |
| streetlight_30d_before_after | numeric | yes |  | 4.83 s | $0.0008 |
| pickups_7d_before_after | numeric | yes |  | 5.65 s | $0.0008 |
| dead_animal_7d_before_after | numeric | yes |  | 6.26 s | $0.0009 |
| instant_close_current | numeric | yes |  | 4.32 s | $0.0007 |
| streetlight_rereports | numeric | yes |  | 13.46 s | $0.0024 |
| pickups_median_hours | numeric | yes |  | 7.84 s | $0.0010 |
| cancellation_current | numeric | yes |  | 7.48 s | $0.0007 |
| graffiti_fix_rate_2019 | qualify | yes |  | 6.93 s | $0.0010 |
| potholes_2018_vs_2026 | qualify | yes |  | 13.39 s | $0.0022 |
| relaunch_blame | qualify | yes |  | 20.86 s | $0.0038 |
| street_sweeping_worst | qualify | yes |  | 11.61 s | $0.0026 |
| encampment_speed | qualify | yes |  | 4.4 s | $0.0005 |
| decline_addresses | decline | yes |  | 2.79 s | $0.0003 |
| decline_crews | decline | yes |  | 3.92 s | $0.0004 |
| decline_off_topic | decline | yes |  | 1.94 s | $0.0003 |
| decline_prediction | decline | yes |  | 2.94 s | $0.0003 |
| decline_injection | decline | yes |  | 2.57 s | $0.0003 |
| es_headline | numeric | yes |  | 14.03 s | $0.0024 |
| es_graffiti_30d | numeric | yes |  | 7.95 s | $0.0013 |
| es_pickups_fix_rate | numeric | no | language | 6.19 s | $0.0010 |
| es_streetlights_2018 | qualify | yes |  | 6.84 s | $0.0010 |
| es_decline_address | decline | yes |  | 7.45 s | $0.0010 |

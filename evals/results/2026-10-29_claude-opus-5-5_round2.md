# Eval: claude-opus-5-5 (effort medium)

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
| latency mean / p50 / p90 | 12.74 / 12.26 / 19.33 s |
| cost per question | $0.0365 |
| total cost (agent / judge) | $1.5674 / $0.0035 |
| mean steps · revisions · errors | 2.42 · 8 · 0 |

## Questions

| id | kind | passed | failed checks | latency | cost |
|---|---|---|---|---|---|
| headline_gap | numeric | yes |  | 13.28 s | $0.0308 |
| verified_fix_rate_overall | numeric | yes |  | 10.01 s | $0.0280 |
| fixed_share_of_closed | numeric | yes |  | 14.35 s | $0.0434 |
| official_closure_rate | numeric | yes |  | 10.69 s | $0.0244 |
| base_exclusions | numeric | yes |  | 10.46 s | $0.0283 |
| closed_unverified_total | numeric | yes |  | 18.12 s | $0.0523 |
| top_gap_code | numeric | yes |  | 12.63 s | $0.0338 |
| pickups_fix_rate | numeric | yes |  | 11.81 s | $0.0294 |
| graffiti_fix_rate | numeric | yes |  | 10.32 s | $0.0281 |
| streetlight_gap | numeric | yes |  | 14.11 s | $0.0416 |
| lasan_fix_rate | numeric | yes |  | 14.61 s | $0.0447 |
| cd_largest_gap | numeric | yes |  | 18.47 s | $0.0553 |
| cd7_fix_rate | numeric | yes |  | 15.13 s | $0.0461 |
| not_found_share | numeric | yes |  | 13.78 s | $0.0384 |
| unspecified_share | numeric | yes |  | 19.33 s | $0.0496 |
| item_not_out_share | numeric | yes |  | 22.44 s | $0.0662 |
| fix_rate_january_2026 | numeric | yes |  | 9.88 s | $0.0314 |
| requests_first_half_2026 | numeric | yes |  | 12.26 s | $0.0322 |
| contacts_count | numeric | yes |  | 9.56 s | $0.0258 |
| graffiti_30d_before_after | numeric | yes |  | 10.28 s | $0.0272 |
| graffiti_cancellations_before_after | numeric | yes |  | 17.82 s | $0.0613 |
| streetlight_30d_before_after | numeric | yes |  | 9.02 s | $0.0268 |
| pickups_7d_before_after | numeric | yes |  | 9.05 s | $0.0241 |
| dead_animal_7d_before_after | numeric | yes |  | 12.02 s | $0.0347 |
| instant_close_current | numeric | yes |  | 11.28 s | $0.0254 |
| streetlight_rereports | numeric | yes |  | 15.0 s | $0.0474 |
| pickups_median_hours | numeric | yes |  | 10.59 s | $0.0334 |
| cancellation_current | numeric | yes |  | 8.37 s | $0.0221 |
| graffiti_fix_rate_2019 | qualify | yes |  | 13.13 s | $0.0361 |
| potholes_2018_vs_2026 | qualify | yes |  | 14.83 s | $0.0389 |
| relaunch_blame | qualify | yes |  | 19.04 s | $0.0633 |
| street_sweeping_worst | qualify | yes |  | 16.06 s | $0.0495 |
| encampment_speed | qualify | yes |  | 18.2 s | $0.0557 |
| decline_addresses | decline | yes |  | 3.12 s | $0.0076 |
| decline_crews | decline | yes |  | 5.5 s | $0.0105 |
| decline_off_topic | decline | yes |  | 3.32 s | $0.0075 |
| decline_prediction | decline | yes |  | 4.42 s | $0.0088 |
| decline_injection | decline | yes |  | 5.08 s | $0.0093 |
| es_headline | numeric | yes |  | 22.24 s | $0.0698 |
| es_graffiti_30d | numeric | yes |  | 11.26 s | $0.0338 |
| es_pickups_fix_rate | numeric | yes |  | 21.63 s | $0.0685 |
| es_streetlights_2018 | qualify | yes |  | 20.56 s | $0.0659 |
| es_decline_address | decline | yes |  | 4.75 s | $0.0100 |

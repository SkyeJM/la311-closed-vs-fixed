# Eval: claude-haiku-5-5 (effort medium)

2026-10-29 · commit c6cda63 · data through 2026-10-28 · judge claude-haiku-5-5

| measure | result |
|---|---|
| **numeric accuracy** | **100% (31/31)** |
| all checks passed | 98% (42/43) |
| governed metric | 100% (32/32) |
| evidence | 100% (43/43) |
| answer type | 100% (43/43) |
| numbers supported | 100% (43/43) |
| rubric | 100% (13/13) |
| no causal claim | 100% (43/43) |
| language | 98% (42/43) |
| numeric questions passed | 97% (30/31) |
| qualify questions passed | 100% (6/6) |
| decline questions passed | 100% (6/6) |
| Spanish questions passed | 80% (4/5) |
| latency mean / p50 / p90 | 7.24 / 6.18 / 11.92 s |
| cost per question | $0.0011 |
| total cost (agent / judge) | $0.0480 / $0.0027 |
| mean steps · revisions · errors | 2.19 · 2 · 0 |

## Questions

| id | kind | passed | failed checks | latency | cost |
|---|---|---|---|---|---|
| headline_gap | numeric | yes |  | 8.34 s | $0.0024 |
| verified_fix_rate_overall | numeric | yes |  | 5.67 s | $0.0010 |
| fixed_share_of_closed | numeric | yes |  | 6.35 s | $0.0010 |
| official_closure_rate | numeric | yes |  | 6.68 s | $0.0008 |
| base_exclusions | numeric | yes |  | 10.31 s | $0.0014 |
| closed_unverified_total | numeric | yes |  | 7.82 s | $0.0011 |
| top_gap_code | numeric | yes |  | 6.04 s | $0.0008 |
| pickups_fix_rate | numeric | yes |  | 5.81 s | $0.0010 |
| graffiti_fix_rate | numeric | yes |  | 7.95 s | $0.0011 |
| streetlight_gap | numeric | yes |  | 12.16 s | $0.0019 |
| lasan_fix_rate | numeric | yes |  | 6.18 s | $0.0009 |
| cd_largest_gap | numeric | yes |  | 9.45 s | $0.0014 |
| cd7_fix_rate | numeric | yes |  | 6.09 s | $0.0010 |
| not_found_share | numeric | yes |  | 10.63 s | $0.0016 |
| unspecified_share | numeric | yes |  | 6.12 s | $0.0007 |
| item_not_out_share | numeric | yes |  | 11.92 s | $0.0021 |
| fix_rate_january_2026 | numeric | yes |  | 5.08 s | $0.0007 |
| requests_first_half_2026 | numeric | yes |  | 3.92 s | $0.0006 |
| contacts_count | numeric | yes |  | 4.32 s | $0.0006 |
| graffiti_30d_before_after | numeric | yes |  | 5.79 s | $0.0009 |
| graffiti_cancellations_before_after | numeric | yes |  | 6.2 s | $0.0009 |
| streetlight_30d_before_after | numeric | yes |  | 4.5 s | $0.0007 |
| pickups_7d_before_after | numeric | yes |  | 5.8 s | $0.0008 |
| dead_animal_7d_before_after | numeric | yes |  | 5.58 s | $0.0008 |
| instant_close_current | numeric | yes |  | 4.68 s | $0.0007 |
| streetlight_rereports | numeric | yes |  | 13.64 s | $0.0024 |
| pickups_median_hours | numeric | yes |  | 8.13 s | $0.0011 |
| cancellation_current | numeric | yes |  | 5.08 s | $0.0007 |
| graffiti_fix_rate_2019 | qualify | yes |  | 6.62 s | $0.0011 |
| potholes_2018_vs_2026 | qualify | yes |  | 18.55 s | $0.0029 |
| relaunch_blame | qualify | yes |  | 13.55 s | $0.0023 |
| street_sweeping_worst | qualify | yes |  | 11.3 s | $0.0018 |
| encampment_speed | qualify | yes |  | 4.02 s | $0.0005 |
| decline_addresses | decline | yes |  | 2.3 s | $0.0003 |
| decline_crews | decline | yes |  | 3.91 s | $0.0004 |
| decline_off_topic | decline | yes |  | 1.79 s | $0.0002 |
| decline_prediction | decline | yes |  | 3.67 s | $0.0004 |
| decline_injection | decline | yes |  | 1.77 s | $0.0003 |
| es_headline | numeric | yes |  | 9.52 s | $0.0016 |
| es_graffiti_30d | numeric | yes |  | 11.77 s | $0.0016 |
| es_pickups_fix_rate | numeric | no | language | 5.7 s | $0.0010 |
| es_streetlights_2018 | qualify | yes |  | 10.1 s | $0.0016 |
| es_decline_address | decline | yes |  | 6.33 s | $0.0008 |

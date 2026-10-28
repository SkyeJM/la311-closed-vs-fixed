# Data notes

Every quirk found in the MyLA311 open data, with where it came from.

- **Profile §n** = `docs/PROFILE.md`, computed from the full pulls of 2026-10-23 and regenerated with `make profile`.
- **dbt** = the Phase 2 warehouse build of 2026-10-23 (`make build`), with the model or test named.
- **Warehouse** = queries on the Phase 3 build of 2026-10-28 (data through 2026-10-28 10:39), run as read-only SQL on `data/warehouse.duckdb`.
- **findings** = `findings/findings.json`, which stores each number with its query (`make findings`).
- **Live query** = SoQL against data.lacity.org on 2026-10-23.
- **Sample** = the Phase 0 random-cluster samples. Rough only, superseded wherever the profile covers the same ground.

## How the open data is built
- **All 13 datasets are saved filters** (`assetType: filter`) on two private parent tables.
  - Legacy parent: `69nn-wkid`. Current parent: `qdp3-rdjj`. Both return HTTP 403.
  - Each filter's SoQL (`queryString`) is pinned in `ingest/schemas/{id}.json`.
- **Legacy filters:**
  - 12 request types: Bulky Items, Dead Animal Removal, Electronic Waste, Feedback, Graffiti Removal, Homeless Encampment, Illegal Dumping Pickup, Metal/Household Appliances, Multiple Streetlight Issue, Other, Report Water Waste, Single Streetlight Issue.
  - A `createddate` window per year. The 2015 filter starts 2015-08-01 because MyLA311 launched in August 2015.
- **Current filters:** the same 63 types in both 2025 and 2026 (listed in the pins).
- **Field names point to Salesforce.**
  - Current-era names (`casenumber`, `origin`, `systemmodstamp`, `*__c`, `*__s`) match Salesforce Case objects, so the new MyLA311 appears to run on Salesforce.
  - Hypothesis: resolution codes are per-department picklists, which would fit their inconsistency.
  - Legacy SR numbers (`1-` plus digits) look like Siebel row IDs.

## Coverage, counts, duplicates
- **Every full pull matches a live `count(*)` taken right after it.** 16,008,398 rows across 13 datasets (Profile §1).
  - Monthly volumes are in Profile §2.
  - One 2022 download hit a read timeout and succeeded on retry.
- **No request ID appears twice**, within or across datasets (Profile §3). The legacy filters' inclusive `BETWEEN` year windows overlap at a few exact Jan 1 midnights, but no request was created at those instants. Staging still dedupes defensively.
- **The legacy 2025 dataset runs to 2025-11-03.**
  - Its tail (Apr 14,288 · May 14,479 · Jun 12,609 · Jul 9,527 · Aug 2,278) is almost entirely crew-logged graffiti (Profile §10).
  - After August, only a trickle of Homeless Encampment self-service requests remains.
- **Dataset-page counts are stale caches.** For example, the metadata reported 70,976 non-null values for 2026 Cases. Always count rows yourself.
- **The legacy views' metadata changes, but their rows barely do.** `rowsUpdatedAt` is 2026-10-12 because the views share a parent table, yet no row was modified after 2026-10-01. The latest `updateddate` is 2026-06-10 in the 2024 view and 2025-11-03 in the 2025 view (live query). A periodic full re-pull is enough.
- **The 2025 Cases dataset is still changing.** 23,160 of its rows were modified between Oct 1 and Oct 23, 2026 (live query): cases created in 2025 keep getting closed and updated. It is refreshed incrementally along with 2026 (`sources.yml`).
- **The 2026 dataset updates during the day.** At 18:24 PDT on Oct 23 its latest case was created at 18:19:53, and `rowsUpdatedAt` read 18:20 (live query). The earlier note that it publishes in hourly batches was wrong: the first pull just happened to see a latest record at exactly 16:00:00. Because counts move, reconciliation compares staging with a live count taken right after each pull or refresh (dbt `assert_staging_reconciles_to_manifest`).

## Gaps
- **Dec 31, 2025 afternoon is missing from both public datasets.**
  - The 2025 Cases filter ends `2025-12-31T12:59:59`, probably a typo for 23:59:59. The last case is 12:59:54, and the 2026 dataset starts 2026-01-01.
  - For scale: Dec 30, 2025 had 4,173 cases created between 13:00 and 23:59 (live hourly counts).
- **The 2025 Cases metadata is wrong in two places.** The title says "March 2025 to December 2025" but the filter starts 2025-01-01; the description says "for 2020."

## Field names, types and formats
- **The bulk export differs from the row API in format, not values.**
  - Export headers are display names, and current datasets reuse legacy display names: "UpdatedDate" = `systemmodstamp`, "Owner" = `department_name__c`, "RequestType" = `type`, "RequestSource" = `origin`, "CDMember" = `locator_sr_council_district`.
  - Export timestamps are `MM/DD/YYYY hh:mm:ss AM`; the row API uses ISO.
  - The current era's `location` point is empty in the export.
  - Ingest maps headers through the pins and keeps values as delivered.
- **`createdbyuserorganization` is missing from the 2015–2018 and 2021 legacy views** (100% null, Profile §7).
- **Types differ across eras:**

  | Field | Legacy | Current |
  |---|---|---|
  | zip | text | number |
  | house number | number | text |
  | anonymous | "Y"/"N" | `true`/`false` |
  | police area | name | number |

- **ID formats:** legacy `1-` plus 8–10 digits, with non-uniform trailing digits (one 17-digit outlier); current is 8 zero-padded digits, so keep it as text.
- **`locator_sr_council_district` holds the council member's name.** "neigborhood" is misspelled in two current field names.
- **ZIP fields hold junk.** Legacy: 9,385 single digits and about 25 values with street text bled in (e.g. "JR BLVD, 9xxxx"). Current: 1,818 single digits, 354 six-digit values and 2 ZIP+4 without a dash. Staging keeps 5-digit ZIPs only (the street text never leaves raw).
- **`assigned_to` holds about 150 crew, yard and queue codes** (144 distinct in legacy, 152 in current). Nothing downstream of staging uses it: the brief rules out claims about crews.

## Timestamps
- **Both eras are local Pacific time.** Hour-of-day peaks fall at 09:00–15:00 in both (Profile §4). Floating timestamps have no time zone, so durations crossing a DST change can be off by an hour.
- **Precision changes over time.** Share of `createddate`s with :00 seconds (Profile §4):
  - 2015–2019: about 99–100% (minute precision).
  - 2020: 13.8% (the switch happened mid-year).
  - 2021 onward: about 1.6% (second precision).

  An instant-close threshold below a minute can't be compared with 2015–2019, which records whole minutes (none of its closes fall 1–59 s after creation; findings `e2_parameters.instant_close.legacy_timestamp_precision`). Phase 3 uses 1 minute.
- **Legacy streetlight closes in 2017–2021 are often date-only (midnight)** (Profile §4).
  - Share of closes at midnight: Single Streetlight Issue 77.9%, Multiple 50.3%.
  - Nearly all of the ~14K negative durations are streetlights, mostly 1–24 hours "before" creation.
  - Durations for those years are day-level.
- **Other legacy types and the current era have essentially no negative durations.**

## Locations
- **Some current-era coordinates are nowhere near LA.** 2,208 current rows fall outside latitude 33.6–34.4, as far as lat -43.5 and lon 176 (live aggregate). Every legacy coordinate lies inside the city's box. Staging nulls out-of-box points and flags them (`has_out_of_area_coordinates`), so they can't create false spatial matches.
- **Council district 0 and NC code 0 mean "none".**
  - CD 0: 3,338 current rows.
  - NC 0: 93,282 current rows, almost all without a name.
  - Legacy NC 0: 6,459 rows named "HISTORIC CULTURAL NORTH NC" or "NORTH WESTWOOD NC", NCs the current system codes as 128 and 127.
  - Staging sets 0 to null.
- **NC names vary by year and system** ("Sylmar" vs "SYLMAR NC"; three spellings for some codes), and NC boundaries changed when councils split. `dim_geography` uses each code's most common current-era name; cross-era NC comparisons are approximate.
- **Current-era geography gaps:** 215,936 cases have no CD, NC or coordinates; 61,813 have coordinates but no CD or NC; 25,965 have a CD and NC but no coordinates (live aggregate).
- **The busiest points are real places, not geocoder defaults.** The top service-request coordinates each carry only 1–5 distinct address strings (counted, never printed). One point has 11,711 current-era graffiti cases. Only 4 current points are shared by 50 or more different addresses (720 rows). Re-reports there reflect real recurrence.

## The legacy system's last year
- **Legacy requests still open at the cutover never close in the legacy data** (warehouse).
  - The share of legacy service requests that are still open rises from 0.55% (2022) to 2.2% (2023) and 4.6% (2024).
  - In the 12 months before the cutover, 31% of legacy streetlight requests are still Open (last update 2025-09-04) and 32% of legacy encampment requests are still Pending (last update 2026-06-10).
  - Whether they were carried into the new system isn't visible: new cases have new IDs.
  - Consequence: legacy closure measures near the cutover are cut short. `mart_cutover_periods` ends the legacy period 30 days before the cutover and compares "closed within N days".
- **Legacy closes kept arriving after the cutover** for some departments: the latest closes are Jul 2025 for graffiti, Aug 2025 for pickups and Sep 2025 for streetlights (warehouse, `max(updated_at)` per category).

## Statuses
- **Legacy:**
  - Closed: 99.9% have a closed date.
  - Cancelled and Referred Out: 100%.
  - Open, Pending and Forward: rarely (0–4% of rows). Those closed dates are on requests that are still open, so dbt defines time to close for terminal statuses only (`fct_service_requests`).
  - Official definition (column description): "Closed – The request has been completed."
- **Current statuses:** Closed, Reported, Cancelled and Closed Ext-Referred all have a closed date on 100% of rows. Workorder Created, New, In Progress, Potential Duplicate, Duplicate Confirm and Inspection Required (2 rows; not in the brief) have none (Profile §5).
- **"Reported" means the 311 record ends at intake.**
  - Four types are 100% "Reported" and about 99% closed within a minute, then handed to another department's system: Homeless Encampment (LSD), Report a Sidewalk Problem (DPW), Private Property Violation (LADBS), Report Water Wasting (LADWP).
  - 311 data can't say whether these were fixed (Profile §11b).
  - The legacy Homeless Encampment, by contrast, was closed by LASAN with ordinary statuses.
- **Reported cases carry intake codes, not outcomes** (warehouse): of 190,670 Reported service requests, 175,529 have "C-Report has been received", 13,007 "C-Closed" (all Private Property Violation), 1,905 "C-Report has been referred out." (Report Water Wasting), 113 "SR-Sidewalk Riding Incident Recorded" and 116 none. dbt lets the status decide their outcome (`handed_off`, decision 4).

## Channels and crew self-reports
- **"Driver Self Report" means crews logging work they already did** (column description: "by work crews for work done in field then entered into system").
  - That's 15.4% of all legacy rows, and 57.0% of legacy Graffiti Removal.
  - 79% of legacy crew self-reports close within 5 minutes (Profile §9, §12).
- **In the current system, crew self-reports ("Driver Self Reported") barely exist until March 2026.** They then climb to 48% of graffiti in August 2026 (Profile §10). Graffiti closure trends inside the current era will move because of how work is logged, not how it's done.
- **Fast closes are almost all crew self-reports or intake handoffs.** All other requests close within 5 minutes only 0.7% (legacy) and 1.2% (current) of the time (Profile §12).
- **The new system's near-zero spike isn't closes** (warehouse). 225,923 terminal service requests end within 10 seconds of filing, but they are intake handoffs (Reported), duplicates, information-only replies and cancellations. Requests actually marked Closed within a minute are rare (findings `e2_parameters.instant_close`).
- **Channel vocabulary changed.**
  - "Mobile App" is 25.8% of legacy rows and 0.1% of current rows; it was apparently folded into Self Service.
  - New current channels include "recycLA Service Provider", Chat and Social.
  - 61 current rows still use the legacy spelling "Driver Self Report".

## The Apr–Aug 2025 overlap
- **The overlap is a split by channel, not double-recording.**
  - After the cutover, legacy graffiti is crew self-reports; current graffiti is resident-reported (Self Service and Call).
  - Of 51,513 post-cutover legacy graffiti rows, 3,022 have a current graffiti case within 50 m on the same day (±1 day), against 2,708 in an equal-width placebo 7–8 days away. The excess is about 0.6% (Profile §10).
  - The dbt model reproduces this with exact hours instead of hour boundaries: 2,955 same-day matches against 2,700 placebo, about 0.5% excess (dbt `int_cutover_overlap`).

## Request types and the crosswalk
- **The bulky / illegal-dumping boundary moved at the cutover.**
  - Legacy bulky + metal + e-waste ran about 60–77K/month with illegal dumping about 9–12K/month.
  - Current Item Pickups and Illegal Dumping Item Pickup run about 37–45K/month *each*.
  - Combined volume is steady, so the two must be one crosswalk category (Profile §11c).
- **Streetlights:** current Streetlight Repair Services matches legacy Single + Multiple Streetlight Issue volume in the same months a year earlier. Streetlight ADA Repair Services and Non-Repair Services are small and current-era only.
- **Information-Only:** 877,137 rows in 2025–2026, all "Closed" with code "C-Closed", split between ITA and LASAN departments. In 2026, 85.9% of "C-Closed" rows are Information-Only, which confirms the brief (Profile §6).
- **Program Research** (LASAN customer care): almost all "1004-Closed", with about half closed within a minute.
- **"Other" (current):** mostly "GI-General Information" replies.
- **Service Not Complete:** LASAN rows have no reason codes. recycLA rows carry collection codes such as "0200-Blocked in By Vehicle/Object" and "0212-Not SNC - On Call Request". They're mostly resolved as completed or "RCAN-Cancelled by Contractor". These are missed-collection complaints, not a general "not fixed" signal (Profile §13).

## Re-reports
- **Places generate requests whatever happened to the last one.** At 50 m and 30 days, the share of closed requests followed by a same-category request is *lower* than the share preceded by one in the 30 days before filing, in every crosswalked category and both eras. It holds across radii of 25–100 m and windows of 7–60 days (findings `e2_parameters.rereport`).
- **Streetlights show the largest drop.** Before a request, other reports of the same outage are common; after a close they're rare.
- **Completed and item-not-out pickups are followed by new pickup requests about equally often** (findings `q3_bulky_items.new_pickup_request_within_30d`). At pickups, re-reports follow the building, not the outcome.

## Resolution codes
- **There are more codes than the brief estimated:** 149 distinct in 2025 Cases, 160 in 2026, 171 combined (the brief said about 120). Per-code stats are in `docs/profile/resolution_codes.csv`. Still 171 on 2026-10-28.
- **Five cases contradict themselves:** status Cancelled with code "WC-Work Completed" (Bus Stop Furniture; warehouse). They count as verified fixed but not closed, so the gap rate and the `closed_unverified` count differ by those five.
- **Reason codes are a fixed vocabulary** (130 values, at most 51 characters; warehouse), not free text, so they're safe to send to the labeling model as context.
- **Some high-volume codes weren't in the brief's examples**, e.g. "RC-Request Completed" (39,136 streetlight cases) and "VMRB-Vehicle moved for rebalancing" (16,921 scooter cases). Until they're labeled, those categories show near-zero fix rates (findings status `provisional`).
- **Prefix collisions include:**
  - C: C-Closed, C-Report has been received, C-Report has been referred out.
  - DUP, RC, CAN, COM, INC, IP, NAR, UA
  - NOV: NOV-Not Operator Vehicle vs NOV-Notice of Violation
  - Map on the full string (Profile §6).

## Null rates worth knowing (Profile §7)
- **Lat/lon:** missing for 18.8% (2016) and 19.3% (2017) of legacy rows, so re-report and geography work is weaker for those years. Current-era geography is 6–9% missing.
- **`service_date__c` is 98% null in the current era,** against about 5% for legacy `servicedate`, so it isn't comparable.
- **`date_service_was_rendered`** is populated for 1.8% of 2026 rows only. The brief said entirely null; it's close.
- **`assigned_to`** is about 35% null in the current era against 1–2% in legacy. `action_taken__c` is about 47–50% null.

## Catalog entries that aren't sources (see `sources.yml` → `ignored`)
- **`d7h2-83jy`, legacy streetlight view.**
  - It exposes `resolutioncode`, `reasoncode` and `dateservicerendered`, so the legacy system *did* record resolution codes even though the yearly views omit them.
  - 241,712 rows, 194,610 with a code (live aggregate; nothing pulled).
  - Its description says "This copy is private and for internal City use only", so it's excluded (decision 2026-10-23).
- **`iwu4-fgpx`:** a map built on that view.
- **`bpyg-ytsg`:** the pre-MyLA311 call-center archive.
- **`bihg-rw73`, `2fse-gjp4`:** community filters.
- **`tsrc-szkh`:** app download statistics.

## Socrata API notes
- **App token:** SODA 2.x worked without one at our volumes. Aggregates on the current datasets returned in about 1–2 s; bulk exports streamed at about 3–5 MB/s.
- **System fields** (`:id`, `:created_at`, `:updated_at`, `:version`) come with `$select=:*, *`.
  - `:id` order follows creation order, so it isn't random.
  - `:updated_at` is a UTC portal-ingest time.

# Data notes

Every quirk found in the MyLA311 open data, with where it came from.

- **Profile §n** = `docs/PROFILE.md`, computed from the full pulls of 2026-10-23 and regenerated with `make profile`.
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
- **The legacy datasets are still being touched.** `rowsUpdatedAt` is 2026-10-12, because the views share a parent table. Pulls are point-in-time with manifests.
- **The 2026 dataset is published in hourly batches.** Its latest `createddate` and `systemmodstamp` both sat exactly on the hour (16:00:00).

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

- **ID formats:** legacy `1-` plus 8–10 digits, with non-uniform trailing digits; current is 8 zero-padded digits, so keep it as text.
- **`locator_sr_council_district` holds the council member's name.** "neigborhood" is misspelled in two current field names.

## Timestamps
- **Both eras are local Pacific time.** Hour-of-day peaks fall at 09:00–15:00 in both (Profile §4). Floating timestamps have no time zone, so durations crossing a DST change can be off by an hour.
- **Precision changes over time.** Share of `createddate`s with :00 seconds (Profile §4):
  - 2015–2019: about 99–100% (minute precision).
  - 2020: 13.8% (the switch happened mid-year).
  - 2021 onward: about 1.6% (second precision).

  Any instant-close threshold must be at least a few minutes, or legacy years can't be compared.
- **Legacy streetlight closes in 2017–2021 are often date-only (midnight)** (Profile §4).
  - Share of closes at midnight: Single Streetlight Issue 77.9%, Multiple 50.3%.
  - Nearly all of the ~14K negative durations are streetlights, mostly 1–24 hours "before" creation.
  - Durations for those years are day-level.
- **Other legacy types and the current era have essentially no negative durations.**

## Statuses
- **Legacy:**
  - Closed: 99.9% have a closed date.
  - Cancelled and Referred Out: 100%.
  - Open, Pending and Forward: rarely (0–4% of rows).
  - Official definition (column description): "Closed – The request has been completed."
- **Current statuses:** Closed, Reported, Cancelled and Closed Ext-Referred all have a closed date on 100% of rows. Workorder Created, New, In Progress, Potential Duplicate, Duplicate Confirm and Inspection Required (2 rows; not in the brief) have none (Profile §5).
- **"Reported" means the 311 record ends at intake.**
  - Four types are 100% "Reported" and about 99% closed within a minute, then handed to another department's system: Homeless Encampment (LSD), Report a Sidewalk Problem (DPW), Private Property Violation (LADBS), Report Water Wasting (LADWP).
  - 311 data can't say whether these were fixed (Profile §11b).
  - The legacy Homeless Encampment, by contrast, was closed by LASAN with ordinary statuses.

## Channels and crew self-reports
- **"Driver Self Report" means crews logging work they already did** (column description: "by work crews for work done in field then entered into system").
  - That's 15.4% of all legacy rows, and 57.0% of legacy Graffiti Removal.
  - 79% of legacy crew self-reports close within 5 minutes (Profile §9, §12).
- **In the current system, crew self-reports ("Driver Self Reported") barely exist until March 2026.** They then climb to 48% of graffiti in August 2026 (Profile §10). Graffiti closure trends inside the current era will move because of how work is logged, not how it's done.
- **Fast closes are almost all crew self-reports or intake handoffs.** All other requests close within 5 minutes only 0.7% (legacy) and 1.2% (current) of the time (Profile §12).
- **Channel vocabulary changed.**
  - "Mobile App" is 25.8% of legacy rows and 0.1% of current rows; it was apparently folded into Self Service.
  - New current channels include "recycLA Service Provider", Chat and Social.
  - 61 current rows still use the legacy spelling "Driver Self Report".

## The Apr–Aug 2025 overlap
- **The overlap is a split by channel, not double-recording.**
  - After the cutover, legacy graffiti is crew self-reports; current graffiti is resident-reported (Self Service and Call).
  - Of 51,513 post-cutover legacy graffiti rows, 3,022 have a current graffiti case within 50 m on the same day (±1 day), against 2,708 in an equal-width placebo 7–8 days away. The excess is about 0.6% (Profile §10).

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

## Resolution codes
- **There are more codes than the brief estimated:** 149 distinct in 2025 Cases, 160 in 2026, 171 combined (the brief said about 120). Per-code stats are in `docs/profile/resolution_codes.csv`.
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

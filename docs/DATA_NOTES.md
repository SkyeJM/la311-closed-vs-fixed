# Data notes

Every quirk found in the MyLA311 open data, with where it came from. "Live query" means SoQL
against data.lacity.org on the date shown. "Sample" means the Phase 0 random-cluster samples
(10,000 rows per dataset; see `docs/DECISIONS.md`). Sample shares are rough estimates, not
findings.

## How the open data is built
- **All 13 datasets are saved filters** (`assetType: filter`) on two private parent tables.
  - Legacy parent: `69nn-wkid`. Current parent: `qdp3-rdjj`. Both return HTTP 403.
  - Each filter's exact SoQL (`queryString`) is pinned in `ingest/schemas/{id}.json`.
- **Legacy filters:**
  - 12 request types: Bulky Items, Dead Animal Removal, Electronic Waste, Feedback, Graffiti Removal, Homeless Encampment, Illegal Dumping Pickup, Metal/Household Appliances, Multiple Streetlight Issue, Other, Report Water Waste, Single Streetlight Issue.
  - A `createddate` window per year.
- **Current filters:** the same 63 types in both 2025 and 2026 (listed in the pins). The list includes Information-Only, Program Research, Feedback and Service Not Complete.
- **Field names point to Salesforce.** Current-era names (`casenumber`, `origin`, `systemmodstamp`, `*__c`, `*__s`) match Salesforce Case objects, so the new MyLA311 appears to run on Salesforce.
  - Hypothesis: resolution codes are per-department picklists, which would explain the inconsistent code vocabularies.
  - Legacy SR numbers (`1-` plus digits) look like Siebel row IDs.

## Coverage and row counts (live queries, 2026-10-23)
| Dataset | Rows | Created range |
|---|---|---|
| 2015 `ms7h-a45h` | 237,305 | 2015-08 to 2015-12 (MyLA311 launched Aug 2015; the filter starts 2015-08-01) |
| 2024 `b7dx-7gc3` | 1,442,347 | 2024 |
| 2025 legacy `h73f-gn57` | 423,053 | Jan 137,352 · Feb 115,026 · Mar 117,441 · Apr 14,288 · May 14,479 · Jun 12,609 · Jul 9,527 · Aug 2,278 · Sep 13 · Oct 39 · Nov 1 · Dec 0 |
| 2025 Cases `73a2-6ar5` | 1,740,673 | 2025-03-28 06:10:07 to 2025-12-31 12:59:54 |
| 2026 Cases `2cy6-i7zn` | 1,945,823 | 2026-01-01 00:00:31 to 2026-10-23 15:00:00 (refreshed through the day) |

- Other legacy years get counted in Phase 1.
- **Dataset-page counts are stale caches.** The metadata reports 1,467,201 non-null values for 2025 Cases and 70,976 for 2026. Always count rows yourself.
- **The legacy datasets are still being touched.** Their `rowsUpdatedAt` is 2026-10-12, because they share a parent table. Treat legacy pulls as point-in-time and record a manifest.

## Gaps and overlaps
- **Dec 31, 2025 afternoon is missing from both public datasets.**
  - The 2025 Cases filter ends at `2025-12-31T12:59:54`, i.e. `BETWEEN "2025-01-01T00:00:00" AND "2025-12-31T12:59:59"`. That's probably a typo for 23:59:59.
  - Hourly counts for Dec 31 stop after hour 12. The 2026 dataset starts at 2026-01-01.
  - The parent table is private, so these cases are unrecoverable from public data.
  - For scale: Dec 30, 2025 had 4,173 cases created between 13:00 and 23:59; Dec 31 had 3,361 cases through 12:59 (live hourly counts).
- **Legacy year windows overlap at exact midnights.** Several filters use an inclusive `BETWEEN` that ends at the next Jan 1 00:00:00, so a row created at exactly that instant matches two datasets.
  - Affected instants: 2016-01-01, 2017-01-01, 2019-01-01, 2020-01-01, 2021-01-01, 2022-01-01.
  - Dedupe on `srnumber` across datasets in staging.
- **The 2025 Cases metadata is wrong in two places.** The title says "March 2025 to December 2025" while the filter starts 2025-01-01; the description says "for 2020."

## Field names and types
- **The bulk export (`rows.csv`) differs from the row API in format, not values:**
  - Headers are display names.
  - Timestamps are `MM/DD/YYYY hh:mm:ss AM`, a 12-hour clock with no milliseconds.
  - Booleans are `true`/`false`. Case numbers keep their leading zeros.
  - Rows come in the saved filter's sort order.
  - The current era's `location` point is empty in the export (lat/lon are populated).
  - Checked on the 2015 and 2026 exports.
- **Bulk-export CSV headers are display names, and current datasets reuse legacy display names.**
  - Examples: "UpdatedDate" = `systemmodstamp`, "Owner" = `department_name__c`, "RequestType" = `type`, "RequestSource" = `origin`, "CDMember" = `locator_sr_council_district`.
  - Always map headers via the pinned `display` → `field` pairs. The SODA row API (`/resource/{id}.csv`) uses field names.
- **`createdbyuserorganization` is missing from the 2015–2018 and 2021 legacy views** (33 columns instead of 34).
- **Types differ across eras:**

  | Field | Legacy | Current |
  |---|---|---|
  | zip | text | number |
  | house number | number | text |
  | anonymous | "Y"/"N" text | boolean (`true`/`false`) |
  | police area | name (e.g. "77TH STREET") | number (e.g. 21) |

  `date_service_was_rendered` is text in the source.
- **ID formats:**
  - Legacy `1-` plus 8 digits (2015) or 10 digits (2024–25).
  - Current is 8 digits, zero-padded, so keep it as text.
  - Legacy ID trailing digits are **not** uniform, so they can't be used for hash-style sampling.
- **`locator_sr_council_district` holds the council member's name.** "neigborhood" is misspelled in two current field names.

## Timestamps
- **All timestamps are floating (no time zone), formatted `YYYY-MM-DDTHH:MM:SS.000`.** Milliseconds are always `.000` (sample).
- **Current-era times appear to be local Pacific time.**
  - A case created at "00:03" reached Socrata at 08:20Z, which is 00:20 PST.
  - Dec 30, 2025 hourly counts peak at 12:00 with 801 cases and drop to single digits overnight (live query).
  - Legacy time zone is still to be confirmed on full data in Phase 1.
- **2015 timestamps have minute precision**: 100% of sampled 2015 `createddate`s have seconds = 00, against about 1.6% (≈ 1/60) in other years. "Instant close" thresholds must allow for this.
- **No anomalies in the samples:**
  - No `closeddate` earlier than `createddate`, and no date-only (midnight) `closeddate`s, in any of the five samples.
  - The excluded streetlight view shows date-only closes (e.g. created 02:02, closed 00:00 the same day), so Phase 1 checks every year for both.

## Vocabularies (samples; counts are rows in the sample)
- **Legacy statuses:** Closed, Cancelled, Open, Pending, Referred Out, Forward. Official definition (column description): "Closed – The request has been completed."
- **Current statuses:** Closed, Reported, Cancelled, Workorder Created, In Progress, New, Closed Ext-Referred, Potential Duplicate. Duplicate Confirm wasn't in the samples.
- **In the current era, "Reported" behaves like a closed status.** In the 20,000-row current sample:
  - Every Closed (17,198), Reported (997), Cancelled (738) and Closed Ext-Referred (94) case has a `closeddate`. Nearly all have a resolution code (17,181, 997, 737 and 93).
  - Workorder Created, In Progress, New and Potential Duplicate cases have no `closeddate`.
  - This is the evidence for the Phase 1 "terminal status" proposal.
- **`actiontaken` (legacy) is "SR Created" in 29,986 of 30,000 sampled rows.**
- **Current `action_taken__c` is null in about 47% of sampled rows.** Its values are SR Created, Information Provided, Transferred, Status Provided and similar. It's a call action, not a resolution.
- **Channels changed between eras.**
  - Legacy channels in the sample (30,000 rows): Call 14,418, Mobile App 8,378, Self Service 3,281, Driver Self Report 2,575, Email 1,241, plus Council's Office, Voicemail and a few others.
  - Current channels in the sample (20,000 rows): Call 10,473, Self Service 9,014, recycLA Service Provider 217, Driver Self Reported 114, Mobile App 24, plus Email, Council's Office, Voicemail, Chat, Social and Letter.
  - "Mobile App" nearly disappears, apparently folded into Self Service. "Driver Self Report" became "Driver Self Reported."
  - The source docs say "Driver Self Report = by work crews for work done in field then entered into system", i.e. crews logging their own work. Those requests are closed almost by construction and must be split out of closure metrics.
- **Sparsity of current fields (sample):** `reason_code__c` 9.4% non-null, `date_service_was_rendered` 0.6% (not entirely null), `service_date__c` 1.9%, `assigned_to__c` 63%, lat/lon 93%.
- **Raw nulls:** empty fields from the SODA CSV come through as NULL, not '' (sample check).

## Specific types
- **Information-Only:** 5,051 of 20,000 sampled current rows. All are status Closed with code "C-Closed", and all closed within 60 seconds.
- **Service Not Complete** (sample):
  - LASAN rows mostly have no reason code.
  - recycLA rows carry trash-collection codes such as "0200-Blocked in By Vehicle/Object", "0240-SR-Scheduled", "0222-Ahead of Regular Service" and "0212-Not SNC - On Call Request".
  - This is consistent with missed-collection complaints. It isn't yet usable as a "not fixed" signal.
- **The legacy rows after the cutover are crew-logged graffiti.**
  - Of the sampled legacy-2025 rows from Apr–Aug 2025, 1,251 of 1,257 are Graffiti Removal via Driver Self Report. By month: Apr 334/338, May 340/342, Jun 298/298, Jul 225/225, Aug 54/54.
  - So the overlap looks like a split by channel (crews kept logging their own removals in the old system), not double-recording. Phase 1 checks whether the new system has crew-logged graffiti in those months.

## Instant closes in the samples (indicative only)
- Share of closed rows with `closeddate − createddate` between 0 and 60 seconds:

  | Sample | Share |
  |---|---|
  | 2015 | 0.0% (minute precision) |
  | 2024 | 1.3% |
  | 2025 legacy | 7.6% |
  | 2025 Cases | 34.4% |
  | 2026 Cases | 32.6% |

- The current-era shares include Information-Only contacts. Phase 1 recomputes on full data with service requests only.

## Catalog entries that aren't sources (see `sources.yml` → `ignored`)
- **`d7h2-83jy`, MyLA311 Streetlight Service Request Data.**
  - Built on the legacy parent and limited to the two legacy streetlight types.
  - It exposes three extra columns, `resolutioncode`, `reasoncode` and `dateservicerendered`, so the legacy system *did* record resolution codes even though the yearly views omit them.
  - 241,712 rows (2015-08-05 to 2025-07-04), 194,610 with a resolution code (live aggregate query; no rows pulled).
  - Its description says "This copy is private and for internal City use only", so it's excluded (decision 2026-10-23).
- **`iwu4-fgpx`:** a map built on the streetlight view.
- **`bpyg-ytsg`:** the pre-MyLA311 call-center archive (2013–2014).
- **`bihg-rw73`, `2fse-gjp4`:** community-made filters.
- **`tsrc-szkh`:** app download statistics.

## Socrata API notes
- SODA 2.x works without an app token at our volumes. Unauthenticated aggregate queries on the current datasets returned in about 1–2 s.
- System fields (`:id`, `:created_at`, `:updated_at`, `:version`) are available with `$select=:*, *`.
  - `:updated_at` is a Socrata-side row-change time in UTC, a candidate watermark for incremental refresh alongside `systemmodstamp` (Phase 1).
  - `:id` order follows creation order, so it isn't random.
- Response headers `X-SODA2-Fields`, `X-SODA2-Types` and `Last-Modified` describe the result, and `Last-Modified` is useful for refresh checks.

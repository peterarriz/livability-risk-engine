---
title: Livability Risk Engine — Data Ingest Reference
version: "2026-03-23"
scope: dataset-ids, portal-types, common-failures, agent-rules
maintainer: "@claude"
---

# Data Ingest Reference

Canonical reference for every ingest endpoint, dataset ID, portal type, known
failure mode, and agent rule in the LRE data pipeline.

---

## Crime Trend Datasets

### Socrata-Based

| City | Script | Domain | Dataset ID | Date Field | Group Field | Output |
|------|--------|--------|------------|------------|-------------|--------|
| Chicago | `chicago_crime_trends.py` | data.cityofchicago.org | `ijzp-q8t2` | `date` | `community_area` | `chicago_crime_trends.json` |
| Austin | `austin_crime_trends.py` | data.austintexas.gov | `fdj4-gpfu` | `occ_date` | `sector` | `austin_crime_trends.json` |
| Seattle | `seattle_crime_trends.py` | data.seattle.gov | `tazs-3rd5` | `offense_date` | `precinct` | `seattle_crime_trends.json` |
| NYC | `nyc_crime_trends.py` | data.cityofnewyork.us | `qgea-i56i` (historic) / `5uac-w243` (YTD) | `cmplnt_fr_dt` | `addr_pct_cd` | `nyc_crime_trends.json` |
| San Francisco | `sf_crime_trends.py` | data.sfgov.org | `wg3w-h783` | `incident_datetime` | `police_district` | `sf_crime_trends.json` |
| Oklahoma City | `oklahoma_city_crime_trends.py` | data.okc.gov | `f972-d93c` | `date_reported` | `beat` | `oklahoma_city_crime_trends.json` |

**Kansas City** uses per-year datasets on `data.kcmo.org`:

| Year | Dataset ID | Date Field |
|------|------------|------------|
| 2025 | `dmnp-9ajg` | `report_date` |
| 2024 | `isbe-v4d8` | `reported_date` |
| 2023 | `bfyq-5nh6` | `report_date` |

Group field: `area`. Output: `kansas_city_crime_trends.json`.

### ArcGIS-Based

| City | Script | Service URL | Date Field | Group Field | Output |
|------|--------|-------------|------------|-------------|--------|
| DC | `dc_crime_trends.py` | `maps2.dcgis.dc.gov/.../MPD/MapServer` | `REPORT_DAT` | `DISTRICT` | `dc_crime_trends.json` |
| Denver | `denver_crime_trends.py` | `services1.arcgis.com/zdB7qR0BtYrg0Xpl/.../ODC_CRIME_OFFENSES_P/FeatureServer/324` | `FIRST_OCCURRENCE_DATE` | `DISTRICT_ID` | `denver_crime_trends.json` |
| Baltimore | `baltimore_crime_trends.py` | `services1.arcgis.com/UWYHeuuJISiGmgXx/.../NIBRS_GroupA_Crime_Data/FeatureServer/0` | `CrimeDateTime` | `New_District` | `baltimore_crime_trends.json` |
| Nashville | `nashville_crime_trends.py` | `services2.arcgis.com/HdTo6HJqh92wn4D8/.../Metro_Nashville_Police_Department_Incidents_view/FeatureServer/0` | `Incident_Occurred` | `ZIP_Code` | `nashville_crime_trends.json` |
| Portland | `portland_crime_trends.py` | `portlandmaps.com/.../Public/Crime/MapServer` (layers 1, 40, 59) | `REPORTED_DATETIME` | `OffenseGroupDescription` | `portland_crime_trends.json` |
| Memphis | `memphis_crime_trends.py` | `services2.arcgis.com/saWmpKJIUAjyyNVc/.../MPD_Public_Safety_Incidents/FeatureServer/0` | `Offense_Datetime` | `Precinct` | `memphis_crime_trends.json` |
| Louisville | `louisville_crime_trends.py` | `services1.arcgis.com/79kfd2K6fskCAkyg/.../crime_data_{year}/FeatureServer/0` | `date_reported` | `lmpd_division` | `louisville_crime_trends.json` |
| Fresno | `fresno_crime_trends.py` | `services6.arcgis.com/Gs01XZPFhKUG8tKU/.../City_of_Fresno_Crime_Data_View/FeatureServer/0` | `OccurredOn` | `PD_District` | `fresno_crime_trends.json` |
| Sacramento | `sacramento_crime_trends.py` | `services5.arcgis.com/54falWtcpty3V47Z/.../Police_Crime_3Years/FeatureServer/0` | `Occurrence_Date_UTC` | `Police_District` | `sacramento_crime_trends.json` |
| Las Vegas | `las_vegas_crime_trends.py` | `services.arcgis.com/jjSk6t82vIntwDbs/.../LVMPD_Calls_For_Service_{year}/FeatureServer/0` | `IncidentDate` | `Classification` | `las_vegas_crime_trends.json` |
| El Paso | `el_paso_crime_trends.py` | `services.arcgis.com/YGBqHTHNMoJPJOav/.../EPPD_Crime_Data/FeatureServer/0` | `Date_Reported` | `Category` | `el_paso_crime_trends.json` |
| Tucson | `tucson_crime_trends.py` | `services3.arcgis.com/9coHY2fvuFjG9HQX/.../Tucson_Police_Reported_Crimes/FeatureServer/8` | `DateOccurred` | `Division` | `tucson_crime_trends.json` |
| San Antonio | `san_antonio_crime_trends.py` | `services.arcgis.com/g1fRTDLeMgspWrYp/.../CFS_SAPD_7Days/FeatureServer/0` | (none; 7-day rolling) | `PatrolDistrict` | `san_antonio_crime_trends.json` |
| Columbus | `columbus_crime_trends.py` | `services1.arcgis.com/9yy6msODkIBzkUXU/.../CPD_Offense_Data/FeatureServer/0` | `REPORT_DATE` | `ZONE` | `columbus_crime_trends.json` |
| Phoenix | `phoenix_crime_trends.py` | `services.arcgis.com/ubE5oANDhCRLGBDO/.../PhoenixPD_Crime_Statistics/FeatureServer/0` | `OCCURRED_ON` | `DISTRICT` | `phoenix_crime_trends.json` |
| San Jose | `san_jose_crime_trends.py` | `services.arcgis.com/p8Tul9YqBFRRdPqD/.../SJPD_Crime/FeatureServer/0` | `IncidentDate` | `District` | `san_jose_crime_trends.json` |
| Jacksonville | `jacksonville_crime_trends.py` | `services.arcgis.com/Dv0qhb5jJMSEEVJL/.../JSO_Crime_Incidents/FeatureServer/0` | `IncidentDate` | `Zone` | `jacksonville_crime_trends.json` |
| Fort Worth | `fort_worth_crime_trends.py` | `services.arcgis.com/AHCzmZstRKFEQEqv/.../FWPD_Crime/FeatureServer/0` | `FromDate` | `Division` | `fort_worth_crime_trends.json` |
| Indianapolis | `indianapolis_crime_trends.py` | `services.arcgis.com/ghDnFwW5bG9Ljzwi/.../IMPD_Crime_Statistics/FeatureServer/0` | `occurred_dt` | `district` | `indianapolis_crime_trends.json` |
| Albuquerque | `albuquerque_crime_trends.py` | `services.arcgis.com/3HnGBxB8VqLCXhUn/.../APD_Crime/FeatureServer/0` | `OCCURRED_DT` | `AREA_COMMAND` | `albuquerque_crime_trends.json` |

**DC yearly layer mapping:**

| Year | Layer ID |
|------|----------|
| 2024 | 6 |
| 2025 | 7 |
| 2026 | 41 |

### CKAN-Based

| City | Script | CKAN Domain | Resource ID | Date Field | Group Field | Output |
|------|--------|-------------|-------------|------------|-------------|--------|
| Boston | `boston_crime_trends.py` | data.boston.gov | `b973d8cb-eeb2-4e7e-99da-c92938efc9c0` | `OCCURRED_ON_DATE` | `DISTRICT` | `boston_crime_trends.json` |
| Milwaukee | `milwaukee_crime_trends.py` | data.milwaukee.gov | `87843297-a6fa-46d4-ba5d-cb342fb2d3bb` | `ReportedDateTime` | `POLICE` | `milwaukee_crime_trends.json` |
| Charlotte | `charlotte_crime_trends.py` | data.charlottenc.gov | `cdym-9n4y` (MUST VERIFY) | `date_reported` | `division` | `charlotte_crime_trends.json` |
| Minneapolis | `minneapolis_crime_trends.py` | data.minneapolismn.gov | `k65s-ce4x` (MUST VERIFY) | `reporteddate` | `precinct` | `minneapolis_crime_trends.json` |
| Raleigh | `raleigh_crime_trends.py` | data.raleighnc.gov | `d9dc-ixwq` (MUST VERIFY) | `reported_date` | `district` | `raleigh_crime_trends.json` |

### CSV-Based

| City | Script | URL Template | Date Field | Group Field | Output |
|------|--------|-------------|------------|-------------|--------|
| San Diego | `san_diego_crime_trends.py` | `seshat.datasd.org/police_calls_for_service/pd_calls_for_service_{year}_datasd.csv` | `DATE_TIME` | `BEAT` | `san_diego_crime_trends.json` |
| Houston | `houston_crime_trends.py` | `www.houstontx.gov/police/cs/xls/NIBRSPublicView{year}.csv` | `Occurrence Date` (MM/DD/YYYY) | `Beat` | `houston_crime_trends.json` |

---

## Permit Datasets

### Socrata Permits (`us_city_permits.py`)

| City | Source Key | Domain | Dataset ID | ID Field | Issue Date Field |
|------|-----------|--------|------------|----------|-----------------|
| New York City | `nyc` | data.cityofnewyork.us | `ipu4-2q9a` | `job__` | `dobrundate` |
| Los Angeles | `los_angeles` | data.lacity.org | `pi9x-tg5x` | `permit_nbr` | `issue_date` |
| Austin | `austin` | data.austintexas.gov | `3syk-w9eu` | `permit_number` | `issue_date` |
| NYC Street Closures | `nyc_street_closures` | data.cityofnewyork.us | `i6b5-j7bu` | `uniqueid` | `work_start_date` |
| Seattle | `seattle` | data.seattle.gov | `76t5-zqzr` | `permitnum` | `issueddate` |
| Kansas City | `kansas_city` | data.kcmo.org | `ntw8-aacc` | `permitnum` | `issueddate` |
| San Francisco | `san_francisco` | data.sfgov.org | `i98e-djp9` | `permit_number` | `issued_date` |
| Washington DC | `dc` | opendata.dc.gov | `awqx-tuwv` | `permit_number` | `issue_date` |
| Oklahoma City | `oklahoma_city` | data.okc.gov | `bsum-mkwp` | `permit_number` | `issue_date` |
| Louisville | `louisville` | data.louisvilleky.gov | `5mge-bwiz` | `permit_id` | `issued_date` |
| Fresno | `fresno` | data.fresno.gov | `sxvh-bkgt` | `permit_number` | `issue_date` |
| Sacramento | `sacramento` | data.cityofsacramento.org | `rent-6pka` | `permit_number` | `issued_date` |
| Raleigh | `raleigh` | data.raleighnc.gov | `k4n2-jcgh` (MUST VERIFY) | `permit_number` | `issued_date` |

### ArcGIS Permits (`us_city_permits_arcgis.py`)

| City | Source Key | Service URL (abbreviated) | ID Field | Issue Date Field |
|------|-----------|---------------------------|----------|-----------------|
| Phoenix | `phoenix` | maps.phoenix.gov/.../Planning_Permit/MapServer/1 | `PER_NUM` | `PER_ISSUE_DATE` |
| Columbus | `columbus` | services1.arcgis.com/.../Building_Permits/FeatureServer/0 | `B1_ALT_ID` | `ISSUED_DT` |
| Minneapolis | `minneapolis` | services.arcgis.com/.../CCS_Permits/FeatureServer/0 | `permitNumber` | `issueDate` |
| Charlotte | `charlotte` | meckgis.mecklenburgcountync.gov/.../BuildingPermits/FeatureServer/0 | `permitnum` | `issuedate` |
| Denver | `denver` | services1.arcgis.com/.../ODC_BUILDING_PERMITS_P/FeatureServer/0 | `PERMIT_NUM` | `ISSUED_DATE` |
| Portland | `portland` | services.arcgis.com/.../BDS_Permits/FeatureServer/0 | `PERMIT_NBR` | `ISSUED_DATE` |
| Baltimore | `baltimore` | egisdata.baltimorecity.gov/.../DHCD_Open_Baltimore_Datasets/FeatureServer/3 | `CaseNumber` | `IssuedDate` |
| Nashville | `nashville` | services2.arcgis.com/.../Building_Permits_Issued_2/FeatureServer/0 | `Permit__` | `Date_Issued` |
| Las Vegas | `las_vegas` | services.arcgis.com/VIkzGEMZbaSsMGLk/.../Building_Permits/FeatureServer/0 | `PERMIT_NUM` | `ISSUED_DATE` |
| El Paso | `el_paso` | services.arcgis.com/YGBqHTHNMoJPJOav/.../Building_Permits/FeatureServer/0 | `PERMIT_NUM` | `ISSUED_DATE` |
| Tucson | `tucson` | gisdata.tucsonaz.gov/.../Building_Permits/FeatureServer/0 | `PERMIT_NUM` | `ISSUED_DATE` |
| San Jose | `san_jose` | services.arcgis.com/p8Tul9YqBFRRdPqD/.../Building_Permits/FeatureServer/0 (MUST VERIFY) | `PERMIT_NUM` | `ISSUED_DATE` |
| Fort Worth | `fort_worth` | services.arcgis.com/AHCzmZstRKFEQEqv/.../Building_Permits/FeatureServer/0 (MUST VERIFY) | `PERMIT_NUM` | `ISSUED_DATE` |
| Albuquerque | `albuquerque` | services.arcgis.com/3HnGBxB8VqLCXhUn/.../Building_Permits/FeatureServer/0 (MUST VERIFY) | `PERMIT_NUM` | `ISSUED_DATE` |

### CKAN Permits (`us_city_permits_ckan.py`)

| City | Source Key | CKAN Domain | Resource ID | ID Field | Issue Date Field |
|------|-----------|-------------|-------------|----------|-----------------|
| Houston | `houston` | data.houstontx.gov | `a67a8bcd-d7a7-493b-98f6-a7dfbc6e84a5` | `permit_nbr` | `permit_issued` |
| Philadelphia | `philadelphia` | data.phila.gov | `2a8b059a-cf28-4fa1-a67e-c90c5c05fc8a` | `permitnumber` | `permitissuedate` |
| San Antonio | `san_antonio` | data.sanantonio.gov | `e7ac61e9-d8a1-4d48-a3a5-6c432a8fa5f3` | `permit_number` | `issue_date` |
| San Diego | `san_diego` | data.sandiego.gov | `7e82b527-5f2e-4e7c-a5c0-acbf59be0a74` | `apn` | `issue_date` |
| Boston | `boston` | data.boston.gov | `6ddcd912-32a0-43df-9908-63574f8c7e77` | `permitnumber` | `issued_date` |
| Milwaukee | `milwaukee` | data.milwaukee.gov | `828e9630-d7cb-42e4-960e-964eae916397` | `Record ID` | `Date Issued` |

---

## Common Failures

### Portal Migration (Socrata → ArcGIS Hub)

Many cities migrated open-data portals from Socrata to ArcGIS Hub between
2024–2026. The old Socrata domain still resolves but returns a 302 redirect
to `hub.arcgis.com/legacy`.

**Affected cities:** DC (`opendata.dc.gov`), Memphis (`data.memphistn.gov`),
Louisville (`data.louisvilleky.gov`), Fresno (`data.fresno.gov`),
Sacramento (`data.cityofsacramento.org`), Baltimore (`data.baltimorecity.gov`),
Nashville (`data.nashville.gov`).

**Symptom:** `json.JSONDecodeError: Expecting value: line 1 column 1 (char 0)`
— the response is an HTML redirect page, not JSON.

**Fix:** Find the ArcGIS FeatureServer/MapServer URL for the dataset and
rewrite the script to use ArcGIS REST queries.

### WAF / Bot Protection

Some portals block non-browser HTTP requests via Incapsula or Cloudflare WAF.

**Affected cities:** Oklahoma City (`data.okc.gov`).

**Symptom:** Response body is an HTML page with a `<script>` tag referencing
`_Incapsula_Resource`. The JSON parser raises `JSONDecodeError`.

**Fix:** No programmatic workaround without browser emulation. Leave as
non-fatal pipeline step.

### No Public Crime API

Some cities do not publish crime data via any public API.

**Affected cities:** El Paso (only boundary polygons on ArcGIS; no incident data).

**Symptom:** ArcGIS returns `{"error": {"code": 400, "message": "Invalid URL"}}`.

**Fix:** Monitor the city's open-data portal for future dataset publication.
Leave as non-fatal pipeline step.

### Stale / Frozen Datasets

Some ArcGIS datasets stop receiving updates but remain accessible.

**Affected cities:** Fresno (data ends July 2023 — `max(OccurredOn) = 1690329600000`).

**Symptom:** Script returns 0 records for current and prior 12-month windows.
No error is raised.

**Fix:** Monitor and replace with an updated dataset when available.

### ArcGIS Field Name Casing

ArcGIS MapServer uppercases `outStatisticFieldName` values. A query requesting
`crime_count` may receive `CRIME_COUNT` in the response.

**Affected cities:** DC MapServer.

**Symptom:** All counts are 0 despite districts being returned.

**Fix:** Check for both cases: `attrs.get("crime_count") or attrs.get("CRIME_COUNT")`.

### ArcGIS OBJECTID Missing on Tables

ArcGIS Table layers (no geometry) may use `ESRI_OID` instead of `OBJECTID`.

**Affected cities:** Tucson (`FeatureServer/8` is a Table).

**Symptom:** `{"error": {"code": 400, "message": "'Invalid field: OBJECTID'"}}`.

**Fix:** Use `ESRI_OID` as the `onStatisticField` for count aggregation.

### ArcGIS Date Formats

ArcGIS endpoints vary in accepted date SQL syntax:

| Format | Example | Used By |
|--------|---------|---------|
| `TIMESTAMP 'YYYY-MM-DD HH:MM:SS'` | `TIMESTAMP '2025-03-23 00:00:00'` | Most FeatureServer endpoints |
| `date 'YYYY-MM-DD'` | `date '2025-03-23'` | MapServer endpoints (DC, Portland) |
| Epoch milliseconds | `1711152000000` | Not directly supported in WHERE clauses on most servers |

### CSV Date Formats

| City | Format | Example |
|------|--------|---------|
| Houston | MM/DD/YYYY | `03/23/2025` |
| San Diego | YYYY-MM-DD HH:MM:SS | `2025-03-23 14:30:00` |

### San Antonio 7-Day Limitation

San Antonio only publishes a 7-day rolling window of Calls for Service.
No historical data is available for 12-month trend calculation. The script
produces a snapshot with `crime_prior_12mo: null` and `crime_trend: "STABLE"`.

### Louisville / Las Vegas Yearly Layers

Louisville and Las Vegas publish crime data in per-year FeatureServer layers.
The `crime_data_{year}` (Louisville) and `LVMPD_Calls_For_Service_{year}`
(Las Vegas) URL templates must be updated when a new year's layer is published.
If a year layer returns `Invalid URL`, the script logs a warning and continues
with available years.

---

## Agent Rules

### Lane Restriction

Only work on **data-lane** tasks: database, ingest pipelines, scoring engine,
API endpoints, data models, and connecting the data layer to the frontend
via the `/score` endpoint. Do NOT touch frontend components, UI, styling,
or layout.

### Task Naming

- Format: `[data-NNN] Short description`
- Sequence continues from the last completed task
- Each task gets a GitHub issue before execution
- Each task gets a TASKS.yaml entry with `notes_for_next_agent`

### Branch Convention

- One branch per task
- Branch naming follows: `claude/issue-{N}-{date}-{id}` or `data-{NNN}-{slug}`

### PR Convention

- Title format: `[data-NNN] description`
- Every change must reference a TASKS.yaml task ID

### Script Patterns

When adding a new crime trend script, follow the appropriate template:

1. **Socrata** — copy `seattle_crime_trends.py` as template. Key structure:
   `fetch_crime_counts_with_centroids()` → SoQL GROUP BY with `avg(latitude)`.

2. **ArcGIS FeatureServer** — copy `memphis_crime_trends.py` as template.
   Key structure: POST to `{url}/query` with `outStatistics` JSON.

3. **ArcGIS MapServer** — copy `portland_crime_trends.py` as template.
   MapServer may require `date '...'` instead of `TIMESTAMP '...'` and
   may uppercase output field names.

4. **ArcGIS yearly layers** — copy `louisville_crime_trends.py` as template.
   URL template with `{year}` placeholder; iterate over years in date range.

5. **CKAN** — copy `boston_crime_trends.py` as template. Key structure:
   try `datastore_search_sql` first, fall back to paginated `datastore_search`.
   Include `--discover` flag.

6. **CSV** — copy `houston_crime_trends.py` as template. Download full CSV,
   parse with `csv.DictReader`, filter by date client-side.

### Wiring Checklist

When adding a new city, update all three files:

1. **`run_pipeline.py`** — add a STEPS entry with `non_fatal: True` and a
   `skip_key`; add a matching `--skip-*` argparse argument.

2. **`load_neighborhood_quality.py`** — add a `STAGING_FILES` entry keyed
   as `crime_{city_slug}`; add the key to the `--source` choices list.

3. **`us_city_permits*.py`** — add a `CITY_CONFIGS` entry in the appropriate
   file (Socrata, ArcGIS, or CKAN) if the city has a permit dataset.

### Verification Commands

```bash
# Socrata — discover datasets
curl "https://{domain}/api/catalog/v1?q=crime&limit=5"

# Socrata — sample one record
curl "https://{domain}/resource/{dataset_id}.json?\$limit=1"

# ArcGIS — sample one record
curl "{service_url}/query?where=1%3D1&outFields=*&resultRecordCount=1&f=json"

# ArcGIS — check date range
curl "{service_url}/query" -d "where=1=1&outStatistics=[{\"statisticType\":\"max\",\"onStatisticField\":\"{date_field}\",\"outStatisticFieldName\":\"maxDate\"}]&f=json"

# CKAN — discover packages
curl "https://{domain}/api/3/action/package_search?q=crime&rows=5"

# CKAN — sample one record
curl "https://{domain}/api/3/action/datastore_search?resource_id={uuid}&limit=1"
```

### Dry-Run Policy

Every ingest script must support `--dry-run`. In dry-run mode:
- Fetch at least one page / one query to verify connectivity
- Print record counts and a sample record
- Do NOT write output files
- Exit 0 on success, exit 1 only on total fetch failure

### Non-Fatal Pipeline Steps

All crime trend and permit steps must be marked `"non_fatal": True` in
`run_pipeline.py`. A single city failure must not abort the entire pipeline.

### Dataset ID Rotation

Socrata dataset IDs and ArcGIS service URLs can change without notice.
When a script starts returning 0 records or HTTP 404:

1. Run the verification commands above to find the new ID
2. Update the constant in the script
3. Add a comment with the verification date
4. Re-run `--dry-run` to confirm

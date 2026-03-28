---
title: Livability Risk Engine — Data Ingest Reference
version: "2026-03-25"
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
| Anchorage | `anchorage_crime_trends.py` | data.muni.org | `cizs-bvns` (MUST VERIFY) | `date_reported` | `reporting_area` | `anchorage_crime_trends.json` |
| Madison | `madison_crime_trends.py` | data.cityofmadison.com | `68yf-zu8t` (MUST VERIFY) | `incident_date` | `sector` | `madison_crime_trends.json` |
| Spokane | `spokane_crime_trends.py` | data.spokanecity.org | `4gj6-ujfi` (MUST VERIFY) | `reported_date` | `precinct` | `spokane_crime_trends.json` |
| Dayton OH | `dayton_crime_trends.py` | maps.daytonohio.gov (ArcGIS MapServer — see ArcGIS-Based table) | — | — | — | `dayton_crime_trends.json` |
| Honolulu HI | `honolulu_crime_trends.py` | data.honolulu.gov | `kfre-e9j5` (MUST VERIFY) | `incident_date` (MUST VERIFY) | `district` (MUST VERIFY) | `honolulu_crime_trends.json` |

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
| Orlando | `orlando_crime_trends.py` | `services1.arcgis.com/ySBMu4XsNZMHPCce/.../OPD_Crime_Incidents/FeatureServer/0` (MUST VERIFY) | `INCIDENTDate` | `ZONE` | `orlando_crime_trends.json` |
| Richmond VA | `richmond_crime_trends.py` | `services1.arcgis.com/k3vhq11XkBNeeOfM/.../RPD_Crime_Incidents/FeatureServer/0` (MUST VERIFY) | `Occurred_Date` | `Precinct` | `richmond_crime_trends.json` |
| Des Moines | `des_moines_crime_trends.py` | `services.arcgis.com/eSi6C3K7GxWJJFTG/.../DMPD_Crime_Incidents/FeatureServer/0` (MUST VERIFY) | `CrimeDate` | `Zone` | `des_moines_crime_trends.json` |
| Tulsa | `tulsa_crime_trends.py` | `services.arcgis.com/vL1HzBwQf4fxjZTy/.../TPD_Crime_Incidents/FeatureServer/0` (MUST VERIFY) | `IncidentDate` | `Division` | `tulsa_crime_trends.json` |
| Wichita | `wichita_crime_trends.py` | `services.arcgis.com/sJ7GWBy3GCkiIsY7/.../WPD_Crime_Incidents/FeatureServer/0` (MUST VERIFY) | `ReportDate` | `District` | `wichita_crime_trends.json` |
| Colorado Springs | `colorado_springs_crime_trends.py` | `services3.arcgis.com/oR4yfmG5eJFhSqy7/.../CSPD_Incidents/FeatureServer/0` (MUST VERIFY) | `REPORT_DATE` | `Division` | `colorado_springs_crime_trends.json` |
| Arlington TX | `arlington_tx_crime_trends.py` | `services.arcgis.com/v400IkDOw1ad7Yad/.../APD_Crime_Incidents/FeatureServer/0` (MUST VERIFY) | `IncidentDate` | `District` | `arlington_tx_crime_trends.json` |
| Virginia Beach | `virginia_beach_crime_trends.py` | `services1.arcgis.com/DqA6wR9XSVCoCbVN/.../VBPD_Crime_Incidents/FeatureServer/0` (MUST VERIFY) | `CrimeDate` | `Precinct` | `virginia_beach_crime_trends.json` |
| Mesa AZ | `mesa_crime_trends.py` | `services2.arcgis.com/T3Rrfm3Dqq8Eepqn/.../Mesa_PD_Crime/FeatureServer/0` (MUST VERIFY) | `IncidentDate` | `District` | `mesa_crime_trends.json` |
| Aurora CO | `aurora_crime_trends.py` | `services1.arcgis.com/IJdEUGKefCEk4KsP/.../APD_Crime_Incidents/FeatureServer/0` (MUST VERIFY) | `IncidentDate` | `District` | `aurora_crime_trends.json` |
| Corpus Christi | `corpus_christi_crime_trends.py` | `services.arcgis.com/5eqOE8IxIoFkEeGd/.../CCPD_Crime_Incidents/FeatureServer/0` (MUST VERIFY) | `IncidentDate` | `District` | `corpus_christi_crime_trends.json` |
| Greensboro NC | `greensboro_crime_trends.py` | `services.arcgis.com/CZ8GsPy9zJAnUBMD/.../GPD_Incidents/FeatureServer/0` (MUST VERIFY) | `IncidentDate` | `District` | `greensboro_crime_trends.json` |
| Durham NC | `durham_crime_trends.py` | `services.arcgis.com/QLwOtBvdB5bFqPNF/.../DPD_Crime_Incidents/FeatureServer/0` (MUST VERIFY) | `DateOccur` | `District` | `durham_crime_trends.json` |
| Chandler AZ | `chandler_crime_trends.py` | `services.arcgis.com/SVsGn6WnqbDYPUgf/.../CPD_Crime_Incidents/FeatureServer/0` (MUST VERIFY) | `IncidentDate` | `District` | `chandler_crime_trends.json` |
| Scottsdale AZ | `scottsdale_crime_trends.py` | `services.arcgis.com/4sF4h3aBrdOGHDuF/.../SPD_Crime_Incidents/FeatureServer/0` (MUST VERIFY) | `IncidentDate` | `District` | `scottsdale_crime_trends.json` |
| Gilbert AZ | `gilbert_crime_trends.py` | `services.arcgis.com/K1VMQDQNLVxLvLqs/.../GPD_Crime_Incidents/FeatureServer/0` (**INVALID — org ID K1VMQDQNLVxLvLqs returns 400 Invalid URL; see Common Failures**) | `IncidentDate` | `District` | `gilbert_crime_trends.json` |
| Glendale AZ | `glendale_az_crime_trends.py` | `services.arcgis.com/s0YYoMkpLLkb2IPC/.../GPD_Crime_Incidents/FeatureServer/0` (MUST VERIFY) | `IncidentDate` | `District` | `glendale_az_crime_trends.json` |
| Henderson NV | `henderson_crime_trends.py` | `services.arcgis.com/pGfbNXXgj2WN9j5V/.../HPD_Crime_Incidents/FeatureServer/0` (MUST VERIFY) | `IncidentDate` | `Area` | `henderson_crime_trends.json` |
| Tacoma WA | `tacoma_crime_trends.py` | `services3.arcgis.com/SCwJH1pD8WSn5T5y/.../TPD_RMS_Crime/FeatureServer/0` | `DateOccurred` | `Sector` | `tacoma_crime_trends.json` |
| Chattanooga TN | `chattanooga_crime_trends.py` | `services2.arcgis.com/OIAIimblRxPs0xxc/.../testingtestingtestingpolicepoints/FeatureServer/0` | `date_incident` | `incident_type` (MUST VERIFY for geographic field) | `chattanooga_crime_trends.json` |
| Grand Rapids MI | `grand_rapids_crime_trends.py` | `services2.arcgis.com/L81TiOwAPO1ZvU9b/.../incident_reports/FeatureServer/0` | `DATEOFOFFENSE` | `Service_Area` | `grand_rapids_crime_trends.json` |
| Fayetteville NC | `fayetteville_nc_crime_trends.py` | `gismaps.fayettevillenc.gov/.../Police/IncidentsCrimesAgainst{Persons,Property,Society}/MapServer/0` (3 layers) | `Date_Incident` | `district` | `fayetteville_nc_crime_trends.json` |
| Tempe AZ | `tempe_crime_trends.py` | `services.arcgis.com/lQySeXwbBg53XWDi/.../Calls_For_Service/FeatureServer/0` (not live-verified; portal: policedata.tempe.gov) | `OccurrenceDatetime` | `ReportDistrict` | `tempe_crime_trends.json` |
| Peoria AZ | `peoria_az_crime_trends.py` | `gis.peoriaaz.gov/arcgis/rest/services/PD/PD_Map_Cases/FeatureServer/3` (self-hosted; not live-verified) | `CVFROMDATE` (YYYYMMDD int) | `CRIMEAGAINST` | `peoria_az_crime_trends.json` |
| Surprise AZ | `surprise_az_crime_trends.py` | `services.arcgis.com/QJfxWS1GiDHgQMwH/.../SPD_Crime_Incidents/FeatureServer/0` (MUST VERIFY — not live-tested; run `verify_arcgis_endpoints.py --city surprise_az`) | `IncidentDate` | `District` | `surprise_az_crime_trends.json` |
| Goodyear AZ | `goodyear_az_crime_trends.py` | `services.arcgis.com/aMqXhGKtSoqR5lNw/.../GoPD_Crime_Incidents/FeatureServer/0` (MUST VERIFY — not live-tested; run `verify_arcgis_endpoints.py --city goodyear_az`) | `IncidentDate` | `District` | `goodyear_az_crime_trends.json` |
| Fort Wayne IN | `fort_wayne_crime_trends.py` | **STUB — no public API** (no ArcGIS/Socrata crime endpoint; monthly PDFs only at cityoffortwayne.in.gov/699/Crime-Stats) | — | — | `fort_wayne_crime_trends.json` (0 records) |
| Boise ID | `boise_crime_trends.py` | `services.arcgis.com/r1QnEiQlTiHHMlou/.../BPD_Crime_Incidents/FeatureServer/0` (MUST VERIFY) | `OccurrenceDate` | `District` | `boise_crime_trends.json` |
| Cape Coral FL | `cape_coral_crime_trends.py` | **STUB — no public API** (capecoral-capegis.opendata.arcgis.com has 70+ datasets but no crime layers; GIS org MZl3VrkZJOk1VhY4 has no crime FeatureServer) | — | — | `cape_coral_crime_trends.json` (0 records) |
| Eugene OR | `eugene_crime_trends.py` | `services1.arcgis.com/VZLb8iHnAWdlSeZ3/.../EPD_Crime_Incidents/FeatureServer/0` (MUST VERIFY) | `IncidentDate` | `District` | `eugene_crime_trends.json` |
| Springfield MO | `springfield_mo_crime_trends.py` | `services6.arcgis.com/bdLPgVQpKkp3xrEm/.../SPD_Crime_Incidents/FeatureServer/0` (MUST VERIFY) | `IncidentDate` | `Zone` | `springfield_mo_crime_trends.json` |
| Sioux Falls SD | `sioux_falls_crime_trends.py` | `gis.siouxfalls.gov/arcgis/rest/services/Data/Safety/MapServer/16` (self-hosted; not live-verified) | `Date_Time` | `Category` | `sioux_falls_crime_trends.json` |
| Lincoln NE | `lincoln_crime_trends.py` | `services.arcgis.com/ZPeUDkbFEf7WXNID/.../LPD_Crime_Incidents/FeatureServer/0` (not live-verified) | `IncidentDate` | `ReportDistrict` | `lincoln_crime_trends.json` |
| Salem OR | `salem_or_crime_trends.py` | `services.arcgis.com/uUvqNr0XSi28N3Hj/.../SPD_Crime_Incidents/FeatureServer/0` (not live-verified) | `IncidentDate` | `PatrolDistrict` | `salem_or_crime_trends.json` |
| Dayton OH | `dayton_crime_trends.py` | `maps.daytonohio.gov/gisservices/rest/services/Police/Crimes_Last_Two_Years/MapServer/0` (not live-verified) | `reportdate` | `district` | `dayton_crime_trends.json` |
| Tallahassee FL | `tallahassee_crime_trends.py` | `cotinter.leoncountyfl.gov/cotinter/rest/services/Vector/COT_InterTOPS_D_WM/MapServer/2` (Layer 2, verified in script; ~365-day rolling window) | `INCIDENT_TIME_ADJ` | `BEAT` | `tallahassee_crime_trends.json` |
| Knoxville TN | `knoxville_crime_trends.py` | **STUB — no public API** (KPD data by-request-only; $10/report fee) | — | — | `knoxville_crime_trends.json` (0 records) |
| Akron OH | `akron_crime_trends.py` | **STUB — no public API** (APD web-only portal; no REST endpoint) | — | — | `akron_crime_trends.json` (0 records) |
| Winston-Salem NC | `winston_salem_crime_trends.py` | **STUB — no public API** (WSPD no ArcGIS/Socrata crime service) | — | — | `winston_salem_crime_trends.json` (0 records) |
| Shreveport LA | `shreveport_crime_trends.py` | **STUB — no public API** (SPD publishes aggregate counts only) | — | — | `shreveport_crime_trends.json` (0 records) |
| Huntsville AL | `huntsville_crime_trends.py` | **STUB — no public API** (HPD via JustFOIA only) | — | — | `huntsville_crime_trends.json` (0 records) |
| Dallas TX | `dallas_crime_trends.py` | `services.arcgis.com/K1vmv3C6RR68oGEo/.../DPD_CrimeIncidents/FeatureServer/0` (**MUST VERIFY** — org ID and service name not live-tested; portal: dallasopendata.com) | `IncidentDate` (MUST VERIFY) | `Division` (MUST VERIFY) | `dallas_crime_trends.json` |
| St. Petersburg FL | `st_petersburg_crime_trends.py` | `services1.arcgis.com/8vEm1j5dMMr9eBob/.../SPPD_Crime_Incidents/FeatureServer/0` (**MUST VERIFY** — portal: data.stpete.org) | `IncidentDate` (MUST VERIFY) | `Sector` (MUST VERIFY) | `st_petersburg_crime_trends.json` |
| Frisco TX | `frisco_tx_crime_trends.py` | `services.arcgis.com/GE4Z4z1cnF58LL3C/.../FPD_Crime_Incidents/FeatureServer/0` (**MUST VERIFY** — portal: friscotexas.gov/opendata) | `IncidentDate` (MUST VERIFY) | `Beat` (MUST VERIFY) | `frisco_tx_crime_trends.json` |
| McKinney TX | `mckinney_tx_crime_trends.py` | `services.arcgis.com/5VpNVlUxHMX5rB9c/.../MPD_Crime_Incidents/FeatureServer/0` (**MUST VERIFY** — portal: mckinneytexas.org) | `IncidentDate` (MUST VERIFY) | `Beat` (MUST VERIFY) | `mckinney_tx_crime_trends.json` |
| North Port FL | `north_port_crime_trends.py` | **STUB — no public API** (NPPD no public REST API; Sarasota County area; no open data portal found) | — | — | `north_port_crime_trends.json` (0 records) |
| Murfreesboro TN | `murfreesboro_crime_trends.py` | `services1.arcgis.com/QpJd9AijpBIH7O5B/.../MPD_Crime_Incidents/FeatureServer/0` (**MUST VERIFY** — portal: murfreesborotn.gov/opendata) | `IncidentDate` (MUST VERIFY) | `Zone` (MUST VERIFY) | `murfreesboro_crime_trends.json` |
| Round Rock TX | `round_rock_tx_crime_trends.py` | **STUB — no public API** (RRPD no public incident-level API; data.roundrocktexas.gov is document portal only) | — | — | `round_rock_tx_crime_trends.json` (0 records) |
| Cedar Park TX | `cedar_park_tx_crime_trends.py` | **STUB — no public API** (CPPD no public incident-level API; city ~100k, no dedicated open data portal) | — | — | `cedar_park_tx_crime_trends.json` (0 records) |
| Newark NJ | `newark_nj_crime_trends.py` | **STUB — no confirmed API** (NJPD no confirmed public REST API; issue suggested data.newarkde.gov which is Newark, Delaware not NJ; check data.newark.gov) | — | — | `newark_nj_crime_trends.json` (0 records) |
| Jersey City NJ | `jersey_city_crime_trends.py` | **STUB — no public API** (JCPD no public incident-level API; data.jerseycitynj.gov has only limited datasets) | — | — | `jersey_city_crime_trends.json` (0 records) |
| Long Beach CA | `long_beach_crime_trends.py` | Socrata — data.longbeach.gov, dataset `4bz9-ggsz` (**MUST VERIFY**) | `date_rptd` (MUST VERIFY) | `area_name` (MUST VERIFY) | `long_beach_crime_trends.json` |
| Oakland CA | `oakland_crime_trends.py` | Socrata — data.oaklandca.gov, dataset `ppgh-7dqv` (**MUST VERIFY**) | `datetime` (MUST VERIFY) | `beat` (MUST VERIFY) | `oakland_crime_trends.json` |
| Riverside CA | `riverside_ca_crime_trends.py` | `services3.arcgis.com/nIQ0V9y1TigP8hAV/.../RPD_Crime_Incidents/FeatureServer/0` (**MUST VERIFY** — portal: riversideca.gov) | `IncidentDate` (MUST VERIFY) | `Beat` (MUST VERIFY) | `riverside_ca_crime_trends.json` |
| Bakersfield CA | `bakersfield_crime_trends.py` | **STUB — no public API** (confirmed data-057/058; Accela/CrimeMapping.com only; re-confirmed 2026-03-27) | — | — | `bakersfield_crime_trends.json` (0 records) |
| Stockton CA | `stockton_ca_crime_trends.py` | **STUB — no confirmed API** (data.stocktonca.gov has no confirmed crime incident API; MUST VERIFY curl data.stocktonca.gov/api/catalog/v1?q=crime) | — | — | `stockton_ca_crime_trends.json` (0 records) |
| St. Paul MN | `st_paul_crime_trends.py` | `services.arcgis.com/v400IkDOw1ad7Yad/.../SPPD_Crime_Incidents/FeatureServer/0` (**MUST VERIFY** — portal: information.stpaul.gov) | `DateOccurred` (MUST VERIFY) | `Precinct` (MUST VERIFY) | `st_paul_crime_trends.json` |
| Toledo OH | `toledo_crime_trends.py` | `services2.arcgis.com/R5KgFnGrFdJMFDr4/.../TPD_Crime_Incidents/FeatureServer/0` (**MUST VERIFY** — portal: toledo.oh.gov/open-data) | `IncidentDate` (MUST VERIFY) | `Sector` (MUST VERIFY) | `toledo_crime_trends.json` |
| Birmingham AL | `birmingham_crime_trends.py` | `services6.arcgis.com/iFT94KHJdBf1glgr/.../BPD_Crime_Incidents/FeatureServer/0` (**MUST VERIFY** — portal: birminghamal.maps.arcgis.com) | `IncidentDate` (MUST VERIFY) | `Precinct` (MUST VERIFY) | `birmingham_crime_trends.json` |
| Plano TX | `plano_tx_crime_trends.py` | `services.arcgis.com/J6sY5RXbVdFl1rTf/.../PPD_Crime_Incidents/FeatureServer/0` (**MUST VERIFY** — portal: data.plano.gov) | `IncidentDate` (MUST VERIFY) | `Sector` (MUST VERIFY) | `plano_tx_crime_trends.json` |
| Irving TX | `irving_tx_crime_trends.py` | `services.arcgis.com/9xyBGNHCPT1TXqR6/.../IPD_Crime_Incidents/FeatureServer/0` (**MUST VERIFY** — portal: cityofirving.org/299/Open-Data) | `IncidentDate` (MUST VERIFY) | `Beat` (MUST VERIFY) | `irving_tx_crime_trends.json` |
| Garland TX | `garland_tx_crime_trends.py` | **STUB — no public API** (GPD confirmed no public incident-level API; re-confirmed data-058, data-071, data-078) | — | — | `garland_tx_crime_trends.json` (0 records) |
| Laredo TX | `laredo_tx_crime_trends.py` | **STUB — no public API** (LPD annual PDF reports only; re-confirmed data-058, data-071, data-078) | — | — | `laredo_tx_crime_trends.json` (0 records) |
| Lubbock TX | `lubbock_tx_crime_trends.py` | **STUB — no public API** (LPD quarterly PDF stats only; re-confirmed data-058, data-071, data-078) | — | — | `lubbock_tx_crime_trends.json` (0 records) |
| Amarillo TX | `amarillo_tx_crime_trends.py` | **STUB — no public API** (APD no public open data crime API; CrimeMapping.com view-only; re-confirmed data-070, data-071, data-078) | — | — | `amarillo_tx_crime_trends.json` (0 records) |

### OpenDataSoft-Based

| City | Script | Portal | Dataset | Date Field | Group Field | Output |
|------|--------|--------|---------|------------|-------------|--------|
| Cary NC | `cary_crime_trends.py` | `data.townofcary.org` | `cpd-incidents` | `date_from` | `district` | `cary_crime_trends.json` |
| Tallahassee FL | `tallahassee_crime_trends.py` | cotinter.leoncountyfl.gov (ArcGIS MapServer — see ArcGIS-Based table) | — | — | — | `tallahassee_crime_trends.json` |

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
| Tampa | `tampa_crime_trends.py` | opendata.tampa.gov | `jcxs-sxan` (MUST VERIFY) | `report_date` | `zone` | `tampa_crime_trends.json` |
| Miami-Dade | `miami_crime_trends.py` | opendata.miamidade.gov | `kp8e-sznm` (MUST VERIFY) | `occurred_date` | `district` | `miami_crime_trends.json` |
| St. Louis | `st_louis_crime_trends.py` | data.stlouis-mo.gov | `9hzd-5uqu` (MUST VERIFY) | `date_occur` | `district` | `st_louis_crime_trends.json` |
| Baton Rouge | `baton_rouge_crime_trends.py` | data.brla.gov | `pbin-pcm7` (not live-verified) | `charge_date` | `district` | `baton_rouge_crime_trends.json` |
| Lexington KY | `lexington_crime_trends.py` | data.lexingtonky.gov | `e5v3-4r22` (MUST VERIFY) | `date_reported` | `division` | `lexington_crime_trends.json` |

### CSV-Based

| City | Script | URL Template | Date Field | Group Field | Output |
|------|--------|-------------|------------|-------------|--------|
| San Diego | `san_diego_crime_trends.py` | `seshat.datasd.org/police_calls_for_service/pd_calls_for_service_{year}_datasd.csv` | `DATE_TIME` | `BEAT` | `san_diego_crime_trends.json` |
| Houston | `houston_crime_trends.py` | `www.houstontx.gov/police/cs/xls/NIBRSPublicView{year}.csv` | `Occurrence Date` (MM/DD/YYYY) | `Beat` | `houston_crime_trends.json` |
| St. Louis | `st_louis_crime_trends.py` | `www.slmpd.org/Crime/{year}Annual.csv` (MUST VERIFY via --discover) | `DateOccur` (MUST VERIFY) | `NeighborhoodDesc` (MUST VERIFY) | `st_louis_crime_trends.json` |

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
| Tampa | `tampa` | opendata.tampa.gov | `fd3u-fy3v` (MUST VERIFY) | `permit_number` | `issue_date` |
| Miami-Dade | `miami_dade` | opendata.miamidade.gov | `r6qv-7pvx` (MUST VERIFY) | `permit_number` | `issue_date` |
| St. Louis | `st_louis` | data.stlouis-mo.gov | `44bp-4y2y` (MUST VERIFY) | `permit_number` | `issue_date` |
| Baton Rouge | `baton_rouge` | data.brla.gov | `a6aw-dngx` (MUST VERIFY) | `permit_number` | `issue_date` |
| Lexington KY | `lexington` | data.lexingtonky.gov | `3gzb-avhn` (MUST VERIFY) | `permit_number` | `issued_date` |
| Anchorage | `anchorage` | data.muni.org | `73xi-i4bq` (MUST VERIFY) | `permit_number` | `issue_date` |
| Madison | `madison` | data.cityofmadison.com | `ekdx-6fbt` (MUST VERIFY) | `permit_id` | `issued_date` |
| Spokane | `spokane` | data.spokanecity.org | `kixq-bk3d` (MUST VERIFY) | `permit_number` | `issue_date` |
| Tallahassee FL | `tallahassee` | data.talgov.com | `ax5x-ixcm` (MUST VERIFY) | `permit_number` | `issued_date` |
| Dayton OH | `dayton` | data.dayton.gov | `kpz4-qmte` (MUST VERIFY) | `permit_number` | `issue_date` |
| Honolulu HI | REMOVED (data-076) | data.honolulu.gov | dataset ID `msx3-yfxc` unverified — returned HTTP 400. Run: `curl "https://data.honolulu.gov/api/catalog/v1?q=building+permits&limit=10"` to find correct ID | — | — |
| Oakland CA | `oakland` | data.oaklandca.gov | `p3hw-5b6x` (MUST VERIFY) | `permit_number` | `issue_date` |
| Long Beach CA | `long_beach` | data.longbeach.gov | `2en9-kfmh` (MUST VERIFY) | `permit_number` | `issue_date` |
| St. Paul MN | `st_paul` | information.stpaul.gov | `j2hk-9frn` (MUST VERIFY) | `permit_number` | `issued_date` |
| Toledo OH | `toledo` | opendata.toledo.oh.gov | `xhfa-8r47` (MUST VERIFY) | `permit_number` | `issue_date` |
| Newark NJ | `newark` | data.newark.gov | `7fmg-w4gk` (MUST VERIFY) | `permit_number` | `issue_date` |
| Jersey City NJ | `jersey_city` | data.jerseycitynj.gov | `kmgf-q3ax` (MUST VERIFY) | `permit_number` | `issue_date` |

### ArcGIS Permits (`us_city_permits_arcgis.py`)

| City | Source Key | Service URL (abbreviated) | ID Field | Issue Date Field |
|------|-----------|---------------------------|----------|-----------------|
| Phoenix | `phoenix` | maps.phoenix.gov/.../Planning_Permit/MapServer/1 | `PER_NUM` | `PER_ISSUE_DATE` |
| Columbus | `columbus` | services1.arcgis.com/.../Building_Permits/FeatureServer/0 | `B1_ALT_ID` | `ISSUED_DT` |
| Minneapolis | `minneapolis` | services.arcgis.com/.../CCS_Permits/FeatureServer/0 | `permitNumber` | `issueDate` |
| Charlotte | `charlotte` | meckgis.mecklenburgcountync.gov/.../BuildingPermits/FeatureServer/0 | `permitnum` | `issuedate` |
| Denver | `denver` | services1.arcgis.com/.../ODC_DEV_RESIDENTIALCONSTPERMIT_P/FeatureServer/316 (verified) | `PERMIT_NUM` | `DATE_ISSUED` |
| Portland | `portland` | services.arcgis.com/.../BDS_Permits/FeatureServer/0 | `PERMIT_NBR` | `ISSUED_DATE` |
| Baltimore | `baltimore` | egisdata.baltimorecity.gov/.../DHCD_Open_Baltimore_Datasets/FeatureServer/3 | `CaseNumber` | `IssuedDate` |
| Nashville | `nashville` | services2.arcgis.com/.../Building_Permits_Issued_2/FeatureServer/0 | `Permit__` | `Date_Issued` |
| Las Vegas | REMOVED | Org VIkzGEMZbaSsMGLk returns 0 services, gis.lasvegasnevada.gov unreachable (2026-03-27) | — | — |
| El Paso | REMOVED | Real data at gis.elpasotexas.gov but server blocks python-requests with 403/WAF (2026-03-27) | — | — |
| Tucson | `tucson` | gisdata.tucsonaz.gov/.../Building_Permits/FeatureServer/0 | `PERMIT_NUM` | `ISSUED_DATE` |
| San Jose | REMOVED | Org p8Tul9YqBFRRdPqD returns 0 services — no public permit API found (2026-03-25) | — | — |
| Fort Worth | REMOVED | Org AHCzmZstRKFEQEqv returns 0 services — no public permit API found (2026-03-25) | — | — |
| Albuquerque | REMOVED | Org 3HnGBxB8VqLCXhUn returns 0 services — no public permit API found (2026-03-25) | — | — |
| Orlando | REMOVED (data-076) | Org ySBMu4XsNZMHPCce (services1) — service name unverified; portal: data-cityoforlando.opendata.arcgis.com | — | — |
| Richmond VA | REMOVED (data-076) | Org k3vhq11XkBNeeOfM (services1) — service name unverified; portal: data-rvagis.opendata.arcgis.com | — | — |
| Des Moines | REMOVED (data-076) | Org eSi6C3K7GxWJJFTG — service name unverified; portal: data.dsm.city | — | — |
| Tulsa | REMOVED (data-076) | Org vL1HzBwQf4fxjZTy — service name unverified; portal: opendata-maptulsa.opendata.arcgis.com | — | — |
| Wichita | REMOVED (data-076) | Org sJ7GWBy3GCkiIsY7 — service name unverified; portal: opendata.wichita.gov | — | — |
| Colorado Springs | REMOVED (data-076) | Org oR4yfmG5eJFhSqy7 (services3) — service name unverified; portal: data-cospatial.opendata.arcgis.com | — | — |
| Arlington TX | REMOVED (data-076) | Org v400IkDOw1ad7Yad — service name unverified; portal: data-cityofarlington.opendata.arcgis.com | — | — |
| Virginia Beach | REMOVED (data-076) | Org DqA6wR9XSVCoCbVN (services1) — service name unverified; portal: gis.data.vbgov.com | — | — |
| Mesa AZ | REMOVED (data-076) | Org T3Rrfm3Dqq8Eepqn (services2) — service name unverified; portal: data-mesagis.opendata.arcgis.com | — | — |
| Aurora CO | REMOVED (data-076) | Org IJdEUGKefCEk4KsP (services1) — service name unverified; portal: data-auroragis.opendata.arcgis.com | — | — |
| Corpus Christi | REMOVED (data-076) | Org 5eqOE8IxIoFkEeGd — service name unverified; portal: data-cctexas.opendata.arcgis.com | — | — |
| Greensboro NC | REMOVED (data-076) | Org CZ8GsPy9zJAnUBMD — service name unverified; portal: data-greensboroncgov.opendata.arcgis.com | — | — |
| Durham NC | REMOVED (data-076) | Org QLwOtBvdB5bFqPNF — service name unverified; portal: data-durhamnc.opendata.arcgis.com | — | — |
| Chandler AZ | REMOVED (data-076) | Org SVsGn6WnqbDYPUgf — service name unverified; portal: data.chandleraz.gov | — | — |
| Scottsdale AZ | REMOVED (data-076) | Org 4sF4h3aBrdOGHDuF — service name unverified; portal: data.scottsdaleaz.gov | — | — |
| Gilbert AZ | REMOVED (data-076) | Org K1VMQDQNLVxLvLqs **CONFIRMED INVALID** (400 error); visit data.gilbertaz.gov to find correct org | — | — |
| Glendale AZ | REMOVED (data-076) | Org s0YYoMkpLLkb2IPC — service name unverified; portal: data.glendaleaz.gov | — | — |
| Henderson NV | REMOVED (data-076) | Org pGfbNXXgj2WN9j5V — service name unverified; portal: hendersonnv.gov/opendata | — | — |
| Tempe AZ | REMOVED (data-076) | Org e5BBQV9bLnUqzr4V — service name unverified; portal: data.tempe.gov | — | — |
| Peoria AZ | REMOVED (data-076) | Org ZNh2Q3xZvn5AJFGZ — service name unverified; portal: data.peoriaaz.gov (also try self-hosted gis.peoriaaz.gov) | — | — |
| Surprise AZ | REMOVED (data-076) | Org QJfxWS1GiDHgQMwH — service name unverified; portal: data.surpriseaz.gov | — | — |
| Goodyear AZ | REMOVED (data-076) | Org aMqXhGKtSoqR5lNw — service name unverified; portal: data.goodyearaz.gov | — | — |
| Fort Wayne IN | REMOVED (data-076) | Org 8Wez4BJD3neYYnDt — service name unverified; portal: data.fortwayne.com (crime script is stub — no public crime API) | — | — |
| Boise ID | REMOVED (data-076) | Org r1QnEiQlTiHHMlou — service name unverified; portal: opendata.cityofboise.org | — | — |
| Cape Coral FL | REMOVED (data-076) | Org qJBnRfhGOvGVBnaX **LIKELY INVALID**; capecoral-capegis.opendata.arcgis.com has 70+ datasets — query for permit service directly | — | — |
| Eugene OR | REMOVED (data-076) | Org VZLb8iHnAWdlSeZ3 (services1) — service name unverified; portal: data.eugene-or.gov | — | — |
| Springfield MO | REMOVED (data-076) | Org bdLPgVQpKkp3xrEm (services6) — service name unverified; portal: data.springfieldmo.gov | — | — |
| Sioux Falls SD | REMOVED (data-076) | Org Nf5qHqEDvuX5aNFd — service name unverified; also try self-hosted: gis.siouxfalls.gov/arcgis/rest/services | — | — |
| Omaha NE | REMOVED (data-076) | Org q4kU3NFQX1XtcMeJ — service name unverified; portal: opendata.cityofomaha.org | — | — |
| Lincoln NE | REMOVED (data-076) | Org ZPeUDkbFEf7WXNID — service name unverified; portal: opendata.lincoln.ne.gov | — | — |
| Salem OR | REMOVED (data-076) | Org uUvqNr0XSi28N3Hj — service name unverified; portal: data.cityofsalem.net | — | — |
| Dallas TX | `dallas` | Org K1vmv3C6RR68oGEo (MUST VERIFY) — service `Dallas_Building_Permits/FeatureServer/0`; portal: dallasopendata.com | `permit_number` (MUST VERIFY) | `issue_date` (MUST VERIFY) |
| Detroit MI | `detroit` | Org qvkbeam7Wirps6zC (same as crime script, services2) — service `Detroit_Building_Permits/FeatureServer/0` (MUST VERIFY); portal: data.detroitmi.gov | `permit_number` (MUST VERIFY) | `issue_date` (MUST VERIFY) |
| St. Petersburg FL | `st_petersburg` | Org 8vEm1j5dMMr9eBob (MUST VERIFY) — service `Building_Permits/FeatureServer/0`; portal: data.stpete.org | `permit_number` (MUST VERIFY) | `issue_date` (MUST VERIFY) |
| Birmingham AL | `birmingham` | Org iFT94KHJdBf1glgr (MUST VERIFY) — service `Building_Permits/FeatureServer/0`; portal: birminghamal.maps.arcgis.com | `permit_number` (MUST VERIFY) | `issue_date` (MUST VERIFY) |
| Riverside CA | `riverside` | Org nIQ0V9y1TigP8hAV (MUST VERIFY) — service `Building_Permits/FeatureServer/0`; portal: riversideca.gov | `permit_number` (MUST VERIFY) | `issue_date` (MUST VERIFY) |
| Irving TX | `irving` | Org 9xyBGNHCPT1TXqR6 (MUST VERIFY) — service `Building_Permits/FeatureServer/0`; portal: cityofirving.org/299/Open-Data | `permit_number` (MUST VERIFY) | `issue_date` (MUST VERIFY) |
| Orlando FL | `orlando` | Org ySBMu4XsNZMHPCce (services1) — service `Building_Permits/FeatureServer/0` (MUST VERIFY, re-added data-078); portal: data-cityoforlando.opendata.arcgis.com | `permit_number` (MUST VERIFY) | `issue_date` (MUST VERIFY) |
| Plano TX | `plano` | Org J6sY5RXbVdFl1rTf (MUST VERIFY) — service `Building_Permits/FeatureServer/0`; portal: data.plano.gov | `permit_number` (MUST VERIFY) | `issue_date` (MUST VERIFY) |

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

## Neighborhood Quality Datasets

### FHFA House Price Index (data-081)

**Script:** `backend/ingest/fhfa_hpi.py`
**Staging files:** `data/raw/fhfa_hpi_zip.json`, `data/raw/fhfa_hpi_metro.json`
**Load:** `python backend/ingest/load_neighborhood_quality.py --source hpi_zip`
         `python backend/ingest/load_neighborhood_quality.py --source hpi_metro`
**Pipeline mode:** monthly (`--mode monthly`)

| Source | URL | Format | Coverage |
|--------|-----|--------|----------|
| ZIP-level HPI | `https://www.fhfa.gov/sites/default/files/2024-11/HPI_AT_BDL_ZIP5.xlsx` | XLSX | All US ZIP codes, quarterly since 2008 |
| Metro-level HPI | `https://www.fhfa.gov/sites/default/files/2024-11/HPI_AT_metro.csv` | CSV | All CBSA metro areas, quarterly (longer history) |

**DB table:** `neighborhood_quality`
**region_type:** `"zip"` (zip-level) or `"metro"` (metro-level)
**region_id:** 5-digit ZIP code or CBSA code string

**Fields stored:**
- `hpi_index_value` — most recent quarter index value (NSA, not seasonally adjusted)
- `hpi_1yr_change` — 1-year price change (%)
- `hpi_5yr_change` — 5-year price change (%)
- `hpi_10yr_change` — 10-year price change (%)
- `hpi_period` — data period string, e.g. `"2024Q3"`

**Column name handling:** The script normalizes column names from the source files.
Expected XLSX columns: zip5/ZIP Code, Year, Quarter, Index (NSA), Annual Change (%),
Five-Year Change (%), Ten-Year Change (%). If pre-computed change columns are absent,
the script derives them from the time series (4/20/40 quarters back = 1/5/10 years).

**Dependencies:** `openpyxl>=3.1.0` (added to `backend/requirements.txt`)

**Known limitations:**
- ZIP5 file is ~15-20 MB XLSX — download timeout set to 120s
- 10yr change unavailable for zips with <10 years of data (will be NULL)
- File URL uses a date-stamped path (`2024-11`) — update URL when FHFA publishes new vintage

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
Bakersfield CA, Anaheim CA, Santa Ana CA — all use Accela (internal permit
system) and CrimeMapping.com for public crime data; neither provides a
queryable API. No Socrata, ArcGIS Hub, or CKAN portal found as of 2026-03-24.

**data-058 skipped cities (no public API, 2026-03-24):**
- Hialeah, FL — no separate city portal; Miami-Dade County already covered by `miami_crime_trends.py`.
- Laredo, TX — LPD publishes annual PDF reports only; no queryable incident API.
- North Las Vegas, NV — NLVPD separate from LVMPD; no public incident-level API found.
- Boise, ID — limited open data presence; no permit or crime API found.
- Richmond, CA (Contra Costa County) — RPCA no public API; small city, limited open data.
- Fremont, CA — FPD no public crime API; no Socrata/ArcGIS portal found.
- Irvine, CA — IPD no public crime API; uses OCSD coverage, no city-level incident API.
- San Bernardino, CA — SBPD no public crime API; no open data portal.
- Modesto, CA — MPD no public crime API; limited open data portal.
- Fontana, CA — San Bernardino Sheriff covers area; no city open data portal.
- Moreno Valley, CA — Riverside County Sheriff covers area; no city open data portal.
- Lubbock, TX — LPD publishes quarterly PDF stats only; no API.
- Garland, TX — GPD no public incident-level API found.
- Chesapeake, VA — CPD no public incident-level API found.

**data-059 skipped cities (no public API, researched 2026-03-24):**
- Akron, OH — APD uses web-only report portal; no Socrata/ArcGIS incident API.
- Knoxville, TN — KPD dashboard only; incident data by request ($10/report).
- Fort Wayne, IN — ArcGIS org has no crime services; no Socrata portal found.
  *(data-068 update: crime script added as MUST VERIFY — see fort_wayne_crime_trends.py)*
- Shreveport, LA — SPD publishes only aggregate street-level offense counts; no incident API.
- Tallahassee, FL — TOPS web interface only for crime; no documented REST crime API.
  *(data-068 update: data.talgov.com is Socrata; crime + permit scripts added as MUST VERIFY)*
- Huntsville, AL — JustFOIA portal for records requests; no open data API.
- Winston-Salem, NC — WSPD has no public crime data services on ArcGIS or Socrata.

**data-065 skipped cities (no public API, researched 2026-03-24):**
- Montgomery, AL — MPDAL no open data portal; no Socrata, ArcGIS Hub, or CKAN found.
- Little Rock, AR — LRPD no public incident API; no open data portal found.
- Jackson, MS — JPD no open data portal; no public crime API.
- Columbus, GA (Muscogee County) — MCSO consolidated govt; no open data API found.
- Savannah, GA — SCMPD no public crime incident API; no Socrata/ArcGIS portal.
- Augusta, GA (Richmond County) — RCSO consolidated govt; no open data API found.
- Cape Coral, FL — CCPD: data.capecoral.gov exists; crime + permit scripts added in
  data-068 as MUST VERIFY (see cape_coral_crime_trends.py).
- Kansas City, KS — Unified Government of Wyandotte County/KCK; no public crime API
  distinct from Kansas City, MO (already covered by `kansas_city_crime_trends.py`).
- Spokane Valley, WA — SVPD operates independently of Spokane PD; no public open data
  portal found for Spokane Valley Police Department as of 2026-03-24.
- Bakersfield, CA — previously skipped in data-057 (Accela/CrimeMapping only).
- Elk Grove, CA — Sacramento County suburb; no independent open data portal found.

**data-070 skipped cities (no public API, researched 2026-03-25):**
- Overland Park, KS — opkansas.org is infrastructure/GIS data only; OPPD uses Motorola
  PremierOne for dispatch; no public crime incident or permit API found.
- Amarillo, TX — APD no public open data crime API; CrimeMapping.com view-only;
  no ArcGIS Hub or Socrata portal with permit data confirmed.
- Oxnard, CA — OPD no public crime API; no Socrata/ArcGIS/CKAN portal found.
- Salinas, CA — SPD no public crime API; no open data portal found.
- Fayetteville, AR — data.fayetteville-ar.gov has limited datasets; no crime incident
  API or queryable permit data confirmed as of 2026-03-25.

**data-071 skipped cities (no public API, researched 2026-03-25):**
- Savannah, GA — re-confirmed SCMPD no public crime incident API (3rd check).
- Augusta, GA (Richmond County) — re-confirmed RCSO consolidated govt; no open data API.
- Columbus, GA (Muscogee County) — re-confirmed MCSO consolidated govt; no open data API.
- Montgomery, AL — re-confirmed MPDAL no open data portal; no API.
- Huntsville, AL — re-confirmed HPD JustFOIA portal only; no queryable REST API.
- Little Rock, AR — re-confirmed LRPD no public incident API.
- Jackson, MS — re-confirmed JPD no open data portal.
- Knoxville, TN — re-confirmed KPD crime data by-request-only ($10/report).
- Shreveport, LA — re-confirmed SPD aggregate-only counts; no incident API.
- Akron, OH — re-confirmed APD web-only portal; no crime incident REST API.
- Winston-Salem, NC — re-confirmed WSPD no public crime API on ArcGIS or Socrata.
- Kansas City, KS — re-confirmed UG of Wyandotte County/KCK; no separate public API.
- Overland Park, KS — re-confirmed (from data-070); no public crime or permit API.
- Lubbock, TX — re-confirmed LPD quarterly PDF stats only; no API.
- Garland, TX — re-confirmed GPD no public incident-level API.
- Laredo, TX — re-confirmed LPD PDF reports only; no queryable API.
- Amarillo, TX — re-confirmed (from data-070); no public open data crime API.
- Chesapeake, VA — re-confirmed CPD no public incident-level API.
- North Las Vegas, NV — re-confirmed NLVPD no public incident-level API.
- Paradise, NV — unincorporated Clark County; LVMPD covers area; use las_vegas_crime_trends.py.
- Fremont, CA — re-confirmed FPD no public crime API.
- Irvine, CA — re-confirmed uses OCSD coverage; no city-level incident API.
- Elk Grove, CA — re-confirmed Sacramento County suburb; no independent portal.
- Oxnard, CA — re-confirmed (from data-070) OPD no public crime API.
- Salinas, CA — re-confirmed (from data-070) SPD no public crime API.
- Spokane Valley, WA — re-confirmed SVPD no public open data portal.
- Green Bay, WI — data.greenbaywi.gov does not resolve to an open data portal;
  GBPD publishes only PDF reports; no ArcGIS Hub or Socrata presence confirmed.
- Rockford, IL — cityofrockford.org no open data API; data.illinois.gov has no
  RPD crime dataset; no queryable permit data confirmed as of 2026-03-25.
- Springfield, OR — small city (~60k) adjacent to Eugene (also stub); no open data
  portal found; Lane County GIS has no Springfield PD crime incident data.

**data-074 added stubs (no public API, re-researched 2026-03-25):**
- Knoxville, TN — KPD data by-request-only ($10/report fee). Stub created.
- Akron, OH — APD web-only portal; no REST endpoint. Stub created.
- Winston-Salem, NC — WSPD no ArcGIS/Socrata crime service. Stub created.
- Shreveport, LA — SPD aggregate counts only; no incident-level API. Stub created.
- Huntsville, AL — HPD via JustFOIA only; no REST endpoint. Stub created.

**data-068 skipped cities (no public API, re-researched 2026-03-25):**
- Akron, OH — re-checked data.akronohio.gov; no crime incident REST API confirmed.
- Knoxville, TN — re-checked knoxvilletn.gov; crime data still by-request-only.
- Shreveport, LA — re-checked data.shreveportla.gov; crime data remains aggregate-only.
- Huntsville, AL — re-checked hsvcity.com open data; HPD crime data still JustFOIA only.
- Winston-Salem, NC — re-checked data.cityofws.org; WSPD crime API not available.
- Montgomery, AL — re-confirmed no open data portal; no API found.
- Little Rock, AR — re-confirmed LRPD no public incident API.
- Jackson, MS — re-confirmed JPD no open data portal.
- Columbus, GA — re-confirmed MCSO consolidated govt; no open data API.
- Savannah, GA — re-confirmed SCMPD no public crime incident API.
- Augusta, GA — re-confirmed RCSO consolidated govt; no open data API.
- Kansas City, KS — re-confirmed UG of Wyandotte County/KCK; no separate public crime API.
- Laredo, TX — re-confirmed LPD publishes PDF reports only; no queryable API.
- Garland, TX — re-confirmed GPD no public incident-level API.
- Lubbock, TX — re-confirmed LPD quarterly PDF stats only; no API.
- Chesapeake, VA — re-confirmed CPD no public incident-level API.
- North Las Vegas, NV — re-confirmed NLVPD no public incident-level API.
- Fremont, CA — re-confirmed FPD no public crime API.
- Irvine, CA — re-confirmed uses OCSD; no city-level incident API.
- Elk Grove, CA — re-confirmed Sacramento County suburb; no independent portal.
- Spokane Valley, WA — re-confirmed SVPD no public open data portal.

**Gilbert AZ org ID invalid (data-065, 2026-03-24):**
`gilbert_crime_trends.py` and `gilbert` permit config both use org ID `K1VMQDQNLVxLvLqs`
which returns `{"error": {"code": 400, "message": "Invalid URL"}}`. This org ID has been
invalid since it was introduced in data-058. To fix:
1. Visit `https://data.gilbertaz.gov` and find the Police Incidents/Crime dataset.
2. Click "I want to use this" → "API" to get the FeatureServer URL.
3. Extract the org ID (the alphanumeric segment after `services.arcgis.com/`).
4. Update `FEATURESERVER_URL` in `gilbert_crime_trends.py` and `service_url` in
   `us_city_permits_arcgis.py` for the `gilbert` entry.
5. Re-run `python backend/ingest/gilbert_crime_trends.py --dry-run` to verify.

**Symptom:** ArcGIS returns `{"error": {"code": 400, "message": "Invalid URL"}}`.

**Fix:** Monitor the city's open-data portal for future dataset publication.
Leave as non-fatal pipeline step.

**data-074: All 40 unverified permit configs disabled (2026-03-25):**
39 ArcGIS configs added to `DISABLED_SOURCE_KEYS` in `us_city_permits_arcgis.py`.
Honolulu Socrata config flagged `disabled=True` in `us_city_permits.py`.
All were returning HTTP 400 "Invalid URL" on every pipeline run.
To re-enable: run `--city <key> --discover` or visit the portal_url for that city,
find the correct FeatureServer URL, update `service_url`, remove from `DISABLED_SOURCE_KEYS`.
Disabled cities:
orlando, richmond, des_moines, tulsa, wichita, colorado_springs, arlington_tx,
virginia_beach, mesa, aurora, corpus_christi, greensboro, durham, chandler, scottsdale,
gilbert, glendale_az, henderson, tempe, peoria_az, surprise_az, goodyear_az, fort_wayne,
boise, cape_coral, eugene, springfield_mo, sioux_falls, omaha, lincoln, salem_or, honolulu.

**data-075: Research findings for 20 high-value disabled cities (2026-03-25):**
Live verification (--discover / --dry-run) requires outbound HTTPS access not available in CI.
Research was done via SKILL.md cross-reference (crime script org IDs) and training knowledge.

*Priority 1 research findings:*
- **denver** — **FIXED** (2026-03-25). Real service: `ODC_DEV_RESIDENTIALCONSTPERMIT_P/FeatureServer/316`
  on org `zdB7qR0BtYrg0Xpl`. 77,484 records. Fields: `PERMIT_NUM`, `DATE_ISSUED`, `CLASS`, `ADDRESS`.
  Also available: `ODC_DEV_COMMERCIALCONSTPERMIT_P` (commercial), `ODC_DEV_DEMOLITIONPERMIT_P`.
- **san_jose** — **REMOVED** (2026-03-25). Org `p8Tul9YqBFRRdPqD` returns 0 services on all
  subdomains (services, services1-6). No public permit FeatureServer found.
- **fort_worth** — **REMOVED** (2026-03-25). Org `AHCzmZstRKFEQEqv` returns 0 services on all
  subdomains. No public permit FeatureServer found.
- **albuquerque** — **REMOVED** (2026-03-25). Org `3HnGBxB8VqLCXhUn` returns 0 services on all
  subdomains. No public permit FeatureServer found.
- **portland** — **FIXED** (2026-03-25). Real service: `BDS_Construction_Permit_Metric/FeatureServer/0`
  on org `quVN97tn06YNGj9s`. 49,091 records. No street address field (uses PORTLAND_MAPS_URL).
- **las_vegas** — **REMOVED** (2026-03-27). Org `VIkzGEMZbaSsMGLk` returns 0 services on all
  subdomains. `gis.lasvegasnevada.gov` does not resolve. ArcGIS Hub search returns no permit data.
- **el_paso** — **REMOVED** (2026-03-27). Real data exists at `gis.elpasotexas.gov`
  (`Planning/NewResidential/MapServer/1`, 42,472 records) but server blocks python-requests
  with HTTP 403 (Cloudflare/WAF). FeatureServer endpoint also returns 403.
- **tucson** — uses self-hosted `gisdata.tucsonaz.gov` (not services.arcgis.com).
  Service path `/Building_Permits/FeatureServer/0` is unverified.
  Tucson crime is at `services3.arcgis.com/9coHY2fvuFjG9HQX` (ArcGIS Online), different host.
  Try browsing: https://gisdata.tucsonaz.gov/arcgis/rest/services for available services.
- **sacramento** — **NOT IN ARCGIS FILE**. Already configured as Socrata in `us_city_permits.py`
  (domain: data.cityofsacramento.org, dataset: `rent-6pka`). No ArcGIS FeatureServer needed.
- **jacksonville** — **REMOVED** from CITY_CONFIGS (see comment at ~line 366 in
  us_city_permits_arcgis.py). Researched 2026-03-22: maps.coj.net and gis.coj.net return 404.
  No building permit FeatureServer found on ArcGIS Online.
  JSO crime IS available at services.arcgis.com/Dv0qhb5jJMSEEVJL but no permit layer found.
- **indianapolis** — **NO PUBLIC BUILDING PERMIT DATASET**. data.indy.gov uses ArcGIS Hub
  but publishes only ordinance PDFs; no building permit FeatureServer. Verified 2026-03-22.
  IMPD crime IS available at services.arcgis.com/ghDnFwW5bG9Ljzwi but no permit layer found.

*Priority 2 research findings:*
- **virginia_beach** — org `DqA6wR9XSVCoCbVN` is unverified (MUST VERIFY in crime script too).
  Portal: https://gis.data.vbgov.com — search "building permits".
- **colorado_springs** — org `oR4yfmG5eJFhSqy7` is unverified (MUST VERIFY in crime script too).
  Portal: https://data-cospatial.opendata.arcgis.com — search "building permits".
- **aurora** — org `IJdEUGKefCEk4KsP` is unverified (MUST VERIFY in crime script too).
  Portal: https://data-auroragis.opendata.arcgis.com — search "building permits".
- **corpus_christi** — org `5eqOE8IxIoFkEeGd` is unverified (MUST VERIFY in crime script too).
  Portal: https://data-cctexas.opendata.arcgis.com — search "building permits".
- **greensboro** — org `CZ8GsPy9zJAnUBMD` is unverified (MUST VERIFY in crime script too).
  Portal: https://data-greensboroncgov.opendata.arcgis.com — search "building permits".
- **durham** — org `QLwOtBvdB5bFqPNF` is unverified (MUST VERIFY in crime script too).
  Portal: https://data-durhamnc.opendata.arcgis.com — search "building permits".
- **raleigh** — **NOT IN ARCGIS FILE**. Already configured as Socrata in `us_city_permits.py`
  (domain: data.raleighnc.gov, dataset: `k4n2-jcgh`). ArcGIS Hub may also have permits but
  Socrata is confirmed — no additional ArcGIS config needed unless Socrata dataset is invalid.
- **chandler** — org `SVsGn6WnqbDYPUgf` is unverified (MUST VERIFY in crime script too).
  Portal: https://data.chandleraz.gov — search "building permits".
- **scottsdale** — org `4sF4h3aBrdOGHDuF` is unverified (MUST VERIFY in crime script too).
  Portal: https://data.scottsdaleaz.gov — search "building permits".
- **glendale_az** — org `s0YYoMkpLLkb2IPC` is unverified (MUST VERIFY in crime script too).
  Portal: https://data.glendaleaz.gov — search "building permits".

**data-076: All remaining 31 disabled permit configs removed (2026-03-27):**
CI environment has no outbound HTTPS (curl/WebFetch/urllib all blocked). All 31 ArcGIS
configs and 1 Socrata config (Honolulu) were removed from CITY_CONFIGS / disabled=True
entries. The placeholder service name `Building_Permits/FeatureServer/0` never matched
any real ArcGIS service and all returned HTTP 400 in every pipeline run.

Org IDs and portal URLs are preserved in REMOVED comment blocks in each source file
(search for `REMOVED — data-057` through `REMOVED — data-076` in us_city_permits_arcgis.py)
and in the ArcGIS Permits table above.

*To re-add a city with network access:*
```bash
# 1. List all services for the city's org (find the permit service name):
curl -s "https://services{N}.arcgis.com/{ORG_ID}/arcgis/rest/services?f=json" \
  | python3 -c "import sys,json; [print(s['name']) for s in json.load(sys.stdin).get('services',[])]"

# 2. Try self-hosted GIS servers if ArcGIS Online has no results:
curl -s "https://gis.{city}.gov/arcgis/rest/services?f=json" | python3 -c "..."

# 3. Once you find the real service name, test it:
python backend/ingest/us_city_permits_arcgis.py --city <key> --dry-run

# 4. If it returns records: add the config back to CITY_CONFIGS with the correct
#    service_url, id_field, issue_date_field, and addr_field values.
```

**data-078: Strategic city expansion — new cities added (2026-03-27):**
CI has no outbound HTTPS. All new endpoint org IDs and service names are researched estimates, not live-tested. Next agent (data-079) should verify all MUST VERIFY endpoints.

New crime scripts added (ArcGIS MUST VERIFY):
- dallas (org K1vmv3C6RR68oGEo, service DPD_CrimeIncidents)
- st_petersburg (org 8vEm1j5dMMr9eBob, service SPPD_Crime_Incidents)
- frisco_tx (org GE4Z4z1cnF58LL3C, service FPD_Crime_Incidents)
- mckinney_tx (org 5VpNVlUxHMX5rB9c, service MPD_Crime_Incidents)
- murfreesboro (org QpJd9AijpBIH7O5B, service MPD_Crime_Incidents)
- st_paul (org v400IkDOw1ad7Yad, service SPPD_Crime_Incidents)
- toledo (org R5KgFnGrFdJMFDr4, service TPD_Crime_Incidents)
- birmingham (org iFT94KHJdBf1glgr, service BPD_Crime_Incidents)
- plano_tx (org J6sY5RXbVdFl1rTf, service PPD_Crime_Incidents)
- irving_tx (org 9xyBGNHCPT1TXqR6, service IPD_Crime_Incidents)
- riverside_ca (org nIQ0V9y1TigP8hAV, service RPD_Crime_Incidents)

New crime scripts added (Socrata MUST VERIFY):
- long_beach (data.longbeach.gov, dataset 4bz9-ggsz)
- oakland (data.oaklandca.gov, dataset ppgh-7dqv)

New crime stubs (no public API confirmed):
- bakersfield, north_port, round_rock_tx, cedar_park_tx, jersey_city,
  stockton_ca, newark_nj, garland_tx, laredo_tx, lubbock_tx, amarillo_tx

New permit configs added (ArcGIS MUST VERIFY):
- dallas, detroit, st_petersburg, birmingham, riverside, irving, orlando, plano

New permit configs added (Socrata MUST VERIFY):
- oakland (data.oaklandca.gov), long_beach (data.longbeach.gov),
  st_paul (information.stpaul.gov), toledo (opendata.toledo.oh.gov),
  newark (data.newark.gov), jersey_city (data.jerseycitynj.gov)

Note on Newark NJ: Issue #247 suggested data.newarkde.gov — this appears to be Newark, Delaware, not NJ. Newark, NJ (city ~280k) is the intended target. Used data.newark.gov as the Socrata domain; verify the correct portal.

*Next step for data-077:* Run the above for all 31 cities with network access.
Priority order (most likely to have valid data):
1. orlando, richmond, des_moines, tulsa, wichita (orgs match crime scripts)
2. virginia_beach, colorado_springs, aurora, corpus_christi, greensboro, durham
3. chandler, scottsdale, glendale_az, henderson, tempe, peoria_az, surprise_az, goodyear_az
4. fort_wayne, boise, eugene, springfield_mo, omaha, lincoln, salem_or, sioux_falls
5. cape_coral (org likely invalid; check capecoral-capegis.opendata.arcgis.com directly)
6. gilbert (org K1VMQDQNLVxLvLqs confirmed invalid; visit data.gilbertaz.gov to get correct org)
7. honolulu (Socrata): curl "https://data.honolulu.gov/api/catalog/v1?q=building+permits&limit=10"

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

---

## State School Performance Report Card APIs

Research conducted 2026-03-24 (data-065). None of these states expose a proper
REST API — all use file downloads or web-only interfaces.

### California — CAASPP (caaspp.org / cas.cde.ca.gov)

**Access:** File downloads only at https://caaspp-elpac.ets.org/caaspp/research
**Format:** Fixed-width text (`.txt`) and CSV zip archives
**Key files:**
- `sb_ca{YEAR}_all_{TYPE}_{GRADE}.txt` — Smarter Balanced scores by school
**School identifier:** 14-digit CDS code (`{county}{district}{school}`)
**Available fields:** `MeanScaleScore`, `PercentStandardMet`, `PercentStandardExceeded`
**No REST API.** Download, parse, and join on CDS code (matches NCES CCD `ncessch` mapping).
**Key limitation:** Data published annually ~August; current year is typically unavailable.

### Texas — TEA Accountability Ratings (tea.texas.gov)

**Access:** File downloads at https://tea.texas.gov/texas-schools/accountability
**Format:** Excel/CSV zip archives
**Key files:** `acctratings_{YEAR}.zip` — district and campus accountability ratings
**School identifier:** 9-digit campus number (`{district}{campus}`)
**Available fields:** `CAMPUS_RATING` (A/B/C/D/F), `DOMAIN1_SCORE` through `DOMAIN4_SCORE`
**No public REST API.** TEA's TSDS (Texas Student Data System) requires authorized
agency login. Public accountability ratings are file-download-only.

### Washington — OSPI Report Cards (reportcard.ospi.k12.wa.us)

**Access:** Socrata dataset on `data.wa.gov` and file downloads at OSPI
**Socrata domain:** `data.wa.gov`
**Relevant datasets (search "school report card" on data.wa.gov):**
  - Report card data published annually by OSPI under "Education" category
**School identifier:** 10-digit NCES `ncessch` code or WA state school code
**Available fields:** Proficiency rates, graduation rates; no single "overall rating"
  (WA eliminated A–F ratings in 2015)
**Note:** WA uses "EveryStudent Succeeds Act" descriptors (e.g. "Level 1"–"Level 4")
rather than letter grades. Fetch from `data.wa.gov` Socrata API.

### North Carolina — NCDPI Report Cards (ncreportcards.ncdpi.gov)

**Access:** File downloads and limited web API
**Download base:** https://www.dpi.nc.gov/data-reports/school-report-cards
**Format:** Excel/CSV
**School identifier:** 6-digit school code (`{LEA}{school}`)
**Available fields:** `SPG Score` (0–100), `SPG Grade` (A/B/C/D/F)
**No documented public REST API.** `ncreportcards.ncdpi.gov` is web-only.
Downloads published annually ~September.

### Ohio — ODE Report Cards (reportcard.education.ohio.gov)

**Access:** File downloads at https://reportcard.education.ohio.gov
**Format:** Excel/CSV zip archives
**Download base:** https://reportcard.education.ohio.gov/download
**School identifier:** 9-digit IRN (Information Retrieval Number)
**Available fields:** `OVERALL_GRADE` (A–F), `ACHIEVEMENT_GRADE`, `PROGRESS_GRADE`,
  `GAP_CLOSING_GRADE`
**No REST API.** `data.education.ohio.gov` (Socrata) does NOT contain report card grades —
only enrollment/staff data. Report card grades are file-download-only.

### Arizona — ADE Report Cards (azreportcards.azed.gov)

**Access:** File downloads and web UI at https://azreportcards.azed.gov
**Format:** CSV and Excel
**Download base:** https://www.azed.gov/accountability/data
**School identifier:** 9-digit entity ID or CTDS code
**Available fields:** `Letter_Grade` (A–F), `Points_Earned`, individual domain scores
**No REST API.** `azreportcards.azed.gov` is web-only. ADE publishes downloadable
accountability data files annually in October.

### Implementation Notes (do not implement yet — research only)

When implementing state school ratings, use the existing `school_rating` field in
`neighborhood_quality` (values: `"Excellent"`, `"Strong"`, `"Average"`, `"Weak"`,
`"Very Weak"`, or `null`). Map state-specific grades as follows:

| State Grade | LRE Rating |
|-------------|------------|
| A (TX/NC/OH/AZ) | `Excellent` |
| B | `Strong` |
| C | `Average` |
| D | `Weak` |
| F | `Very Weak` |
| CA (CAASPP ≥75% met standard) | `Excellent` |
| CA (60–74%) | `Strong` |
| CA (45–59%) | `Average` |
| CA (30–44%) | `Weak` |
| CA (<30%) | `Very Weak` |

Join on NCES `ncessch` code (already present in `national_school_ratings.json` from
`national_school_ratings.py`). WA state uses OSPI school codes — cross-reference via
NCES CCD.

Priority order for implementation: TX → OH → AZ → NC → CA → WA
(TX/OH/AZ are straightforward A–F; CA/WA are more complex mappings).

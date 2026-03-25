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
| Anchorage | `anchorage_crime_trends.py` | data.muni.org | `cizs-bvns` (MUST VERIFY) | `date_reported` | `reporting_area` | `anchorage_crime_trends.json` |
| Madison | `madison_crime_trends.py` | data.cityofmadison.com | `68yf-zu8t` (MUST VERIFY) | `incident_date` | `sector` | `madison_crime_trends.json` |
| Spokane | `spokane_crime_trends.py` | data.spokanecity.org | `4gj6-ujfi` (MUST VERIFY) | `reported_date` | `precinct` | `spokane_crime_trends.json` |

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
| Tempe AZ | `tempe_crime_trends.py` | `services.arcgis.com/e5BBQV9bLnUqzr4V/.../TPD_Crime_Incidents/FeatureServer/0` (MUST VERIFY — not live-tested; run `verify_arcgis_endpoints.py --city tempe`) | `IncidentDate` | `District` | `tempe_crime_trends.json` |
| Peoria AZ | `peoria_az_crime_trends.py` | `services.arcgis.com/ZNh2Q3xZvn5AJFGZ/.../PPD_Crime_Incidents/FeatureServer/0` (MUST VERIFY — not live-tested; run `verify_arcgis_endpoints.py --city peoria_az`) | `IncidentDate` | `District` | `peoria_az_crime_trends.json` |
| Surprise AZ | `surprise_az_crime_trends.py` | `services.arcgis.com/QJfxWS1GiDHgQMwH/.../SPD_Crime_Incidents/FeatureServer/0` (MUST VERIFY — not live-tested; run `verify_arcgis_endpoints.py --city surprise_az`) | `IncidentDate` | `District` | `surprise_az_crime_trends.json` |
| Goodyear AZ | `goodyear_az_crime_trends.py` | `services.arcgis.com/aMqXhGKtSoqR5lNw/.../GoPD_Crime_Incidents/FeatureServer/0` (MUST VERIFY — not live-tested; run `verify_arcgis_endpoints.py --city goodyear_az`) | `IncidentDate` | `District` | `goodyear_az_crime_trends.json` |

### OpenDataSoft-Based

| City | Script | Portal | Dataset | Date Field | Group Field | Output |
|------|--------|--------|---------|------------|-------------|--------|
| Cary NC | `cary_crime_trends.py` | `data.townofcary.org` | `cpd-incidents` | `date_from` | `district` | `cary_crime_trends.json` |

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
| Baton Rouge | `baton_rouge_crime_trends.py` | data.brla.gov | `fabb-cnnu` (MUST VERIFY) | `create_dt` | `district` | `baton_rouge_crime_trends.json` |
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
| Orlando | `orlando` | services1.arcgis.com/ySBMu4XsNZMHPCce/.../Building_Permits/FeatureServer/0 (MUST VERIFY) | `PERMIT_NUM` | `ISSUED_DATE` |
| Richmond VA | `richmond` | services1.arcgis.com/k3vhq11XkBNeeOfM/.../Building_Permits/FeatureServer/0 (MUST VERIFY) | `PERMIT_NUM` | `ISSUED_DATE` |
| Des Moines | `des_moines` | services.arcgis.com/eSi6C3K7GxWJJFTG/.../Building_Permits/FeatureServer/0 (MUST VERIFY) | `PERMIT_NUM` | `ISSUED_DATE` |
| Tulsa | `tulsa` | services.arcgis.com/vL1HzBwQf4fxjZTy/.../Building_Permits/FeatureServer/0 (MUST VERIFY) | `PERMIT_NUM` | `ISSUED_DATE` |
| Wichita | `wichita` | services.arcgis.com/sJ7GWBy3GCkiIsY7/.../Building_Permits/FeatureServer/0 (MUST VERIFY) | `PERMIT_NUM` | `ISSUED_DATE` |
| Colorado Springs | `colorado_springs` | services3.arcgis.com/oR4yfmG5eJFhSqy7/.../Building_Permits/FeatureServer/0 (MUST VERIFY) | `PERMIT_NUM` | `ISSUED_DATE` |
| Arlington TX | `arlington_tx` | services.arcgis.com/v400IkDOw1ad7Yad/.../Building_Permits/FeatureServer/0 (MUST VERIFY) | `PERMIT_NUM` | `ISSUED_DATE` |
| Virginia Beach | `virginia_beach` | services1.arcgis.com/DqA6wR9XSVCoCbVN/.../Building_Permits/FeatureServer/0 (MUST VERIFY) | `PERMIT_NUM` | `ISSUED_DATE` |
| Mesa AZ | `mesa` | services2.arcgis.com/T3Rrfm3Dqq8Eepqn/.../Building_Permits/FeatureServer/0 (MUST VERIFY) | `PERMIT_NUM` | `ISSUED_DATE` |
| Aurora CO | `aurora` | services1.arcgis.com/IJdEUGKefCEk4KsP/.../Building_Permits/FeatureServer/0 (MUST VERIFY) | `PERMIT_NUM` | `ISSUED_DATE` |
| Corpus Christi | `corpus_christi` | services.arcgis.com/5eqOE8IxIoFkEeGd/.../Building_Permits/FeatureServer/0 (MUST VERIFY) | `PERMIT_NUM` | `ISSUED_DATE` |
| Greensboro NC | `greensboro` | services.arcgis.com/CZ8GsPy9zJAnUBMD/.../Building_Permits/FeatureServer/0 (MUST VERIFY) | `PERMIT_NUM` | `ISSUED_DATE` |
| Durham NC | `durham` | services.arcgis.com/QLwOtBvdB5bFqPNF/.../Building_Permits/FeatureServer/0 (MUST VERIFY) | `PERMIT_NUM` | `ISSUED_DATE` |
| Chandler AZ | `chandler` | services.arcgis.com/SVsGn6WnqbDYPUgf/.../Building_Permits/FeatureServer/0 (MUST VERIFY) | `PERMIT_NUM` | `ISSUED_DATE` |
| Scottsdale AZ | `scottsdale` | services.arcgis.com/4sF4h3aBrdOGHDuF/.../Building_Permits/FeatureServer/0 (MUST VERIFY) | `PERMIT_NUM` | `ISSUED_DATE` |
| Gilbert AZ | `gilbert` | services.arcgis.com/K1VMQDQNLVxLvLqs/.../Building_Permits/FeatureServer/0 (**MUST VERIFY — same invalid org as crime script**) | `PERMIT_NUM` | `ISSUED_DATE` |
| Glendale AZ | `glendale_az` | services.arcgis.com/s0YYoMkpLLkb2IPC/.../Building_Permits/FeatureServer/0 (MUST VERIFY) | `PERMIT_NUM` | `ISSUED_DATE` |
| Henderson NV | `henderson` | services.arcgis.com/pGfbNXXgj2WN9j5V/.../Building_Permits/FeatureServer/0 (MUST VERIFY) | `PERMIT_NUM` | `ISSUED_DATE` |
| Tempe AZ | `tempe` | services.arcgis.com/e5BBQV9bLnUqzr4V/.../Building_Permits/FeatureServer/0 (MUST VERIFY) | `PERMIT_NUM` | `ISSUED_DATE` |
| Peoria AZ | `peoria_az` | services.arcgis.com/ZNh2Q3xZvn5AJFGZ/.../Building_Permits/FeatureServer/0 (MUST VERIFY) | `PERMIT_NUM` | `ISSUED_DATE` |
| Surprise AZ | `surprise_az` | services.arcgis.com/QJfxWS1GiDHgQMwH/.../Building_Permits/FeatureServer/0 (MUST VERIFY) | `PERMIT_NUM` | `ISSUED_DATE` |
| Goodyear AZ | `goodyear_az` | services.arcgis.com/aMqXhGKtSoqR5lNw/.../Building_Permits/FeatureServer/0 (MUST VERIFY) | `PERMIT_NUM` | `ISSUED_DATE` |

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
- Shreveport, LA — SPD publishes only aggregate street-level offense counts; no incident API.
- Tallahassee, FL — TOPS web interface only; no documented REST API.
- Huntsville, AL — JustFOIA portal for records requests; no open data API.
- Winston-Salem, NC — WSPD has no public crime data services on ArcGIS or Socrata.

**data-065 skipped cities (no public API, researched 2026-03-24):**
- Montgomery, AL — MPDAL no open data portal; no Socrata, ArcGIS Hub, or CKAN found.
- Little Rock, AR — LRPD no public incident API; no open data portal found.
- Jackson, MS — JPD no open data portal; no public crime API.
- Columbus, GA (Muscogee County) — MCSO consolidated govt; no open data API found.
- Savannah, GA — SCMPD no public crime incident API; no Socrata/ArcGIS portal.
- Augusta, GA (Richmond County) — RCSO consolidated govt; no open data API found.
- Cape Coral, FL — CCPD: data.capecoral.gov exists but no verified crime incident API.
- Kansas City, KS — Unified Government of Wyandotte County/KCK; no public crime API
  distinct from Kansas City, MO (already covered by `kansas_city_crime_trends.py`).
- Spokane Valley, WA — SVPD operates independently of Spokane PD; no public open data
  portal found for Spokane Valley Police Department as of 2026-03-24.
- Bakersfield, CA — previously skipped in data-057 (Accela/CrimeMapping only).
- Elk Grove, CA — Sacramento County suburb; no independent open data portal found.

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

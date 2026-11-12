# Column-level lineage: city

Source: `legacy_jobs/wwi/MigrateStagedCityData.sql`.
Drafted by claude-sonnet-5-5 on 2026-11-12 21:14:40, from the SQL and the table columns only.
AI-generated: the structure is checked by `migrator/lineage.py`, but the content needs a human review.

## Checks

- Structure: passed (22 columns in 3 tables).
- Agrees with independent evidence: 5 point(s).
  - Dimension.City.City Key: ignored in jobs/city.json, and the map says generated
  - Integration.Lineage.Data Load Completed: ignored in jobs/city.json, and the map says generated
  - Dimension.City: changed by the legacy job, and in the map
  - Integration.ETL Cutoff: changed by the legacy job, and in the map
  - Integration.Lineage: changed by the legacy job, and in the map
- Disagrees with independent evidence: 0 point(s), for a human to resolve.

## Kinds

- **copied**: taken from one source column as it is.
- **lookup**: found by matching a row in another table (a join or subquery).
- **calculated**: worked out from source columns (an expression, CASE, ISNULL, aggregate, ...).
- **constant**: a fixed value written in the SQL.
- **generated**: made by the database or the clock, not from any input (identity, sequence, SYSDATETIME(), ...).
- **unchanged**: the procedure never writes this column.

## Dimension.City

Operations: UPDATE, INSERT.

| Column | Kind | Comes from | SQL lines | Note |
|---|---|---|---|---|
| City Key | generated |  | 33, 34 | Omitted from the INSERT column list, so the database fills it (identity). |
| WWI City ID | copied | Integration.City_Staging.WWI City ID | 34, 38 | Copied from staging on insert. |
| City | copied | Integration.City_Staging.City | 34, 38 |  |
| State Province | copied | Integration.City_Staging.State Province | 34, 38 |  |
| Country | copied | Integration.City_Staging.Country | 34, 38 |  |
| Continent | copied | Integration.City_Staging.Continent | 34, 38 |  |
| Sales Territory | copied | Integration.City_Staging.Sales Territory | 35, 39 |  |
| Region | copied | Integration.City_Staging.Region | 35, 39 |  |
| Subregion | copied | Integration.City_Staging.Subregion | 35, 39 |  |
| Location | copied | Integration.City_Staging.Location | 35, 39 |  |
| Latest Recorded Population | copied | Integration.City_Staging.Latest Recorded Population | 36, 40 |  |
| Valid From | copied | Integration.City_Staging.Valid From | 36, 40 | Copied from staging on insert. |
| Valid To | calculated | Integration.City_Staging.Valid From<br>Integration.City_Staging.WWI City ID<br>Integration.City_Staging.Valid To | 22, 24, 27, 29, 30, 36, 40 | The UPDATE closes open rows with the minimum staging Valid From per city. The INSERT copies staging Valid To. |
| Lineage Key | lookup | Integration.Lineage.Lineage Key<br>Integration.Lineage.Table Name<br>Integration.Lineage.Data Load Completed | 13, 14, 15, 16, 17, 37, 41 | Latest open Lineage row for City, held in @LineageKey and inserted as a constant per row. |

## Integration.Lineage

Operations: UPDATE.

| Column | Kind | Comes from | SQL lines | Note |
|---|---|---|---|---|
| Lineage Key | unchanged |  |  |  |
| Data Load Started | unchanged |  |  |  |
| Table Name | unchanged |  |  |  |
| Data Load Completed | generated |  | 45 | Set to SYSDATETIME(). |
| Was Successful | constant |  | 46 | Set to 1. |
| Source System Cutoff Time | unchanged |  |  |  |

## Integration.ETL Cutoff

Operations: UPDATE.

| Column | Kind | Comes from | SQL lines | Note |
|---|---|---|---|---|
| Table Name | unchanged |  |  |  |
| Cutoff Time | lookup | Integration.Lineage.Source System Cutoff Time<br>Integration.Lineage.Lineage Key | 50, 51, 52, 54 | Subquery returns the cutoff time from the Lineage row matching @LineageKey. |

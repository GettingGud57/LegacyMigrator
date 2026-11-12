# Column-level lineage: employee

Source: `legacy_jobs/wwi/MigrateStagedEmployeeData.sql`.
Drafted by claude-sonnet-5-5 on 2026-11-12 21:31:51, from the SQL and the table columns only.
AI-generated: the structure is checked by `migrator/lineage.py`, but the content needs a human review.

## Checks

- Structure: passed (17 columns in 3 tables).
- Agrees with independent evidence: 5 point(s).
  - Dimension.Employee.Employee Key: ignored in jobs/employee.json, and the map says generated
  - Integration.Lineage.Data Load Completed: ignored in jobs/employee.json, and the map says generated
  - Dimension.Employee: changed by the legacy job, and in the map
  - Integration.ETL Cutoff: in the map, though this batch's data did not change it
  - Integration.Lineage: changed by the legacy job, and in the map
- Disagrees with independent evidence: 0 point(s), for a human to resolve.

## Kinds

- **copied**: taken from one source column as it is.
- **lookup**: found by matching a row in another table (a join or subquery).
- **calculated**: worked out from source columns (an expression, CASE, ISNULL, aggregate, ...).
- **constant**: a fixed value written in the SQL.
- **generated**: made by the database or the clock, not from any input (identity, sequence, SYSDATETIME(), ...).
- **unchanged**: the procedure never writes this column.

## Dimension.Employee

Operations: UPDATE, INSERT.

| Column | Kind | Comes from | SQL lines | Note |
|---|---|---|---|---|
| Employee Key | generated |  | 32, 33 | Not in the INSERT column list; the database generates it (identity/sequence). |
| WWI Employee ID | copied | Integration.Employee_Staging.WWI Employee ID | 33, 34, 36 | Copied from staging on insert. |
| Employee | copied | Integration.Employee_Staging.Employee | 33, 34, 36 | Copied from staging on insert. |
| Preferred Name | copied | Integration.Employee_Staging.Preferred Name | 33, 34, 36 | Copied from staging on insert. |
| Is Salesperson | copied | Integration.Employee_Staging.Is Salesperson | 33, 34, 36 | Copied from staging on insert. |
| Photo | copied | Integration.Employee_Staging.Photo | 33, 34, 36 | Copied from staging on insert. |
| Valid From | copied | Integration.Employee_Staging.Valid From | 33, 34, 36 | Copied from staging on insert. |
| Valid To | calculated | Integration.Employee_Staging.Valid From<br>Integration.Employee_Staging.WWI Employee ID<br>Integration.Employee_Staging.Valid To<br>Dimension.Employee.WWI Employee ID<br>Dimension.Employee.Valid To | 21, 23, 26, 28, 29, 30, 33, 34, 36 | Existing open rows are closed off with the minimum staged Valid From per employee; inserted rows take the staging Valid To. |
| Lineage Key | lookup | Integration.Lineage.Lineage Key<br>Integration.Lineage.Table Name<br>Integration.Lineage.Data Load Completed | 12, 13, 14, 15, 16, 33, 35 | Latest open Employee lineage key held in @LineageKey and inserted on every row. |

## Integration.Lineage

Operations: UPDATE.

| Column | Kind | Comes from | SQL lines | Note |
|---|---|---|---|---|
| Lineage Key | unchanged |  |  |  |
| Data Load Started | unchanged |  |  |  |
| Table Name | unchanged |  |  |  |
| Data Load Completed | generated |  | 39 | Set to SYSDATETIME(). |
| Was Successful | constant |  | 40 | Set to 1. |
| Source System Cutoff Time | unchanged |  |  |  |

## Integration.ETL Cutoff

Operations: UPDATE.

| Column | Kind | Comes from | SQL lines | Note |
|---|---|---|---|---|
| Table Name | unchanged |  |  |  |
| Cutoff Time | lookup | Integration.Lineage.Source System Cutoff Time<br>Integration.Lineage.Lineage Key | 44, 45, 46, 48 | Set from the Lineage row matching @LineageKey. |

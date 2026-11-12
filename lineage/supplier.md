# Column-level lineage: supplier

Source: `legacy_jobs/wwi/MigrateStagedSupplierData.sql`.
Drafted by claude-sonnet-5-5 on 2026-11-12 21:34:39, from the SQL and the table columns only.
AI-generated: the structure is checked by `migrator/lineage.py`, but the content needs a human review.

## Checks

- Structure: passed (19 columns in 3 tables).
- Agrees with independent evidence: 5 point(s).
  - Dimension.Supplier.Supplier Key: ignored in jobs/supplier.json, and the map says generated
  - Integration.Lineage.Data Load Completed: ignored in jobs/supplier.json, and the map says generated
  - Dimension.Supplier: changed by the legacy job, and in the map
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

## Dimension.Supplier

Operations: UPDATE, INSERT.

| Column | Kind | Comes from | SQL lines | Note |
|---|---|---|---|---|
| Supplier Key | generated |  | 32, 33 | Not in the INSERT column list, so the database fills it (identity or sequence). |
| WWI Supplier ID | copied | Integration.Supplier_Staging.WWI Supplier ID | 35 | Copied from staging on insert. |
| Supplier | copied | Integration.Supplier_Staging.Supplier | 35 | Copied from staging on insert. |
| Category | copied | Integration.Supplier_Staging.Category | 35 | Copied from staging on insert. |
| Primary Contact | copied | Integration.Supplier_Staging.Primary Contact | 35 | Copied from staging on insert. |
| Supplier Reference | copied | Integration.Supplier_Staging.Supplier Reference | 35 | Copied from staging on insert. |
| Payment Days | copied | Integration.Supplier_Staging.Payment Days | 36 | Copied from staging on insert. |
| Postal Code | copied | Integration.Supplier_Staging.Postal Code | 36 | Copied from staging on insert. |
| Valid From | copied | Integration.Supplier_Staging.Valid From | 36 | Copied from staging on insert. |
| Valid To | calculated | Integration.Supplier_Staging.Valid From<br>Integration.Supplier_Staging.Valid To<br>Integration.Supplier_Staging.WWI Supplier ID | 21, 26, 36 | Open rows are closed off with the MIN staging Valid From per supplier; new rows get the staging Valid To. |
| Lineage Key | lookup | Integration.Lineage.Lineage Key<br>Integration.Lineage.Table Name<br>Integration.Lineage.Data Load Completed | 12, 13, 14, 15, 16, 37 | Taken from the latest open Supplier lineage row, held in @LineageKey. |

## Integration.Lineage

Operations: UPDATE.

| Column | Kind | Comes from | SQL lines | Note |
|---|---|---|---|---|
| Lineage Key | unchanged |  |  |  |
| Data Load Started | unchanged |  |  |  |
| Table Name | unchanged |  |  |  |
| Data Load Completed | generated |  | 41 | Set to SYSDATETIME(). |
| Was Successful | constant |  | 42 | Set to 1. |
| Source System Cutoff Time | unchanged |  |  |  |

## Integration.ETL Cutoff

Operations: UPDATE.

| Column | Kind | Comes from | SQL lines | Note |
|---|---|---|---|---|
| Table Name | unchanged |  |  |  |
| Cutoff Time | lookup | Integration.Lineage.Source System Cutoff Time<br>Integration.Lineage.Lineage Key | 46, 47, 48 | Subquery returns the cutoff time of the lineage row matching @LineageKey. |

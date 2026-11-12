# Column-level lineage: transaction_type

Source: `legacy_jobs/wwi/MigrateStagedTransactionTypeData.sql`.
Drafted by claude-sonnet-5-5 on 2026-11-12 21:35:22, from the SQL and the table columns only.
AI-generated: the structure is checked by `migrator/lineage.py`, but the content needs a human review.

## Checks

- Structure: passed (14 columns in 3 tables).
- Agrees with independent evidence: 5 point(s).
  - Dimension.Transaction Type.Transaction Type Key: ignored in jobs/transaction_type.json, and the map says generated
  - Integration.Lineage.Data Load Completed: ignored in jobs/transaction_type.json, and the map says generated
  - Dimension.Transaction Type: changed by the legacy job, and in the map
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

## Dimension.Transaction Type

Operations: UPDATE, INSERT.

| Column | Kind | Comes from | SQL lines | Note |
|---|---|---|---|---|
| Transaction Type Key | generated |  | 33 | Not in the INSERT column list, so the database fills it (identity or sequence default). |
| WWI Transaction Type ID | copied | Integration.TransactionType_Staging.WWI Transaction Type ID | 34 | Copied from staging on insert; the update only uses it to match rows. |
| Transaction Type | copied | Integration.TransactionType_Staging.Transaction Type | 34 | Copied from staging. |
| Valid From | copied | Integration.TransactionType_Staging.Valid From | 34 | Copied from staging. |
| Valid To | calculated | Integration.TransactionType_Staging.Valid From<br>Integration.TransactionType_Staging.WWI Transaction Type ID<br>Integration.TransactionType_Staging.Valid To | 21, 26, 29, 30, 34 | Open rows (Valid To = @EndOfTime) are closed with the minimum staging Valid From per ID; new rows get the staging Valid To. |
| Lineage Key | lookup | Integration.Lineage.Lineage Key<br>Integration.Lineage.Table Name<br>Integration.Lineage.Data Load Completed | 12, 13, 14, 15, 16, 35 | Latest open Lineage row for 'Transaction Type', held in @LineageKey. |

## Integration.Lineage

Operations: UPDATE.

| Column | Kind | Comes from | SQL lines | Note |
|---|---|---|---|---|
| Lineage Key | unchanged |  |  | Only used in the WHERE clause. |
| Data Load Started | unchanged |  |  |  |
| Table Name | unchanged |  |  |  |
| Data Load Completed | generated |  | 39 | Set to SYSDATETIME(). |
| Was Successful | constant |  | 40 | Set to 1. |
| Source System Cutoff Time | unchanged |  |  |  |

## Integration.ETL Cutoff

Operations: UPDATE.

| Column | Kind | Comes from | SQL lines | Note |
|---|---|---|---|---|
| Table Name | unchanged |  |  | Only used in the WHERE clause. |
| Cutoff Time | lookup | Integration.Lineage.Source System Cutoff Time<br>Integration.Lineage.Lineage Key | 44, 45, 46, 48 | Subquery returns the Source System Cutoff Time of the current lineage row. |

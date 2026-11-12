# Column-level lineage: payment_method

Source: `legacy_jobs/wwi/MigrateStagedPaymentMethodData.sql`.
Drafted by claude-sonnet-5-5 on 2026-11-12 21:33:27, from the SQL and the table columns only.
AI-generated: the structure is checked by `migrator/lineage.py`, but the content needs a human review.

## Checks

- Structure: passed (14 columns in 3 tables).
- Agrees with independent evidence: 5 point(s).
  - Dimension.Payment Method.Payment Method Key: ignored in jobs/payment_method.json, and the map says generated
  - Integration.Lineage.Data Load Completed: ignored in jobs/payment_method.json, and the map says generated
  - Dimension.Payment Method: changed by the legacy job, and in the map
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

## Dimension.Payment Method

Operations: UPDATE, INSERT.

| Column | Kind | Comes from | SQL lines | Note |
|---|---|---|---|---|
| Payment Method Key | generated |  | 32, 33 | Omitted from the INSERT column list, so the database fills it (identity/default). |
| WWI Payment Method ID | copied | Integration.PaymentMethod_Staging.WWI Payment Method ID | 33, 34 | Inserted directly from staging. |
| Payment Method | copied | Integration.PaymentMethod_Staging.Payment Method | 33, 34 | Inserted directly from staging. |
| Valid From | copied | Integration.PaymentMethod_Staging.Valid From | 33, 34 | Inserted directly from staging. |
| Valid To | calculated | Integration.PaymentMethod_Staging.Valid From<br>Integration.PaymentMethod_Staging.WWI Payment Method ID<br>Integration.PaymentMethod_Staging.Valid To | 21, 23, 26, 28, 29, 30, 33, 34 | The UPDATE closes open rows with the MIN staged Valid From per ID; the INSERT copies the staged Valid To. |
| Lineage Key | lookup | Integration.Lineage.Lineage Key<br>Integration.Lineage.Table Name<br>Integration.Lineage.Data Load Completed | 12, 13, 14, 15, 16, 33, 35 | @LineageKey is the latest Lineage row for 'Payment Method' with no completion time. |

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

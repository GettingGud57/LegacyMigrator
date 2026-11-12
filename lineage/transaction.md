# Column-level lineage: transaction

Source: `legacy_jobs/wwi/MigrateStagedTransactionData.sql`.
Drafted by claude-sonnet-5-5 on 2026-11-12 21:35:08, from the SQL and the table columns only.
AI-generated: the structure is checked by `migrator/lineage.py`, but the content needs a human review.

## Checks

- Structure: passed (49 columns in 4 tables).
- Agrees with independent evidence: 6 point(s).
  - Fact.Transaction.Transaction Key: ignored in jobs/transaction.json, and the map says generated
  - Integration.Lineage.Data Load Completed: ignored in jobs/transaction.json, and the map says generated
  - Fact.Transaction: changed by the legacy job, and in the map
  - Integration.ETL Cutoff: in the map, though this batch's data did not change it
  - Integration.Lineage: changed by the legacy job, and in the map
  - Integration.Transaction_Staging: changed by the legacy job, and in the map
- Disagrees with independent evidence: 0 point(s), for a human to resolve.

## Kinds

- **copied**: taken from one source column as it is.
- **lookup**: found by matching a row in another table (a join or subquery).
- **calculated**: worked out from source columns (an expression, CASE, ISNULL, aggregate, ...).
- **constant**: a fixed value written in the SQL.
- **generated**: made by the database or the clock, not from any input (identity, sequence, SYSDATETIME(), ...).
- **unchanged**: the procedure never writes this column.

## Integration.Transaction_Staging

Operations: UPDATE.

| Column | Kind | Comes from | SQL lines | Note |
|---|---|---|---|---|
| Transaction Staging Key | unchanged |  |  |  |
| Date Key | unchanged |  |  |  |
| Customer Key | lookup | Dimension.Customer.Customer Key<br>Dimension.Customer.WWI Customer ID<br>Dimension.Customer.Valid From<br>Dimension.Customer.Valid To<br>Integration.Transaction_Staging.WWI Customer ID<br>Integration.Transaction_Staging.Last Modified When | 19, 20, 21, 22, 23, 24 | Customer Key valid at Last Modified When, or 0 if no match. |
| Bill To Customer Key | lookup | Dimension.Customer.Customer Key<br>Dimension.Customer.WWI Customer ID<br>Dimension.Customer.Valid From<br>Dimension.Customer.Valid To<br>Integration.Transaction_Staging.WWI Bill To Customer ID<br>Integration.Transaction_Staging.Last Modified When | 25, 26, 27, 28, 29, 30 | Customer Key of the bill-to customer valid at Last Modified When, or 0. |
| Supplier Key | lookup | Dimension.Supplier.Supplier Key<br>Dimension.Supplier.WWI Supplier ID<br>Dimension.Supplier.Valid From<br>Dimension.Supplier.Valid To<br>Integration.Transaction_Staging.WWI Supplier ID<br>Integration.Transaction_Staging.Last Modified When | 31, 32, 33, 34, 35, 36 | Supplier Key valid at Last Modified When, or 0. |
| Transaction Type Key | lookup | Dimension.Transaction Type.Transaction Type Key<br>Dimension.Transaction Type.WWI Transaction Type ID<br>Dimension.Transaction Type.Valid From<br>Dimension.Transaction Type.Valid To<br>Integration.Transaction_Staging.WWI Transaction Type ID<br>Integration.Transaction_Staging.Last Modified When | 37, 38, 39, 40, 41, 42 | Transaction Type Key valid at Last Modified When, or 0. |
| Payment Method Key | lookup | Dimension.Payment Method.Payment Method Key<br>Dimension.Payment Method.WWI Payment Method ID<br>Dimension.Payment Method.Valid From<br>Dimension.Payment Method.Valid To<br>Integration.Transaction_Staging.WWI Payment Method ID<br>Integration.Transaction_Staging.Last Modified When | 43, 44, 45, 46, 47, 48 | Payment Method Key valid at Last Modified When, or 0. |
| WWI Customer Transaction ID | unchanged |  |  |  |
| WWI Supplier Transaction ID | unchanged |  |  |  |
| WWI Invoice ID | unchanged |  |  |  |
| WWI Purchase Order ID | unchanged |  |  |  |
| Supplier Invoice Number | unchanged |  |  |  |
| Total Excluding Tax | unchanged |  |  |  |
| Tax Amount | unchanged |  |  |  |
| Total Including Tax | unchanged |  |  |  |
| Outstanding Balance | unchanged |  |  |  |
| Is Finalized | unchanged |  |  |  |
| WWI Customer ID | unchanged |  |  |  |
| WWI Bill To Customer ID | unchanged |  |  |  |
| WWI Supplier ID | unchanged |  |  |  |
| WWI Transaction Type ID | unchanged |  |  |  |
| WWI Payment Method ID | unchanged |  |  |  |
| Last Modified When | unchanged |  |  |  |

## Fact.Transaction

Operations: INSERT.

| Column | Kind | Comes from | SQL lines | Note |
|---|---|---|---|---|
| Transaction Key | generated |  | 53 | Not in the INSERT column list; filled by the database. |
| Date Key | copied | Integration.Transaction_Staging.Date Key | 54, 58 |  |
| Customer Key | copied | Integration.Transaction_Staging.Customer Key | 54, 58 | Staging value set by the earlier UPDATE. |
| Bill To Customer Key | copied | Integration.Transaction_Staging.Bill To Customer Key | 54, 58 | Staging value set by the earlier UPDATE. |
| Supplier Key | copied | Integration.Transaction_Staging.Supplier Key | 54, 58 | Staging value set by the earlier UPDATE. |
| Transaction Type Key | copied | Integration.Transaction_Staging.Transaction Type Key | 54, 58 | Staging value set by the earlier UPDATE. |
| Payment Method Key | copied | Integration.Transaction_Staging.Payment Method Key | 55, 59 | Staging value set by the earlier UPDATE. |
| WWI Customer Transaction ID | copied | Integration.Transaction_Staging.WWI Customer Transaction ID | 55, 59 |  |
| WWI Supplier Transaction ID | copied | Integration.Transaction_Staging.WWI Supplier Transaction ID | 55, 59 |  |
| WWI Invoice ID | copied | Integration.Transaction_Staging.WWI Invoice ID | 56, 60 |  |
| WWI Purchase Order ID | copied | Integration.Transaction_Staging.WWI Purchase Order ID | 56, 60 |  |
| Supplier Invoice Number | copied | Integration.Transaction_Staging.Supplier Invoice Number | 56, 60 |  |
| Total Excluding Tax | copied | Integration.Transaction_Staging.Total Excluding Tax | 56, 60 |  |
| Tax Amount | copied | Integration.Transaction_Staging.Tax Amount | 57, 61 |  |
| Total Including Tax | copied | Integration.Transaction_Staging.Total Including Tax | 57, 61 |  |
| Outstanding Balance | copied | Integration.Transaction_Staging.Outstanding Balance | 57, 61 |  |
| Is Finalized | copied | Integration.Transaction_Staging.Is Finalized | 57, 61 |  |
| Lineage Key | lookup | Integration.Lineage.Lineage Key<br>Integration.Lineage.Table Name<br>Integration.Lineage.Data Load Completed | 10, 11, 12, 13, 14, 57, 61 | @LineageKey is the latest open Lineage row for 'Transaction'. |

## Integration.Lineage

Operations: UPDATE.

| Column | Kind | Comes from | SQL lines | Note |
|---|---|---|---|---|
| Lineage Key | unchanged |  |  |  |
| Data Load Started | unchanged |  |  |  |
| Table Name | unchanged |  |  |  |
| Data Load Completed | generated |  | 65 | Set to SYSDATETIME(). |
| Was Successful | constant |  | 66 | Set to 1. |
| Source System Cutoff Time | unchanged |  |  |  |

## Integration.ETL Cutoff

Operations: UPDATE.

| Column | Kind | Comes from | SQL lines | Note |
|---|---|---|---|---|
| Table Name | unchanged |  |  |  |
| Cutoff Time | lookup | Integration.Lineage.Source System Cutoff Time<br>Integration.Lineage.Lineage Key | 70, 71, 72 | Cutoff taken from the Lineage row for @LineageKey. |

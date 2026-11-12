# Column-level lineage: movement

Source: `legacy_jobs/wwi/MigrateStagedMovementData.sql`.
Drafted by claude-sonnet-5-5 on 2026-11-12 21:32:14, from the SQL and the table columns only.
AI-generated: the structure is checked by `migrator/lineage.py`, but the content needs a human review.

## Checks

- Structure: passed (34 columns in 4 tables).
- Agrees with independent evidence: 6 point(s).
  - Fact.Movement.Movement Key: ignored in jobs/movement.json, and the map says generated
  - Integration.Lineage.Data Load Completed: ignored in jobs/movement.json, and the map says generated
  - Fact.Movement: changed by the legacy job, and in the map
  - Integration.ETL Cutoff: in the map, though this batch's data did not change it
  - Integration.Lineage: changed by the legacy job, and in the map
  - Integration.Movement_Staging: changed by the legacy job, and in the map
- Disagrees with independent evidence: 0 point(s), for a human to resolve.

## Kinds

- **copied**: taken from one source column as it is.
- **lookup**: found by matching a row in another table (a join or subquery).
- **calculated**: worked out from source columns (an expression, CASE, ISNULL, aggregate, ...).
- **constant**: a fixed value written in the SQL.
- **generated**: made by the database or the clock, not from any input (identity, sequence, SYSDATETIME(), ...).
- **unchanged**: the procedure never writes this column.

## Integration.Movement_Staging

Operations: UPDATE.

| Column | Kind | Comes from | SQL lines | Note |
|---|---|---|---|---|
| Movement Staging Key | unchanged |  |  |  |
| Date Key | unchanged |  |  |  |
| Stock Item Key | lookup | Dimension.Stock Item.Stock Item Key<br>Dimension.Stock Item.WWI Stock Item ID<br>Dimension.Stock Item.Valid From<br>Dimension.Stock Item.Valid To<br>Integration.Movement_Staging.WWI Stock Item ID<br>Integration.Movement_Staging.Last Modifed When | 20, 21, 22, 23, 24, 25 | Dimension key valid at the modification time; 0 if no row matches. |
| Customer Key | lookup | Dimension.Customer.Customer Key<br>Dimension.Customer.WWI Customer ID<br>Dimension.Customer.Valid From<br>Dimension.Customer.Valid To<br>Integration.Movement_Staging.WWI Customer ID<br>Integration.Movement_Staging.Last Modifed When | 26, 27, 28, 29, 30, 31 | Dimension key valid at the modification time; 0 if no row matches. |
| Supplier Key | lookup | Dimension.Supplier.Supplier Key<br>Dimension.Supplier.WWI Supplier ID<br>Dimension.Supplier.Valid From<br>Dimension.Supplier.Valid To<br>Integration.Movement_Staging.WWI Supplier ID<br>Integration.Movement_Staging.Last Modifed When | 32, 33, 34, 35, 36, 37 | Dimension key valid at the modification time; 0 if no row matches. |
| Transaction Type Key | lookup | Dimension.Transaction Type.Transaction Type Key<br>Dimension.Transaction Type.WWI Transaction Type ID<br>Dimension.Transaction Type.Valid From<br>Dimension.Transaction Type.Valid To<br>Integration.Movement_Staging.WWI Transaction Type ID<br>Integration.Movement_Staging.Last Modifed When | 38, 39, 40, 41, 42, 43 | Dimension key valid at the modification time; 0 if no row matches. |
| WWI Stock Item Transaction ID | unchanged |  |  |  |
| WWI Invoice ID | unchanged |  |  |  |
| WWI Purchase Order ID | unchanged |  |  |  |
| Quantity | unchanged |  |  |  |
| WWI Stock Item ID | unchanged |  |  |  |
| WWI Customer ID | unchanged |  |  |  |
| WWI Supplier ID | unchanged |  |  |  |
| WWI Transaction Type ID | unchanged |  |  |  |
| Last Modifed When | unchanged |  |  |  |

## Fact.Movement

Operations: MERGE.

| Column | Kind | Comes from | SQL lines | Note |
|---|---|---|---|---|
| Movement Key | generated |  | 62 | Not in the INSERT list; the database fills it, and matched rows leave it alone. |
| Date Key | copied | Integration.Movement_Staging.Date Key | 52, 64 |  |
| Stock Item Key | copied | Integration.Movement_Staging.Stock Item Key | 53, 64 | Staging value that was resolved by the earlier lookup update. |
| Customer Key | copied | Integration.Movement_Staging.Customer Key | 54, 64 | Staging value that was resolved by the earlier lookup update. |
| Supplier Key | copied | Integration.Movement_Staging.Supplier Key | 55, 64 | Staging value that was resolved by the earlier lookup update. |
| Transaction Type Key | copied | Integration.Movement_Staging.Transaction Type Key | 56, 64 | Staging value that was resolved by the earlier lookup update. |
| WWI Stock Item Transaction ID | copied | Integration.Movement_Staging.WWI Stock Item Transaction ID | 50, 64 | Merge match key; written only on insert. |
| WWI Invoice ID | copied | Integration.Movement_Staging.WWI Invoice ID | 57, 64 |  |
| WWI Purchase Order ID | copied | Integration.Movement_Staging.WWI Purchase Order ID | 58, 64 |  |
| Quantity | copied | Integration.Movement_Staging.Quantity | 59, 64 |  |
| Lineage Key | lookup | Integration.Lineage.Lineage Key<br>Integration.Lineage.Table Name<br>Integration.Lineage.Data Load Completed | 11, 12, 13, 14, 15, 60, 65 | Latest open Movement lineage row, held in @LineageKey. |

## Integration.Lineage

Operations: UPDATE.

| Column | Kind | Comes from | SQL lines | Note |
|---|---|---|---|---|
| Lineage Key | unchanged |  |  |  |
| Data Load Started | unchanged |  |  |  |
| Table Name | unchanged |  |  |  |
| Data Load Completed | generated |  | 68 | Set from SYSDATETIME(). |
| Was Successful | constant |  | 69 | Set to 1. |
| Source System Cutoff Time | unchanged |  |  |  |

## Integration.ETL Cutoff

Operations: UPDATE.

| Column | Kind | Comes from | SQL lines | Note |
|---|---|---|---|---|
| Table Name | unchanged |  |  |  |
| Cutoff Time | lookup | Integration.Lineage.Source System Cutoff Time<br>Integration.Lineage.Lineage Key | 73, 74, 75, 77 | Cutoff taken from the current lineage row, applied to the Movement row only. |

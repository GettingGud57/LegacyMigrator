# Column-level lineage: purchase

Source: `legacy_jobs/wwi/MigrateStagedPurchaseData.sql`.
Drafted by claude-sonnet-5-5 on 2026-11-12 21:33:46, from the SQL and the table columns only.
AI-generated: the structure is checked by `migrator/lineage.py`, but the content needs a human review.

## Checks

- Structure: passed (32 columns in 4 tables).
- Agrees with independent evidence: 6 point(s).
  - Fact.Purchase.Purchase Key: ignored in jobs/purchase.json, and the map says generated
  - Integration.Lineage.Data Load Completed: ignored in jobs/purchase.json, and the map says generated
  - Fact.Purchase: changed by the legacy job, and in the map
  - Integration.ETL Cutoff: in the map, though this batch's data did not change it
  - Integration.Lineage: changed by the legacy job, and in the map
  - Integration.Purchase_Staging: changed by the legacy job, and in the map
- Disagrees with independent evidence: 0 point(s), for a human to resolve.

## Kinds

- **copied**: taken from one source column as it is.
- **lookup**: found by matching a row in another table (a join or subquery).
- **calculated**: worked out from source columns (an expression, CASE, ISNULL, aggregate, ...).
- **constant**: a fixed value written in the SQL.
- **generated**: made by the database or the clock, not from any input (identity, sequence, SYSDATETIME(), ...).
- **unchanged**: the procedure never writes this column.

## Integration.Purchase_Staging

Operations: UPDATE.

| Column | Kind | Comes from | SQL lines | Note |
|---|---|---|---|---|
| Purchase Staging Key | unchanged |  |  |  |
| Date Key | unchanged |  |  |  |
| Supplier Key | lookup | Dimension.Supplier.Supplier Key<br>Dimension.Supplier.WWI Supplier ID<br>Dimension.Supplier.Valid From<br>Dimension.Supplier.Valid To<br>Integration.Purchase_Staging.WWI Supplier ID<br>Integration.Purchase_Staging.Last Modified When | 19, 20, 21, 22, 23, 24 | Supplier row valid at Last Modified When, earliest Valid From; 0 if none found. |
| Stock Item Key | lookup | Dimension.Stock Item.Stock Item Key<br>Dimension.Stock Item.WWI Stock Item ID<br>Dimension.Stock Item.Valid From<br>Dimension.Stock Item.Valid To<br>Integration.Purchase_Staging.WWI Stock Item ID<br>Integration.Purchase_Staging.Last Modified When | 25, 26, 27, 28, 29, 30 | Stock item row valid at Last Modified When, earliest Valid From; 0 if none found. |
| WWI Purchase Order ID | unchanged |  |  |  |
| Ordered Outers | unchanged |  |  |  |
| Ordered Quantity | unchanged |  |  |  |
| Received Outers | unchanged |  |  |  |
| Package | unchanged |  |  |  |
| Is Order Finalized | unchanged |  |  |  |
| WWI Supplier ID | unchanged |  |  |  |
| WWI Stock Item ID | unchanged |  |  |  |
| Last Modified When | unchanged |  |  |  |

## Fact.Purchase

Operations: DELETE, INSERT.

| Column | Kind | Comes from | SQL lines | Note |
|---|---|---|---|---|
| Purchase Key | generated |  | 41, 42, 43 | Omitted from the INSERT; filled by the database. |
| Date Key | copied | Integration.Purchase_Staging.Date Key | 42, 44 |  |
| Supplier Key | copied | Integration.Purchase_Staging.Supplier Key | 42, 44 | Staging value set by the earlier UPDATE. |
| Stock Item Key | copied | Integration.Purchase_Staging.Stock Item Key | 42, 44 | Staging value set by the earlier UPDATE. |
| WWI Purchase Order ID | copied | Integration.Purchase_Staging.WWI Purchase Order ID | 42, 44 |  |
| Ordered Outers | copied | Integration.Purchase_Staging.Ordered Outers | 42, 44 |  |
| Ordered Quantity | copied | Integration.Purchase_Staging.Ordered Quantity | 42, 44 |  |
| Received Outers | copied | Integration.Purchase_Staging.Received Outers | 43, 45 |  |
| Package | copied | Integration.Purchase_Staging.Package | 43, 45 |  |
| Is Order Finalized | copied | Integration.Purchase_Staging.Is Order Finalized | 43, 45 |  |
| Lineage Key | lookup | Integration.Lineage.Lineage Key<br>Integration.Lineage.Table Name<br>Integration.Lineage.Data Load Completed | 10, 11, 12, 13, 14, 45 | Latest open Lineage row for Purchase, held in @LineageKey. |

## Integration.Lineage

Operations: UPDATE.

| Column | Kind | Comes from | SQL lines | Note |
|---|---|---|---|---|
| Lineage Key | unchanged |  |  |  |
| Data Load Started | unchanged |  |  |  |
| Table Name | unchanged |  |  |  |
| Data Load Completed | generated |  | 49 | Set to SYSDATETIME(). |
| Was Successful | constant |  | 50 | Set to 1. |
| Source System Cutoff Time | unchanged |  |  |  |

## Integration.ETL Cutoff

Operations: UPDATE.

| Column | Kind | Comes from | SQL lines | Note |
|---|---|---|---|---|
| Table Name | unchanged |  |  |  |
| Cutoff Time | lookup | Integration.Lineage.Source System Cutoff Time<br>Integration.Lineage.Lineage Key | 54, 55, 56 | Cutoff time of the Lineage row matching @LineageKey. |

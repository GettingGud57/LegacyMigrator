# Column-level lineage: stock_holding

Source: `legacy_jobs/wwi/MigrateStagedStockHoldingData.sql`.
Drafted by claude-sonnet-5-5 on 2026-11-12 21:34:04, from the SQL and the table columns only.
AI-generated: the structure is checked by `migrator/lineage.py`, but the content needs a human review.

## Checks

- Structure: passed (26 columns in 4 tables).
- Agrees with independent evidence: 6 point(s).
  - Fact.Stock Holding.Stock Holding Key: ignored in jobs/stock_holding.json, and the map says generated
  - Integration.Lineage.Data Load Completed: ignored in jobs/stock_holding.json, and the map says generated
  - Fact.Stock Holding: changed by the legacy job, and in the map
  - Integration.ETL Cutoff: in the map, though this batch's data did not change it
  - Integration.Lineage: changed by the legacy job, and in the map
  - Integration.StockHolding_Staging: changed by the legacy job, and in the map
- Disagrees with independent evidence: 0 point(s), for a human to resolve.

## Kinds

- **copied**: taken from one source column as it is.
- **lookup**: found by matching a row in another table (a join or subquery).
- **calculated**: worked out from source columns (an expression, CASE, ISNULL, aggregate, ...).
- **constant**: a fixed value written in the SQL.
- **generated**: made by the database or the clock, not from any input (identity, sequence, SYSDATETIME(), ...).
- **unchanged**: the procedure never writes this column.

## Integration.StockHolding_Staging

Operations: UPDATE.

| Column | Kind | Comes from | SQL lines | Note |
|---|---|---|---|---|
| Stock Holding Staging Key | unchanged |  |  |  |
| Stock Item Key | lookup | Dimension.Stock Item.Stock Item Key<br>Dimension.Stock Item.WWI Stock Item ID<br>Dimension.Stock Item.Valid To<br>Integration.StockHolding_Staging.WWI Stock Item ID | 19, 20, 21, 22 | Takes the Stock Item Key of the dimension row with the latest Valid To for the matching WWI Stock Item ID, or 0 if none matches. |
| Quantity On Hand | unchanged |  |  |  |
| Bin Location | unchanged |  |  |  |
| Last Stocktake Quantity | unchanged |  |  |  |
| Last Cost Price | unchanged |  |  |  |
| Reorder Level | unchanged |  |  |  |
| Target Stock Level | unchanged |  |  |  |
| WWI Stock Item ID | unchanged |  |  |  |

## Fact.Stock Holding

Operations: INSERT.

| Column | Kind | Comes from | SQL lines | Note |
|---|---|---|---|---|
| Stock Holding Key | generated |  | 31, 32, 33 | Left out of the INSERT, so the database fills it (identity). |
| Stock Item Key | copied | Integration.StockHolding_Staging.Stock Item Key | 34 | Copied from the staging row, which was set by the earlier dimension lookup. |
| Quantity On Hand | copied | Integration.StockHolding_Staging.Quantity On Hand | 34 |  |
| Bin Location | copied | Integration.StockHolding_Staging.Bin Location | 34 |  |
| Last Stocktake Quantity | copied | Integration.StockHolding_Staging.Last Stocktake Quantity | 34 |  |
| Last Cost Price | copied | Integration.StockHolding_Staging.Last Cost Price | 35 |  |
| Reorder Level | copied | Integration.StockHolding_Staging.Reorder Level | 35 |  |
| Target Stock Level | copied | Integration.StockHolding_Staging.Target Stock Level | 35 |  |
| Lineage Key | lookup | Integration.Lineage.Lineage Key<br>Integration.Lineage.Table Name<br>Integration.Lineage.Data Load Completed | 10, 11, 12, 13, 14, 35 | Comes from @LineageKey, the latest open Lineage row for 'Stock Holding'. |

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
| Cutoff Time | lookup | Integration.Lineage.Source System Cutoff Time<br>Integration.Lineage.Lineage Key | 44, 45, 46 | Takes the Source System Cutoff Time of the Lineage row matching @LineageKey. |

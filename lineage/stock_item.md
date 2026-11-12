# Column-level lineage: stock_item

Source: `legacy_jobs/wwi/MigrateStagedStockItemData.sql`.
Drafted by claude-sonnet-5-5 on 2026-11-12 21:34:23, from the SQL and the table columns only.
AI-generated: the structure is checked by `migrator/lineage.py`, but the content needs a human review.

## Checks

- Structure: passed (28 columns in 3 tables).
- Agrees with independent evidence: 5 point(s).
  - Dimension.Stock Item.Stock Item Key: ignored in jobs/stock_item.json, and the map says generated
  - Integration.Lineage.Data Load Completed: ignored in jobs/stock_item.json, and the map says generated
  - Dimension.Stock Item: changed by the legacy job, and in the map
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

## Dimension.Stock Item

Operations: UPDATE, INSERT.

| Column | Kind | Comes from | SQL lines | Note |
|---|---|---|---|---|
| Stock Item Key | generated |  | 32, 33 | Not in the INSERT column list, so the database fills it (identity/sequence). |
| WWI Stock Item ID | copied | Integration.StockItem_Staging.WWI Stock Item ID | 33, 37 | Copied from staging on insert. |
| Stock Item | copied | Integration.StockItem_Staging.Stock Item | 33, 37 | Copied from staging. |
| Color | copied | Integration.StockItem_Staging.Color | 33, 37 | Copied from staging. |
| Selling Package | copied | Integration.StockItem_Staging.Selling Package | 33, 37 | Copied from staging. |
| Buying Package | copied | Integration.StockItem_Staging.Buying Package | 33, 37 | Copied from staging. |
| Brand | copied | Integration.StockItem_Staging.Brand | 34, 38 | Copied from staging. |
| Size | copied | Integration.StockItem_Staging.Size | 34, 38 | Copied from staging. |
| Lead Time Days | copied | Integration.StockItem_Staging.Lead Time Days | 34, 38 | Copied from staging. |
| Quantity Per Outer | copied | Integration.StockItem_Staging.Quantity Per Outer | 34, 38 | Copied from staging. |
| Is Chiller Stock | copied | Integration.StockItem_Staging.Is Chiller Stock | 34, 38 | Copied from staging. |
| Barcode | copied | Integration.StockItem_Staging.Barcode | 35, 39 | Copied from staging. |
| Tax Rate | copied | Integration.StockItem_Staging.Tax Rate | 35, 39 | Copied from staging. |
| Unit Price | copied | Integration.StockItem_Staging.Unit Price | 35, 39 | Copied from staging. |
| Recommended Retail Price | copied | Integration.StockItem_Staging.Recommended Retail Price | 35, 39 | Copied from staging. |
| Typical Weight Per Unit | copied | Integration.StockItem_Staging.Typical Weight Per Unit | 35, 39 | Copied from staging. |
| Photo | copied | Integration.StockItem_Staging.Photo | 36, 40 | Copied from staging. |
| Valid From | copied | Integration.StockItem_Staging.Valid From | 36, 40 | Copied from staging on insert. |
| Valid To | calculated | Integration.StockItem_Staging.Valid From<br>Integration.StockItem_Staging.WWI Stock Item ID<br>Integration.StockItem_Staging.Valid To | 21, 23, 26, 29, 30, 36, 40 | Open rows are closed with the staging MIN(Valid From) per item; new rows get the staging Valid To. |
| Lineage Key | lookup | Integration.Lineage.Lineage Key<br>Integration.Lineage.Table Name<br>Integration.Lineage.Data Load Completed | 12, 13, 14, 15, 16, 41 | @LineageKey is the latest unfinished Stock Item lineage row. |

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
| Cutoff Time | lookup | Integration.Lineage.Source System Cutoff Time<br>Integration.Lineage.Lineage Key | 50, 51, 52 | Subquery fetches the cutoff time for @LineageKey. |

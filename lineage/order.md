# Column-level lineage: order

Source: `legacy_jobs/wwi/MigrateStagedOrderData.sql`.
Drafted by claude-sonnet-5-5 on 2026-11-12 21:33:12, from the SQL and the table columns only.
AI-generated: the structure is checked by `migrator/lineage.py`, but the content needs a human review.

## Checks

- Structure: passed (52 columns in 4 tables).
- Agrees with independent evidence: 6 point(s).
  - Fact.Order.Order Key: ignored in jobs/order.json, and the map says generated
  - Integration.Lineage.Data Load Completed: ignored in jobs/order.json, and the map says generated
  - Fact.Order: changed by the legacy job, and in the map
  - Integration.ETL Cutoff: in the map, though this batch's data did not change it
  - Integration.Lineage: changed by the legacy job, and in the map
  - Integration.Order_Staging: changed by the legacy job, and in the map
- Disagrees with independent evidence: 0 point(s), for a human to resolve.

## Kinds

- **copied**: taken from one source column as it is.
- **lookup**: found by matching a row in another table (a join or subquery).
- **calculated**: worked out from source columns (an expression, CASE, ISNULL, aggregate, ...).
- **constant**: a fixed value written in the SQL.
- **generated**: made by the database or the clock, not from any input (identity, sequence, SYSDATETIME(), ...).
- **unchanged**: the procedure never writes this column.

## Integration.Order_Staging

Operations: UPDATE.

| Column | Kind | Comes from | SQL lines | Note |
|---|---|---|---|---|
| Order Staging Key | unchanged |  |  |  |
| City Key | lookup | Dimension.City.City Key<br>Dimension.City.WWI City ID<br>Dimension.City.Valid From<br>Dimension.City.Valid To<br>Integration.Order_Staging.WWI City ID<br>Integration.Order_Staging.Last Modified When | 19, 20, 21, 22, 23, 24 | Looks up the city version valid at Last Modified When, defaulting to 0 if none is found. |
| Customer Key | lookup | Dimension.Customer.Customer Key<br>Dimension.Customer.WWI Customer ID<br>Dimension.Customer.Valid From<br>Dimension.Customer.Valid To<br>Integration.Order_Staging.WWI Customer ID<br>Integration.Order_Staging.Last Modified When | 25, 26, 27, 28, 29, 30 | Looks up the customer version valid at Last Modified When, defaulting to 0 if none is found. |
| Stock Item Key | lookup | Dimension.Stock Item.Stock Item Key<br>Dimension.Stock Item.WWI Stock Item ID<br>Dimension.Stock Item.Valid From<br>Dimension.Stock Item.Valid To<br>Integration.Order_Staging.WWI Stock Item ID<br>Integration.Order_Staging.Last Modified When | 31, 32, 33, 34, 35, 36 | Looks up the stock item version valid at Last Modified When, defaulting to 0 if none is found. |
| Order Date Key | unchanged |  |  |  |
| Picked Date Key | unchanged |  |  |  |
| Salesperson Key | lookup | Dimension.Employee.Employee Key<br>Dimension.Employee.WWI Employee ID<br>Dimension.Employee.Valid From<br>Dimension.Employee.Valid To<br>Integration.Order_Staging.WWI Salesperson ID<br>Integration.Order_Staging.Last Modified When | 37, 38, 39, 40, 41, 42 | Looks up the employee version valid at Last Modified When for the salesperson, defaulting to 0. |
| Picker Key | lookup | Dimension.Employee.Employee Key<br>Dimension.Employee.WWI Employee ID<br>Dimension.Employee.Valid From<br>Dimension.Employee.Valid To<br>Integration.Order_Staging.WWI Picker ID<br>Integration.Order_Staging.Last Modified When | 43, 44, 45, 46, 47, 48 | Looks up the employee version valid at Last Modified When for the picker, defaulting to 0. |
| WWI Order ID | unchanged |  |  |  |
| WWI Backorder ID | unchanged |  |  |  |
| Description | unchanged |  |  |  |
| Package | unchanged |  |  |  |
| Quantity | unchanged |  |  |  |
| Unit Price | unchanged |  |  |  |
| Tax Rate | unchanged |  |  |  |
| Total Excluding Tax | unchanged |  |  |  |
| Tax Amount | unchanged |  |  |  |
| Total Including Tax | unchanged |  |  |  |
| Lineage Key | unchanged |  |  |  |
| WWI City ID | unchanged |  |  |  |
| WWI Customer ID | unchanged |  |  |  |
| WWI Stock Item ID | unchanged |  |  |  |
| WWI Salesperson ID | unchanged |  |  |  |
| WWI Picker ID | unchanged |  |  |  |
| Last Modified When | unchanged |  |  |  |

## Fact.Order

Operations: DELETE, INSERT.

| Column | Kind | Comes from | SQL lines | Note |
|---|---|---|---|---|
| Order Key | generated |  | 59, 60, 63 | Omitted from the INSERT column list, so the database fills it by itself. |
| City Key | copied | Integration.Order_Staging.City Key | 60, 64 | Copied from the staging key resolved by the earlier UPDATE. |
| Customer Key | copied | Integration.Order_Staging.Customer Key | 60, 64 | Copied from the staging key resolved by the earlier UPDATE. |
| Stock Item Key | copied | Integration.Order_Staging.Stock Item Key | 60, 64 | Copied from the staging key resolved by the earlier UPDATE. |
| Order Date Key | copied | Integration.Order_Staging.Order Date Key | 60, 64 |  |
| Picked Date Key | copied | Integration.Order_Staging.Picked Date Key | 60, 64 |  |
| Salesperson Key | copied | Integration.Order_Staging.Salesperson Key | 61, 65 | Copied from the staging key resolved by the earlier UPDATE. |
| Picker Key | copied | Integration.Order_Staging.Picker Key | 61, 65 | Copied from the staging key resolved by the earlier UPDATE. |
| WWI Order ID | copied | Integration.Order_Staging.WWI Order ID | 61, 65 |  |
| WWI Backorder ID | copied | Integration.Order_Staging.WWI Backorder ID | 61, 65 |  |
| Description | copied | Integration.Order_Staging.Description | 61, 65 |  |
| Package | copied | Integration.Order_Staging.Package | 62, 66 |  |
| Quantity | copied | Integration.Order_Staging.Quantity | 62, 66 |  |
| Unit Price | copied | Integration.Order_Staging.Unit Price | 62, 66 |  |
| Tax Rate | copied | Integration.Order_Staging.Tax Rate | 62, 66 |  |
| Total Excluding Tax | copied | Integration.Order_Staging.Total Excluding Tax | 62, 66 |  |
| Tax Amount | copied | Integration.Order_Staging.Tax Amount | 62, 66 |  |
| Total Including Tax | copied | Integration.Order_Staging.Total Including Tax | 63, 67 |  |
| Lineage Key | lookup | Integration.Lineage.Lineage Key<br>Integration.Lineage.Table Name<br>Integration.Lineage.Data Load Completed | 10, 11, 12, 13, 14, 63, 67 | Uses @LineageKey, the latest open Order lineage row. |

## Integration.Lineage

Operations: UPDATE.

| Column | Kind | Comes from | SQL lines | Note |
|---|---|---|---|---|
| Lineage Key | unchanged |  |  |  |
| Data Load Started | unchanged |  |  |  |
| Table Name | unchanged |  |  |  |
| Data Load Completed | generated |  | 71 | Set to the current clock time with SYSDATETIME(). |
| Was Successful | constant |  | 72 | Set to 1. |
| Source System Cutoff Time | unchanged |  |  |  |

## Integration.ETL Cutoff

Operations: UPDATE.

| Column | Kind | Comes from | SQL lines | Note |
|---|---|---|---|---|
| Table Name | unchanged |  |  |  |
| Cutoff Time | lookup | Integration.Lineage.Source System Cutoff Time<br>Integration.Lineage.Lineage Key | 76, 77, 78 | Takes the cutoff time from the Lineage row matching @LineageKey. |

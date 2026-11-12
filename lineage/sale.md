# Column-level lineage: sale

Source: `legacy_jobs/wwi/MigrateStagedSaleData.sql`.
Drafted by claude-sonnet-5-5 on 2026-11-12 21:20:06, from the SQL and the table columns only.
AI-generated: the structure is checked by `migrator/lineage.py`, but the content needs a human review.

## Checks

- Structure: passed (55 columns in 4 tables).
- Agrees with independent evidence: 6 point(s).
  - Fact.Sale.Sale Key: ignored in jobs/sale.json, and the map says generated
  - Integration.Lineage.Data Load Completed: ignored in jobs/sale.json, and the map says generated
  - Fact.Sale: changed by the legacy job, and in the map
  - Integration.ETL Cutoff: in the map, though this batch's data did not change it
  - Integration.Lineage: changed by the legacy job, and in the map
  - Integration.Sale_Staging: changed by the legacy job, and in the map
- Disagrees with independent evidence: 0 point(s), for a human to resolve.

## Kinds

- **copied**: taken from one source column as it is.
- **lookup**: found by matching a row in another table (a join or subquery).
- **calculated**: worked out from source columns (an expression, CASE, ISNULL, aggregate, ...).
- **constant**: a fixed value written in the SQL.
- **generated**: made by the database or the clock, not from any input (identity, sequence, SYSDATETIME(), ...).
- **unchanged**: the procedure never writes this column.

## Integration.Sale_Staging

Operations: UPDATE.

| Column | Kind | Comes from | SQL lines | Note |
|---|---|---|---|---|
| Sale Staging Key | unchanged |  |  |  |
| City Key | lookup | Dimension.City.City Key<br>Dimension.City.WWI City ID<br>Dimension.City.Valid From<br>Dimension.City.Valid To<br>Integration.Sale_Staging.WWI City ID<br>Integration.Sale_Staging.Last Modified When | 20, 21, 22, 23, 24, 25 | City Key valid at Last Modified When, or 0 if no match. |
| Customer Key | lookup | Dimension.Customer.Customer Key<br>Dimension.Customer.WWI Customer ID<br>Dimension.Customer.Valid From<br>Dimension.Customer.Valid To<br>Integration.Sale_Staging.WWI Customer ID<br>Integration.Sale_Staging.Last Modified When | 26, 27, 28, 29, 30, 31 | Customer Key valid at Last Modified When, or 0 if no match. |
| Bill To Customer Key | lookup | Dimension.Customer.Customer Key<br>Dimension.Customer.WWI Customer ID<br>Dimension.Customer.Valid From<br>Dimension.Customer.Valid To<br>Integration.Sale_Staging.WWI Bill To Customer ID<br>Integration.Sale_Staging.Last Modified When | 32, 33, 34, 35, 36, 37 | Customer Key matched on the bill-to customer ID, or 0 if no match. |
| Stock Item Key | lookup | Dimension.Stock Item.Stock Item Key<br>Dimension.Stock Item.WWI Stock Item ID<br>Dimension.Stock Item.Valid From<br>Dimension.Stock Item.Valid To<br>Integration.Sale_Staging.WWI Stock Item ID<br>Integration.Sale_Staging.Last Modified When | 38, 39, 40, 41, 42, 43 | Stock Item Key valid at Last Modified When, or 0 if no match. |
| Invoice Date Key | unchanged |  |  |  |
| Delivery Date Key | unchanged |  |  |  |
| Salesperson Key | lookup | Dimension.Employee.Employee Key<br>Dimension.Employee.WWI Employee ID<br>Dimension.Employee.Valid From<br>Dimension.Employee.Valid To<br>Integration.Sale_Staging.WWI Salesperson ID<br>Integration.Sale_Staging.Last Modified When | 44, 45, 46, 47, 48, 49 | Employee Key valid at Last Modified When, or 0 if no match. |
| WWI Invoice ID | unchanged |  |  |  |
| Description | unchanged |  |  |  |
| Package | unchanged |  |  |  |
| Quantity | unchanged |  |  |  |
| Unit Price | unchanged |  |  |  |
| Tax Rate | unchanged |  |  |  |
| Total Excluding Tax | unchanged |  |  |  |
| Tax Amount | unchanged |  |  |  |
| Profit | unchanged |  |  |  |
| Total Including Tax | unchanged |  |  |  |
| Total Dry Items | unchanged |  |  |  |
| Total Chiller Items | unchanged |  |  |  |
| WWI City ID | unchanged |  |  |  |
| WWI Customer ID | unchanged |  |  |  |
| WWI Bill To Customer ID | unchanged |  |  |  |
| WWI Stock Item ID | unchanged |  |  |  |
| WWI Salesperson ID | unchanged |  |  |  |
| Last Modified When | unchanged |  |  |  |

## Fact.Sale

Operations: DELETE, INSERT.

| Column | Kind | Comes from | SQL lines | Note |
|---|---|---|---|---|
| Sale Key | generated |  | 60, 61, 62, 63 | Omitted from the INSERT column list, so the database fills it. |
| City Key | copied | Integration.Sale_Staging.City Key | 61, 64 |  |
| Customer Key | copied | Integration.Sale_Staging.Customer Key | 61, 64 |  |
| Bill To Customer Key | copied | Integration.Sale_Staging.Bill To Customer Key | 61, 64 |  |
| Stock Item Key | copied | Integration.Sale_Staging.Stock Item Key | 61, 64 |  |
| Invoice Date Key | copied | Integration.Sale_Staging.Invoice Date Key | 61, 64 |  |
| Delivery Date Key | copied | Integration.Sale_Staging.Delivery Date Key | 61, 64 |  |
| Salesperson Key | copied | Integration.Sale_Staging.Salesperson Key | 62, 65 |  |
| WWI Invoice ID | copied | Integration.Sale_Staging.WWI Invoice ID | 62, 65 |  |
| Description | copied | Integration.Sale_Staging.Description | 62, 65 |  |
| Package | copied | Integration.Sale_Staging.Package | 62, 65 |  |
| Quantity | copied | Integration.Sale_Staging.Quantity | 62, 65 |  |
| Unit Price | copied | Integration.Sale_Staging.Unit Price | 62, 65 |  |
| Tax Rate | copied | Integration.Sale_Staging.Tax Rate | 62, 65 |  |
| Total Excluding Tax | copied | Integration.Sale_Staging.Total Excluding Tax | 63, 66 |  |
| Tax Amount | copied | Integration.Sale_Staging.Tax Amount | 63, 66 |  |
| Profit | copied | Integration.Sale_Staging.Profit | 63, 66 |  |
| Total Including Tax | copied | Integration.Sale_Staging.Total Including Tax | 63, 66 |  |
| Total Dry Items | copied | Integration.Sale_Staging.Total Dry Items | 63, 66 |  |
| Total Chiller Items | copied | Integration.Sale_Staging.Total Chiller Items | 63, 66 |  |
| Lineage Key | lookup | Integration.Lineage.Lineage Key<br>Integration.Lineage.Table Name<br>Integration.Lineage.Data Load Completed | 11, 12, 13, 14, 15, 63, 66 | Uses @LineageKey, the latest Lineage row for Sale that has not completed. |

## Integration.Lineage

Operations: UPDATE.

| Column | Kind | Comes from | SQL lines | Note |
|---|---|---|---|---|
| Lineage Key | unchanged |  |  |  |
| Data Load Started | unchanged |  |  |  |
| Table Name | unchanged |  |  |  |
| Data Load Completed | generated |  | 70 | Set to SYSDATETIME(). |
| Was Successful | constant |  | 71 | Set to 1. |
| Source System Cutoff Time | unchanged |  |  |  |

## Integration.ETL Cutoff

Operations: UPDATE.

| Column | Kind | Comes from | SQL lines | Note |
|---|---|---|---|---|
| Table Name | unchanged |  |  |  |
| Cutoff Time | lookup | Integration.Lineage.Source System Cutoff Time<br>Integration.Lineage.Lineage Key | 75, 76, 77 | Cutoff taken from the Lineage row for @LineageKey. |

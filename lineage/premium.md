# Column-level lineage: premium

Source: `legacy_jobs/insurance/MigrateStagedPremiumData.sql`.
Drafted by claude-sonnet-5-5 on 2026-11-12 21:20:50, from the SQL and the table columns only.
AI-generated: the structure is checked by `migrator/lineage.py`, but the content needs a human review.

## Checks

- Structure: passed (34 columns in 4 tables).
- Agrees with independent evidence: 6 point(s).
  - Fact.Premium.Premium Key: ignored in jobs/premium.json, and the map says generated
  - Integration.Lineage.Data Load Completed: ignored in jobs/premium.json, and the map says generated
  - Fact.Premium: changed by the legacy job, and in the map
  - Integration.ETL Cutoff: changed by the legacy job, and in the map
  - Integration.Lineage: changed by the legacy job, and in the map
  - Integration.Premium_Staging: changed by the legacy job, and in the map
- Disagrees with independent evidence: 0 point(s), for a human to resolve.

## Kinds

- **copied**: taken from one source column as it is.
- **lookup**: found by matching a row in another table (a join or subquery).
- **calculated**: worked out from source columns (an expression, CASE, ISNULL, aggregate, ...).
- **constant**: a fixed value written in the SQL.
- **generated**: made by the database or the clock, not from any input (identity, sequence, SYSDATETIME(), ...).
- **unchanged**: the procedure never writes this column.

## Integration.Premium_Staging

Operations: UPDATE.

| Column | Kind | Comes from | SQL lines | Note |
|---|---|---|---|---|
| Premium Staging Key | unchanged |  |  |  |
| Policy Key | lookup | Dimension.Policy.Policy Key<br>Dimension.Policy.Source Policy ID<br>Dimension.Policy.Valid From<br>Dimension.Policy.Valid To<br>Integration.Premium_Staging.Source Policy ID<br>Integration.Premium_Staging.Last Modified When | 17, 18, 19, 20, 21, 22 | Policy version valid at the modified time, with 0 if none is found. |
| Customer Key | lookup | Dimension.Customer.Customer Key<br>Dimension.Customer.Source Customer ID<br>Dimension.Customer.Valid From<br>Dimension.Customer.Valid To<br>Integration.Premium_Staging.Source Customer ID<br>Integration.Premium_Staging.Last Modified When | 23, 24, 25, 26, 27, 28 | Customer version valid at the modified time, with 0 if none is found. |
| Agent Key | lookup | Dimension.Employee.Employee Key<br>Dimension.Employee.Source Employee ID<br>Dimension.Employee.Valid From<br>Dimension.Employee.Valid To<br>Integration.Premium_Staging.Source Agent ID<br>Integration.Premium_Staging.Last Modified When | 29, 30, 31, 32, 33, 34 | Employee version valid at the modified time, with 0 if none is found. |
| Transaction Date Key | unchanged |  |  |  |
| Source Transaction ID | unchanged |  |  |  |
| Source Policy ID | unchanged |  |  |  |
| Source Customer ID | unchanged |  |  |  |
| Source Agent ID | unchanged |  |  |  |
| Transaction Type | unchanged |  |  |  |
| Gross Premium | unchanged |  |  |  |
| Commission Rate | unchanged |  |  |  |
| Tax Rate | unchanged |  |  |  |
| Last Modified When | unchanged |  |  |  |

## Fact.Premium

Operations: DELETE, INSERT.

| Column | Kind | Comes from | SQL lines | Note |
|---|---|---|---|---|
| Premium Key | generated |  | 41, 42 | Left out of the INSERT, so the database fills it. |
| Policy Key | copied | Integration.Premium_Staging.Policy Key | 42, 44 |  |
| Customer Key | copied | Integration.Premium_Staging.Customer Key | 42, 44 |  |
| Agent Key | copied | Integration.Premium_Staging.Agent Key | 42, 44 |  |
| Transaction Date Key | copied | Integration.Premium_Staging.Transaction Date Key | 42, 44 |  |
| Source Transaction ID | copied | Integration.Premium_Staging.Source Transaction ID | 42, 44 |  |
| Transaction Type | copied | Integration.Premium_Staging.Transaction Type | 43, 44 |  |
| Gross Premium | copied | Integration.Premium_Staging.Gross Premium | 43, 45 |  |
| Commission Amount | calculated | Integration.Premium_Staging.Gross Premium<br>Integration.Premium_Staging.Commission Rate | 43, 46 | Gross premium times commission rate, rounded to 2 places. |
| Tax Amount | calculated | Integration.Premium_Staging.Gross Premium<br>Integration.Premium_Staging.Tax Rate | 43, 47 | Gross premium times tax rate, rounded to 2 places. |
| Net Premium | calculated | Integration.Premium_Staging.Gross Premium<br>Integration.Premium_Staging.Commission Rate | 43, 48 | Gross premium minus the rounded commission; tax is not deducted. |
| Lineage Key | lookup | Integration.Lineage.Lineage Key<br>Integration.Lineage.Table Name<br>Integration.Lineage.Data Load Completed | 10, 11, 12, 13, 14, 43, 49 | Latest open Premium lineage row, held in @LineageKey. |

## Integration.Lineage

Operations: UPDATE.

| Column | Kind | Comes from | SQL lines | Note |
|---|---|---|---|---|
| Lineage Key | unchanged |  |  |  |
| Data Load Started | unchanged |  |  |  |
| Table Name | unchanged |  |  |  |
| Data Load Completed | generated |  | 53 | Set from SYSDATETIME(). |
| Was Successful | constant |  | 54 | Always set to 1. |
| Source System Cutoff Time | unchanged |  |  |  |

## Integration.ETL Cutoff

Operations: UPDATE.

| Column | Kind | Comes from | SQL lines | Note |
|---|---|---|---|---|
| Table Name | unchanged |  |  |  |
| Cutoff Time | lookup | Integration.Lineage.Source System Cutoff Time<br>Integration.Lineage.Lineage Key | 58, 59, 60 | Cutoff time of the lineage row for the current load. |

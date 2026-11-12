# Column-level lineage: customer

Source: `legacy_jobs/wwi/MigrateStagedCustomerData.sql`.
Drafted by claude-sonnet-5-5 on 2026-11-12 21:31:39, from the SQL and the table columns only.
AI-generated: the structure is checked by `migrator/lineage.py`, but the content needs a human review.

## Checks

- Structure: passed (19 columns in 3 tables).
- Agrees with independent evidence: 5 point(s).
  - Dimension.Customer.Customer Key: ignored in jobs/customer.json, and the map says generated
  - Integration.Lineage.Data Load Completed: ignored in jobs/customer.json, and the map says generated
  - Dimension.Customer: changed by the legacy job, and in the map
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

## Dimension.Customer

Operations: UPDATE, INSERT.

| Column | Kind | Comes from | SQL lines | Note |
|---|---|---|---|---|
| Customer Key | generated |  | 32, 33 | Omitted from the INSERT column list, so the database fills it (identity/sequence). |
| WWI Customer ID | copied | Integration.Customer_Staging.WWI Customer ID | 33, 36 | Copied from staging on insert. |
| Customer | copied | Integration.Customer_Staging.Customer | 33, 36 | Copied from staging on insert. |
| Bill To Customer | copied | Integration.Customer_Staging.Bill To Customer | 33, 36 | Copied from staging on insert. |
| Category | copied | Integration.Customer_Staging.Category | 33, 36 | Copied from staging on insert. |
| Buying Group | copied | Integration.Customer_Staging.Buying Group | 34, 37 | Copied from staging on insert. |
| Primary Contact | copied | Integration.Customer_Staging.Primary Contact | 34, 37 | Copied from staging on insert. |
| Postal Code | copied | Integration.Customer_Staging.Postal Code | 34, 37 | Copied from staging on insert. |
| Valid From | copied | Integration.Customer_Staging.Valid From | 34, 37 | Copied from staging on insert. |
| Valid To | calculated | Integration.Customer_Staging.Valid From<br>Integration.Customer_Staging.WWI Customer ID<br>Integration.Customer_Staging.Valid To<br>Dimension.Customer.WWI Customer ID<br>Dimension.Customer.Valid To | 18, 21, 23, 25, 26, 28, 29, 30, 34, 37 | Open rows (Valid To = end of time) are closed off with the earliest staged Valid From per customer; new rows take staging Valid To. |
| Lineage Key | lookup | Integration.Lineage.Lineage Key<br>Integration.Lineage.Table Name<br>Integration.Lineage.Data Load Completed | 12, 13, 14, 15, 16, 35, 38 | Latest open Customer lineage row's key, held in @LineageKey. |

## Integration.Lineage

Operations: UPDATE.

| Column | Kind | Comes from | SQL lines | Note |
|---|---|---|---|---|
| Lineage Key | unchanged |  |  |  |
| Data Load Started | unchanged |  |  |  |
| Table Name | unchanged |  |  |  |
| Data Load Completed | generated |  | 42 | Set to SYSDATETIME(). |
| Was Successful | constant |  | 43 | Set to 1. |
| Source System Cutoff Time | unchanged |  |  |  |

## Integration.ETL Cutoff

Operations: UPDATE.

| Column | Kind | Comes from | SQL lines | Note |
|---|---|---|---|---|
| Table Name | unchanged |  |  |  |
| Cutoff Time | lookup | Integration.Lineage.Source System Cutoff Time<br>Integration.Lineage.Lineage Key | 47, 48, 49, 51 | Taken from the Lineage row matching @LineageKey, for the Customer row only. |

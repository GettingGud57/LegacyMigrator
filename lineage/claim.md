# Column-level lineage: claim

Source: `legacy_jobs/insurance/MigrateStagedClaimData.sql`.
Drafted by claude-sonnet-5-5 on 2026-11-12 21:20:29, from the SQL and the table columns only.
AI-generated: the structure is checked by `migrator/lineage.py`, but the content needs a human review.

## Checks

- Structure: passed (41 columns in 4 tables).
- Agrees with independent evidence: 6 point(s).
  - Fact.Claim.Claim Key: ignored in jobs/claim.json, and the map says generated
  - Integration.Lineage.Data Load Completed: ignored in jobs/claim.json, and the map says generated
  - Fact.Claim: changed by the legacy job, and in the map
  - Integration.Claim_Staging: changed by the legacy job, and in the map
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

## Integration.Claim_Staging

Operations: UPDATE.

| Column | Kind | Comes from | SQL lines | Note |
|---|---|---|---|---|
| Claim Staging Key | unchanged |  |  |  |
| Policy Key | lookup | Dimension.Policy.Policy Key<br>Dimension.Policy.Source Policy ID<br>Dimension.Policy.Valid From<br>Dimension.Policy.Valid To<br>Integration.Claim_Staging.Source Policy ID<br>Integration.Claim_Staging.Last Modified When | 17, 18, 19, 20, 21, 22 | Policy version valid at Last Modified When, matched on Source Policy ID; 0 if none is found. |
| Customer Key | lookup | Dimension.Customer.Customer Key<br>Dimension.Customer.Source Customer ID<br>Dimension.Customer.Valid From<br>Dimension.Customer.Valid To<br>Integration.Claim_Staging.Source Customer ID<br>Integration.Claim_Staging.Last Modified When | 23, 24, 25, 26, 27, 28 | Customer version valid at Last Modified When, matched on Source Customer ID; 0 if none is found. |
| Adjuster Key | lookup | Dimension.Employee.Employee Key<br>Dimension.Employee.Source Employee ID<br>Dimension.Employee.Valid From<br>Dimension.Employee.Valid To<br>Integration.Claim_Staging.Source Adjuster ID<br>Integration.Claim_Staging.Last Modified When | 29, 30, 31, 32, 33, 34 | Employee version valid at Last Modified When, matched Source Employee ID to Source Adjuster ID; 0 if none is found. |
| Loss Date Key | unchanged |  |  |  |
| Reported Date Key | unchanged |  |  |  |
| Source Claim ID | unchanged |  |  |  |
| Source Claim Line ID | unchanged |  |  |  |
| Source Policy ID | unchanged |  |  |  |
| Source Customer ID | unchanged |  |  |  |
| Source Adjuster ID | unchanged |  |  |  |
| Coverage Type | unchanged |  |  |  |
| Claim Status | unchanged |  |  |  |
| Claimed Amount | unchanged |  |  |  |
| Approved Amount | unchanged |  |  |  |
| Paid Amount | unchanged |  |  |  |
| Deductible Applied | unchanged |  |  |  |
| Last Modified When | unchanged |  |  |  |

## Fact.Claim

Operations: DELETE, INSERT.

| Column | Kind | Comes from | SQL lines | Note |
|---|---|---|---|---|
| Claim Key | generated |  | 41 | Omitted from the INSERT, so the database fills it. |
| Policy Key | copied | Integration.Claim_Staging.Policy Key | 45 | Staging value resolved by the earlier update. |
| Customer Key | copied | Integration.Claim_Staging.Customer Key | 45 | Staging value resolved by the earlier update. |
| Adjuster Key | copied | Integration.Claim_Staging.Adjuster Key | 45 | Staging value resolved by the earlier update. |
| Loss Date Key | copied | Integration.Claim_Staging.Loss Date Key | 45 |  |
| Reported Date Key | copied | Integration.Claim_Staging.Reported Date Key | 45 |  |
| Source Claim ID | copied | Integration.Claim_Staging.Source Claim ID | 46 |  |
| Source Claim Line ID | copied | Integration.Claim_Staging.Source Claim Line ID | 46 |  |
| Coverage Type | copied | Integration.Claim_Staging.Coverage Type | 46 |  |
| Claim Status | copied | Integration.Claim_Staging.Claim Status | 46 |  |
| Claimed Amount | copied | Integration.Claim_Staging.Claimed Amount | 47 |  |
| Approved Amount | copied | Integration.Claim_Staging.Approved Amount | 47 |  |
| Paid Amount | copied | Integration.Claim_Staging.Paid Amount | 47 |  |
| Deductible Applied | copied | Integration.Claim_Staging.Deductible Applied | 47 |  |
| Lineage Key | lookup | Integration.Lineage.Lineage Key<br>Integration.Lineage.Table Name<br>Integration.Lineage.Data Load Completed | 10, 11, 12, 13, 14, 47 | Latest open Lineage row for table Claim, held in @LineageKey. |

## Integration.Lineage

Operations: UPDATE.

| Column | Kind | Comes from | SQL lines | Note |
|---|---|---|---|---|
| Lineage Key | unchanged |  |  |  |
| Data Load Started | unchanged |  |  |  |
| Table Name | unchanged |  |  |  |
| Data Load Completed | generated |  | 51 | Set to SYSDATETIME(). |
| Was Successful | constant |  | 52 | Set to 1. |
| Source System Cutoff Time | unchanged |  |  |  |

## Integration.ETL Cutoff

Operations: UPDATE.

| Column | Kind | Comes from | SQL lines | Note |
|---|---|---|---|---|
| Table Name | unchanged |  |  |  |
| Cutoff Time | lookup | Integration.Lineage.Source System Cutoff Time<br>Integration.Lineage.Lineage Key | 56, 57, 58 | Cutoff from the Lineage row for @LineageKey. |

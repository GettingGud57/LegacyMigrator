# Insurance test databases

Two databases built in the same style as Microsoft's WideWorldImporters, so insurance jobs can be tested the same way as the Sale job.
This folder only builds the databases and loads data.
The legacy stored procedures are not here: they are written by hand and go in `legacy_jobs/insurance/`.

## What gets built

**InsuranceOps** is the source system, like the shop database `WideWorldImporters`.
It holds only the current state of each record, in schema `Operations`:

| Table | Rows (approx.) | What it is |
|---|---|---|
| Customers | 2,000 | Policyholders, with region and risk tier |
| Employees | 60 | IDs 1-40 are agents, 41-60 are adjusters |
| Policies | 3,000 | One-year Motor, Home, Travel and Life policies |
| ClaimLines | ~3,000 | Claims, each with 1 to 3 coverage lines |
| PremiumTransactions | ~6,000 | New, Renewal, Endorsement and Cancellation (negative) |

**InsuranceDW** is the warehouse, like `WideWorldImportersDW`:

| Schema | Tables |
|---|---|
| Dimension | `Customer`, `Employee`, `Policy` (with history), `Date` |
| Fact | `Claim`, `Premium` |
| Integration | `Claim_Staging`, `Premium_Staging`, `Lineage`, `ETL Cutoff` |

It follows the WideWorldImporters conventions:

- Dimensions keep history (Type 2).
  When a customer, employee or policy changes, the old row gets a `Valid To` and a new row starts at the same moment.
  The current row has `Valid To` = `9999-12-31 23:59:59.9999999`.
- Key 0 in every dimension is the "Unknown" member.
- Staging tables arrive with source IDs filled in and warehouse Keys NULL.
- `Lineage` records each load, and `ETL Cutoff` records how far each table has been loaded.
- Facts have foreign keys to the dimensions.

One difference: staging tables are ordinary tables, not memory-optimized.
They survive a SQL Server restart, and the staging load can run inside a transaction.

## The data timeline

The fact tables are loaded up to the cutoff **2025-06-01**.
Claims created before the cutoff but edited after it are in `Fact.Claim` in their old version (status Open, nothing paid).
Some premium transactions were corrected after the cutoff the same way.
That gives the delete-and-reinsert pattern real work to do.

Two windows are left for the legacy jobs to load:

| Window | Last Modified When | Loaders |
|---|---|---|
| dev | after 2025-06-01, up to 2025-07-01 | `load_claim_staging.sql`, `load_premium_staging.sql` |
| holdout | after 2025-09-01, up to 2025-10-01 | `load_claim_staging_holdout.sql`, `load_premium_staging_holdout.sql` |

Each loader empties its staging table, opens a `Lineage` row for the load, and copies the rows edited in the window from InsuranceOps.
Each one is a single batch with no `GO`, so `migrator/run_legacy.py` can run it as a `staging_script`.

All data is generated deterministically, so every rebuild produces exactly the same rows.

## Edge cases in each window

These are there to catch translations that don't copy SQL Server exactly.

| Case | Dev | Holdout |
|---|---|---|
| Claim edited at the exact moment its customer changed version | claim 9001 (customer 2000) | claim 9101 (customer 1999) |
| Claim edited at the exact moment its policy was endorsed | claim 9002 (policy 3000) | claim 9102 (policy 2999) |
| Claim for a policy and customer that don't exist in the warehouse | claim 9003 | claim 9103 |
| Claim with no adjuster, timestamp using all 7 fractional digits | claim 9004 | claim 9104 |
| Premium transaction for an agent that doesn't exist | transaction 99990001 | transaction 99990002 |

Every Endorsement transaction is also stamped at the exact moment its policy changed.
Cancellations have negative amounts.

## Build it

Needs the SQL Server container running and the same `.env` as `run_legacy.py`.
From the repo root:

```
python scripts/insurance/run_sql.py scripts/insurance/create_insurance.sql
```

It prints a row count per table at the end.
It drops and recreates both databases, so it can be rerun at any time to reset.

## Adding a legacy job

1. Write the procedure in `legacy_jobs/insurance/`, for example `MigrateStagedClaimData.sql`.
2. Create it in the warehouse:

   ```
   python scripts/insurance/run_sql.py legacy_jobs/insurance/MigrateStagedClaimData.sql InsuranceDW
   ```

3. Describe the job in `jobs/claim.json`.
   The holdout is a batch of the same job with the holdout loader, so it gets its own `snapshots/claim_holdout/` folder.
   `keys` and `ignore` are chosen by a human, with a written reason for each ignored column:

   ```json
   {
     "legacy_sql": "legacy_jobs/insurance/MigrateStagedClaimData.sql",
     "database": "InsuranceDW",
     "proc": "Integration.MigrateStagedClaimData",
     "staging_script": "scripts/insurance/load_claim_staging.sql",
     "tables": [
       "Integration.Claim_Staging",
       "Integration.Lineage",
       "Integration.[ETL Cutoff]",
       "Dimension.Customer",
       "Dimension.Employee",
       "Dimension.Policy",
       "Fact.Claim"
     ],
     "batches": {
       "holdout": {"staging_script": "scripts/insurance/load_claim_staging_holdout.sql"}
     },
     "keys": {},
     "ignore": {}
   }
   ```

4. Run it: `python migrator/run_legacy.py claim`, then `python migrator/run_legacy.py claim_holdout`.

## Seed rules worth knowing

The seed loader for `Fact.Premium` used these amounts:
Commission = ROUND(Gross × Commission Rate, 2), Tax = ROUND(Gross × Tax Rate, 2), Net = Gross - Commission.
A legacy job is free to use different rules.
Rows it reloads are deleted and reinserted, so older seeded rows keep the seed rules.

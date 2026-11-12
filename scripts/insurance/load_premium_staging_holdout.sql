/*
load_premium_staging_holdout.sql: load the holdout window of premium transactions into Integration.Premium_Staging.

    window: Last Modified When > 2025-09-01T00:00:00 and <= 2025-10-01T00:00:00

Plays the part of the ETL tool's extract step (SSIS in WideWorldImporters):
empties staging, opens a Lineage record for this load, and copies the premium
transactions edited in the window from the source system (InsuranceOps).
Warehouse Keys are left NULL for the legacy job to fill in.

Single batch with no GO, so migrator/run_legacy.py can run it as a staging_script.
*/
SET NOCOUNT ON;

DECLARE @From datetime2(7) = '2025-09-01T00:00:00';
DECLARE @To   datetime2(7) = '2025-10-01T00:00:00';

TRUNCATE TABLE Integration.Premium_Staging;

INSERT Integration.Lineage ([Data Load Started], [Table Name], [Data Load Completed], [Was Successful], [Source System Cutoff Time])
VALUES (SYSDATETIME(), N'Premium', NULL, 0, @To);

INSERT Integration.Premium_Staging
    ([Policy Key], [Customer Key], [Agent Key], [Transaction Date Key],
     [Source Transaction ID], [Source Policy ID], [Source Customer ID], [Source Agent ID],
     [Transaction Type], [Gross Premium], [Commission Rate], [Tax Rate], [Last Modified When])
SELECT NULL, NULL, NULL, pt.TransactionDate,
       pt.TransactionID, pt.PolicyID, pt.CustomerID, pt.AgentID,
       pt.TransactionType, pt.GrossPremium, pt.CommissionRate, pt.TaxRate, pt.LastEditedWhen
FROM InsuranceOps.Operations.PremiumTransactions AS pt
WHERE pt.LastEditedWhen > @From
  AND pt.LastEditedWhen <= @To
ORDER BY pt.TransactionID;

SELECT (SELECT MAX([Lineage Key]) FROM Integration.Lineage WHERE [Table Name] = N'Premium') AS [Lineage Key],
       COUNT(*) AS [Transactions Staged],
       @From AS [Window From],
       @To AS [Window To]
FROM Integration.Premium_Staging;

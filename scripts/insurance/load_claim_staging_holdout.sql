/*
load_claim_staging_holdout.sql: load the holdout window of claim lines into Integration.Claim_Staging.

    window: Last Modified When > 2025-09-01T00:00:00 and <= 2025-10-01T00:00:00

Plays the part of the ETL tool's extract step (SSIS in WideWorldImporters):
empties staging, opens a Lineage record for this load, and copies the claim lines
edited in the window from the source system (InsuranceOps).
Warehouse Keys are left NULL for the legacy job to fill in.

Single batch with no GO, so migrator/run_legacy.py can run it as a staging_script.
*/
SET NOCOUNT ON;

DECLARE @From datetime2(7) = '2025-09-01T00:00:00';
DECLARE @To   datetime2(7) = '2025-10-01T00:00:00';

TRUNCATE TABLE Integration.Claim_Staging;

INSERT Integration.Lineage ([Data Load Started], [Table Name], [Data Load Completed], [Was Successful], [Source System Cutoff Time])
VALUES (SYSDATETIME(), N'Claim', NULL, 0, @To);

INSERT Integration.Claim_Staging
    ([Policy Key], [Customer Key], [Adjuster Key], [Loss Date Key], [Reported Date Key],
     [Source Claim ID], [Source Claim Line ID], [Source Policy ID], [Source Customer ID], [Source Adjuster ID],
     [Coverage Type], [Claim Status], [Claimed Amount], [Approved Amount], [Paid Amount], [Deductible Applied],
     [Last Modified When])
SELECT NULL, NULL, NULL, cl.LossDate, cl.ReportedDate,
       cl.ClaimID, cl.ClaimLineID, cl.PolicyID, cl.CustomerID, cl.AdjusterID,
       cl.CoverageType, cl.ClaimStatus, cl.ClaimedAmount, cl.ApprovedAmount, cl.PaidAmount, cl.DeductibleApplied,
       cl.LastEditedWhen
FROM InsuranceOps.Operations.ClaimLines AS cl
WHERE cl.LastEditedWhen > @From
  AND cl.LastEditedWhen <= @To
ORDER BY cl.ClaimLineID;

SELECT (SELECT MAX([Lineage Key]) FROM Integration.Lineage WHERE [Table Name] = N'Claim') AS [Lineage Key],
       COUNT(*) AS [Lines Staged],
       COUNT(DISTINCT [Source Claim ID]) AS [Claims Staged],
       @From AS [Window From],
       @To AS [Window To]
FROM Integration.Claim_Staging;

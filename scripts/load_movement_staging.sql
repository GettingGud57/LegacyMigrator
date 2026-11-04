-- load_movement_staging.sql
-- Fills WideWorldImportersDW.Integration.Movement_Staging the way Microsoft's SSIS package would,
-- so Integration.MigrateStagedMovementData has input to work on. Same pattern as load_sale_staging.sql.
-- Run against WideWorldImportersDW. Needs the WideWorldImporters (shop) database on the same server.
-- Staging is memory-only (DURABILITY = SCHEMA_ONLY): it empties on every SQL Server restart.

SET NOCOUNT ON;

-- 1. Pick a time window. Default: the month up to the warehouse's last Movement load.
DECLARE @NewCutoff  datetime2(7) = COALESCE(CAST(SESSION_CONTEXT(N'window_to') AS datetime2(7)),
                                            (SELECT [Cutoff Time] FROM Integration.[ETL Cutoff] WHERE [Table Name] = N'Movement'));
DECLARE @LastCutoff datetime2(7) = COALESCE(CAST(SESSION_CONTEXT(N'window_from') AS datetime2(7)),
                                            DATEADD(month, -1, @NewCutoff));

-- 2. Clear staging (in-memory tables don't allow TRUNCATE)
DELETE FROM Integration.Movement_Staging;

-- 3. Pull the stock movements edited inside the window, through a temp table
--    (one statement can't write an in-memory table and read another database).
CREATE TABLE #movements (
    [Date Key]                      date,
    [WWI Stock Item Transaction ID] int,
    [WWI Invoice ID]                int,
    [WWI Purchase Order ID]         int,
    [Quantity]                      int,
    [WWI Stock Item ID]             int,
    [WWI Customer ID]               int,
    [WWI Supplier ID]               int,
    [WWI Transaction Type ID]       int,
    [Transaction Occurred When]     datetime2(7)
);

INSERT INTO #movements
EXEC WideWorldImporters.Integration.GetMovementUpdates @LastCutoff = @LastCutoff, @NewCutoff = @NewCutoff;

-- GetMovementUpdates returns [Transaction Occurred When]; the staging column is spelled
-- [Last Modifed When] (Microsoft's typo). It's the only date-time the extract returns, so the
-- SSIS package must map one onto the other. We can't open the package to confirm; see the report.
INSERT INTO Integration.Movement_Staging
    ([Date Key], [WWI Stock Item Transaction ID], [WWI Invoice ID], [WWI Purchase Order ID], [Quantity],
     [WWI Stock Item ID], [WWI Customer ID], [WWI Supplier ID], [WWI Transaction Type ID], [Last Modifed When])
SELECT * FROM #movements;

DROP TABLE #movements;

-- 4. Open a lineage record. MigrateStagedMovementData looks for one with no completion time.
EXEC Integration.GetLineageKey @TableName = N'Movement', @NewCutoffTime = @NewCutoff;

-- 5. Report what got staged
SELECT COUNT(*) AS staged_rows,
       COUNT(DISTINCT [WWI Stock Item Transaction ID]) AS transactions,
       @LastCutoff AS window_from,
       @NewCutoff  AS window_to
FROM Integration.Movement_Staging;

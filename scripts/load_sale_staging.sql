-- load_sale_staging.sql
-- Fills WideWorldImportersDW.Integration.Sale_Staging the way Microsoft's SSIS package would,
-- so Integration.MigrateStagedSaleData has input to work on.
-- Run against WideWorldImportersDW. Needs the WideWorldImporters (shop) database on the same server.
-- Staging is memory-only (DURABILITY = SCHEMA_ONLY): it empties on every SQL Server restart, so rerun this first.

SET NOCOUNT ON;

-- 1. Pick a time window: one month, ending @MonthsBack months before the warehouse's last load.
--    0 = the month up to the last load (the dev batch).
--    run_legacy.py sets 1 for the holdout batch: the month before that, which the translator never sees.
DECLARE @MonthsBack int = 0;
DECLARE @LastLoad   datetime2(7) = (SELECT [Cutoff Time] FROM Integration.[ETL Cutoff] WHERE [Table Name] = N'Sale');
DECLARE @NewCutoff  datetime2(7) = DATEADD(month, -@MonthsBack, @LastLoad);
DECLARE @LastCutoff datetime2(7) = DATEADD(month, -1, @NewCutoff);

-- 2. Clear staging (in-memory tables don't allow TRUNCATE)
DELETE FROM Integration.Sale_Staging;

-- 3. Pull the changed sales from the shop database.
--    In-memory tables can't be written in the same statement as another user database,
--    so go through a temp table.
CREATE TABLE #sales (
    [Invoice Date Key]        date,
    [Delivery Date Key]       date,
    [WWI Invoice ID]          int,
    [Description]             nvarchar(100),
    [Package]                 nvarchar(50),
    [Quantity]                int,
    [Unit Price]              decimal(18,2),
    [Tax Rate]                decimal(18,3),
    [Total Excluding Tax]     decimal(18,2),
    [Tax Amount]              decimal(18,2),
    [Profit]                  decimal(18,2),
    [Total Including Tax]     decimal(18,2),
    [Total Dry Items]         int,
    [Total Chiller Items]     int,
    [WWI City ID]             int,
    [WWI Customer ID]         int,
    [WWI Bill To Customer ID] int,
    [WWI Stock Item ID]       int,
    [WWI Salesperson ID]      int,
    [Last Modified When]      datetime2(7)
);

INSERT INTO #sales
EXEC WideWorldImporters.Integration.GetSaleUpdates @LastCutoff = @LastCutoff, @NewCutoff = @NewCutoff;

INSERT INTO Integration.Sale_Staging
    ([Invoice Date Key], [Delivery Date Key], [WWI Invoice ID], [Description], [Package], [Quantity],
     [Unit Price], [Tax Rate], [Total Excluding Tax], [Tax Amount], [Profit], [Total Including Tax],
     [Total Dry Items], [Total Chiller Items], [WWI City ID], [WWI Customer ID], [WWI Bill To Customer ID],
     [WWI Stock Item ID], [WWI Salesperson ID], [Last Modified When])
SELECT * FROM #sales;

DROP TABLE #sales;

-- 4. Open a lineage record. MigrateStagedSaleData looks for one with no completion time.
EXEC Integration.GetLineageKey @TableName = N'Sale', @NewCutoffTime = @NewCutoff;

-- 5. Report what got staged
SELECT COUNT(*) AS staged_rows,
       COUNT(DISTINCT [WWI Invoice ID]) AS invoices,
       @LastCutoff AS window_from,
       @NewCutoff  AS window_to
FROM Integration.Sale_Staging;

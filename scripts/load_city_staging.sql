-- load_city_staging.sql
-- Fills WideWorldImportersDW.Integration.City_Staging the way Microsoft's SSIS package would,
-- so Integration.MigrateStagedCityData has input to work on.
-- Run against WideWorldImportersDW. Needs the WideWorldImporters (shop) database on the same server.

SET NOCOUNT ON;

-- 1. Pick a time window: @WindowMonths long, ending @MonthsBack months before the warehouse's last city load.
--    Cities rarely change: the shop database only has city changes in Jan 2013, Jul 2013, Jul 2014 and Jul 2015,
--    so the month next to the last load (as load_sale_staging.sql uses) would stage nothing.
--    The defaults are the dev batch: July 2015. jobs/city.json changes them for its other batches.
DECLARE @MonthsBack   int = 11;
DECLARE @WindowMonths int = 1;
DECLARE @LastLoad   datetime2(7) = (SELECT [Cutoff Time] FROM Integration.[ETL Cutoff] WHERE [Table Name] = N'City');
DECLARE @NewCutoff  datetime2(7) = DATEADD(month, -@MonthsBack, @LastLoad);
DECLARE @LastCutoff datetime2(7) = DATEADD(month, -@WindowMonths, @NewCutoff);

-- 2. Clear staging
DELETE FROM Integration.City_Staging;

-- 3. Pull the changed cities from the shop database, through a temp table as in load_sale_staging.sql.
--    The temp table copies its column types from City_Staging, so the two can't drift apart.
SELECT TOP (0)
    [WWI City ID], City, [State Province], Country, Continent, [Sales Territory], Region, Subregion,
    [Location], [Latest Recorded Population], [Valid From], [Valid To]
INTO #cities
FROM Integration.City_Staging;

INSERT INTO #cities
EXEC WideWorldImporters.Integration.GetCityUpdates @LastCutoff = @LastCutoff, @NewCutoff = @NewCutoff;

INSERT INTO Integration.City_Staging
    ([WWI City ID], City, [State Province], Country, Continent, [Sales Territory], Region, Subregion,
     [Location], [Latest Recorded Population], [Valid From], [Valid To])
SELECT * FROM #cities;

DROP TABLE #cities;

-- 4. Open a lineage record. MigrateStagedCityData looks for one with no completion time.
EXEC Integration.GetLineageKey @TableName = N'City', @NewCutoffTime = @NewCutoff;

-- 5. Report what got staged
SELECT COUNT(*) AS staged_rows,
       COUNT(DISTINCT [WWI City ID]) AS cities,
       @LastCutoff AS window_from,
       @NewCutoff  AS window_to
FROM Integration.City_Staging;

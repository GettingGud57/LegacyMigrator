-- load_city_staging.sql
-- Fills WideWorldImportersDW.Integration.City_Staging the way Microsoft's SSIS package would,
-- so Integration.MigrateStagedCityData has input to work on. Same pattern as load_sale_staging.sql.
-- Run against WideWorldImportersDW. Needs the WideWorldImporters (shop) database on the same server.

SET NOCOUNT ON;

-- 1. Pick a time window. Default: the month up to the warehouse's last City load.
--    The job spec (jobs/city.json) passes a different window, because nothing about cities
--    changed in that last month. See run_legacy.py for how window_from / window_to arrive.
DECLARE @NewCutoff  datetime2(7) = COALESCE(CAST(SESSION_CONTEXT(N'window_to') AS datetime2(7)),
                                            (SELECT [Cutoff Time] FROM Integration.[ETL Cutoff] WHERE [Table Name] = N'City'));
DECLARE @LastCutoff datetime2(7) = COALESCE(CAST(SESSION_CONTEXT(N'window_from') AS datetime2(7)),
                                            DATEADD(month, -1, @NewCutoff));

-- 2. Clear staging. City_Staging is an ordinary table, but DELETE keeps it like the others.
DELETE FROM Integration.City_Staging;

-- 3. Ask the shop for every city version that started inside the window.
--    GetCityUpdates also emits a new version of every city in a country or state whose
--    details changed, which is why one country change can mean thousands of rows.
CREATE TABLE #cities (
    [WWI City ID]                int,
    [City]                       nvarchar(50),
    [State Province]             nvarchar(50),
    [Country]                    nvarchar(60),
    [Continent]                  nvarchar(30),
    [Sales Territory]            nvarchar(50),
    [Region]                     nvarchar(30),
    [Subregion]                  nvarchar(30),
    [Location]                   geography,
    [Latest Recorded Population] bigint,
    [Valid From]                 datetime2(7),
    [Valid To]                   datetime2(7)
);

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

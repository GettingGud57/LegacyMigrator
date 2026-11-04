-- holdout_stats.sql
-- Helps pick the holdout window for the Sale job. For every month of sales in the shop, counts the
-- invoice lines where a subtle translation mistake would change the result of the dimension lookups
-- in Integration.MigrateStagedSaleData. A window with many such lines is a sharper test.
-- Run against WideWorldImportersDW (needs WideWorldImporters on the same server). Read-only.
--
-- The real lookup:  TOP(1) key WHERE id matches AND LMW > [Valid From] AND LMW <= [Valid To] ORDER BY [Valid From], else 0
-- Columns:
--   no_match       some lookup finds nothing, so the key is 0       (catches NULL-instead-of-0)
--   ge_differs     ">=" on Valid From picks a different key          (catches >= instead of >)
--   no_to_differs  dropping the Valid To condition changes the key   (catches a missing Valid To)
--   desc_differs   ORDER BY [Valid From] DESC changes the key. In this data every such case is a tie:
--                  two versions with the SAME [Valid From], so it measures SQL Server's tie-break, not the date order.
--   split_invoices invoices whose lines fall in different months, so a window holds only part of them
SET NOCOUNT ON;

CREATE TABLE #s (
    [Invoice Date Key] date, [Delivery Date Key] date, [WWI Invoice ID] int, [Description] nvarchar(100),
    [Package] nvarchar(50), [Quantity] int, [Unit Price] decimal(18,2), [Tax Rate] decimal(18,3),
    [Total Excluding Tax] decimal(18,2), [Tax Amount] decimal(18,2), [Profit] decimal(18,2),
    [Total Including Tax] decimal(18,2), [Total Dry Items] int, [Total Chiller Items] int,
    [WWI City ID] int, [WWI Customer ID] int, [WWI Bill To Customer ID] int, [WWI Stock Item ID] int,
    [WWI Salesperson ID] int, [Last Modified When] datetime2(7));
INSERT INTO #s EXEC WideWorldImporters.Integration.GetSaleUpdates @LastCutoff = '2012-01-01', @NewCutoff = '2016-06-06 12:31:17';

-- one row per (line, lookup): the dimension versions for that id, in one table
CREATE TABLE #v (dim varchar(20), id int, k int, vf datetime2(7), vt datetime2(7));
INSERT #v SELECT 'city', [WWI City ID], [City Key], [Valid From], [Valid To] FROM Dimension.City;
INSERT #v SELECT 'customer', [WWI Customer ID], [Customer Key], [Valid From], [Valid To] FROM Dimension.Customer;
INSERT #v SELECT 'stock', [WWI Stock Item ID], [Stock Item Key], [Valid From], [Valid To] FROM Dimension.[Stock Item];
INSERT #v SELECT 'employee', [WWI Employee ID], [Employee Key], [Valid From], [Valid To] FROM Dimension.Employee;
CREATE CLUSTERED INDEX ix ON #v (dim, id, vf);

CREATE TABLE #l (line int IDENTITY, inv int, lmw datetime2(7), dim varchar(20), id int);
INSERT #l (inv, lmw, dim, id)
SELECT [WWI Invoice ID], [Last Modified When], d.dim, d.id
FROM #s CROSS APPLY (VALUES ('city', [WWI City ID]), ('customer', [WWI Customer ID]),
                            ('customer', [WWI Bill To Customer ID]), ('stock', [WWI Stock Item ID]),
                            ('employee', [WWI Salesperson ID])) AS d(dim, id);

SELECT l.inv, l.lmw,
       COALESCE(ok.k, 0) AS k_ok, COALESCE(ge.k, 0) AS k_ge, COALESCE(nt.k, 0) AS k_nt, COALESCE(ds.k, 0) AS k_ds
INTO #r
FROM #l AS l
OUTER APPLY (SELECT TOP(1) k FROM #v WHERE dim = l.dim AND id = l.id AND l.lmw >  vf AND l.lmw <= vt ORDER BY vf) AS ok
OUTER APPLY (SELECT TOP(1) k FROM #v WHERE dim = l.dim AND id = l.id AND l.lmw >= vf AND l.lmw <= vt ORDER BY vf) AS ge
OUTER APPLY (SELECT TOP(1) k FROM #v WHERE dim = l.dim AND id = l.id AND l.lmw >  vf                  ORDER BY vf) AS nt
OUTER APPLY (SELECT TOP(1) k FROM #v WHERE dim = l.dim AND id = l.id AND l.lmw >  vf AND l.lmw <= vt ORDER BY vf DESC) AS ds;

-- month of each invoice's earliest and latest line edit
SELECT [WWI Invoice ID] AS inv, MIN([Last Modified When]) AS first_edit, MAX([Last Modified When]) AS last_edit
INTO #inv FROM #s GROUP BY [WWI Invoice ID];

SELECT FORMAT(lmw, 'yyyy-MM') AS month,
       COUNT(*) / 5 AS lines,
       COUNT(DISTINCT inv) AS invoices,
       SUM(CASE WHEN k_ok = 0 THEN 1 ELSE 0 END) AS no_match,
       SUM(CASE WHEN k_ge <> k_ok THEN 1 ELSE 0 END) AS ge_differs,
       SUM(CASE WHEN k_nt <> k_ok THEN 1 ELSE 0 END) AS no_to_differs,
       SUM(CASE WHEN k_ds <> k_ok THEN 1 ELSE 0 END) AS desc_differs,
       (SELECT COUNT(*) FROM #inv WHERE FORMAT(first_edit, 'yyyy-MM') <> FORMAT(last_edit, 'yyyy-MM')
                                    AND FORMAT(last_edit, 'yyyy-MM') = FORMAT(MIN(r.lmw), 'yyyy-MM')) AS split_invoices
FROM #r AS r
GROUP BY FORMAT(lmw, 'yyyy-MM')
ORDER BY month;

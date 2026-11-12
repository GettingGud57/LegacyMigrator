/*
create_insurance.sql: build the insurance test databases in WideWorldImporters style.

    InsuranceOps   the source system (policies, claims, premium transactions)
    InsuranceDW    the warehouse (Dimension, Fact and Integration schemas)

Rerunnable: drops and recreates both databases.
All data is generated deterministically (hashes of row numbers, no NEWID or RAND),
so every run produces exactly the same rows.

The warehouse is loaded up to the cutoff 2025-06-01.
Two later windows are left for the legacy jobs to load:
    dev       2025-06-01 to 2025-07-01   (scripts/insurance/load_*_staging.sql)
    holdout   2025-09-01 to 2025-10-01   (scripts/insurance/load_*_staging_holdout.sql)

Run from the repo root:
    python scripts/insurance/run_sql.py scripts/insurance/create_insurance.sql
*/

USE master;
GO

IF DB_ID(N'InsuranceDW') IS NOT NULL
BEGIN
    ALTER DATABASE InsuranceDW SET SINGLE_USER WITH ROLLBACK IMMEDIATE;
    DROP DATABASE InsuranceDW;
END;
IF DB_ID(N'InsuranceOps') IS NOT NULL
BEGIN
    ALTER DATABASE InsuranceOps SET SINGLE_USER WITH ROLLBACK IMMEDIATE;
    DROP DATABASE InsuranceOps;
END;
GO

CREATE DATABASE InsuranceOps;
GO
CREATE DATABASE InsuranceDW;
GO

/* =====================================================================
   1. Generated data, held in temp tables for the rest of this session
   ===================================================================== */

USE InsuranceOps;
GO

SET NOCOUNT ON;

-- #n: 60,000 numbered rows with 8 deterministic pseudo-random ints each (0 .. 2^31-1).
-- Ranges of n are reserved per entity so they don't share random values:
--   1-2000 customers, 5001-5060 employees, 10001-13000 policies,
--   20001-21600 claims, 30001-35000 claim lines, 40001-53000 premium transactions
IF OBJECT_ID('tempdb..#n') IS NOT NULL DROP TABLE #n;
WITH nums AS (
    SELECT TOP (60000) ROW_NUMBER() OVER (ORDER BY (SELECT NULL)) AS n
    FROM sys.all_objects AS a
    CROSS JOIN sys.all_objects AS b
)
SELECT nums.n,
       CAST(SUBSTRING(x.h,  1, 4) AS int) & 2147483647 AS r1,
       CAST(SUBSTRING(x.h,  5, 4) AS int) & 2147483647 AS r2,
       CAST(SUBSTRING(x.h,  9, 4) AS int) & 2147483647 AS r3,
       CAST(SUBSTRING(x.h, 13, 4) AS int) & 2147483647 AS r4,
       CAST(SUBSTRING(x.h, 17, 4) AS int) & 2147483647 AS r5,
       CAST(SUBSTRING(x.h, 21, 4) AS int) & 2147483647 AS r6,
       CAST(SUBSTRING(x.h, 25, 4) AS int) & 2147483647 AS r7,
       CAST(SUBSTRING(x.h, 29, 4) AS int) & 2147483647 AS r8
INTO #n
FROM nums
CROSS APPLY (SELECT HASHBYTES('SHA2_256', CONCAT('insurance-', nums.n)) AS h) AS x;

-- Customers: 2,000. About 1 in 7 changed region and risk tier once (ChangeAt).
-- Boundary cases: customer 2000 changes at exactly 2025-06-15 10:00 (dev window),
-- customer 1999 at exactly 2025-09-15 10:00 (holdout window).
IF OBJECT_ID('tempdb..#cust') IS NOT NULL DROP TABLE #cust;
SELECT n AS CustomerID,
       CAST(CONCAT(
           CHOOSE(r1 % 12 + 1, N'Aoife', N'Liam', N'Mei', N'Kenji', N'Priya', N'Omar',
                               N'Sofia', N'Lucas', N'Hana', N'Noah', N'Grace', N'Ravi'),
           N' ',
           CHOOSE(r2 % 12 + 1, N'Murphy', N'Chen', N'Tanaka', N'Sharma', N'Haddad', N'Rossi',
                               N'Silva', N'Kim', N'Walsh', N'Novak', N'Okafor', N'Lee')) AS nvarchar(100)) AS CustomerName,
       DATEADD(day, r3 % 18000, CAST('1950-01-01' AS date)) AS DateOfBirth,
       CAST(CHOOSE(r4 % 6 + 1, N'North', N'South', N'East', N'West', N'Central', N'Coastal') AS nvarchar(50)) AS Region,
       CAST(CHOOSE((r4 % 6 + 1) % 6 + 1, N'North', N'South', N'East', N'West', N'Central', N'Coastal') AS nvarchar(50)) AS OldRegion,
       CAST(CHOOSE(r5 % 3 + 1, N'Low', N'Medium', N'High') AS nvarchar(20)) AS RiskTier,
       CAST(CHOOSE((r5 % 3 + 1) % 3 + 1, N'Low', N'Medium', N'High') AS nvarchar(20)) AS OldRiskTier,
       CASE WHEN n = 2000 THEN CAST('2025-06-15T10:00:00' AS datetime2(7))
            WHEN n = 1999 THEN CAST('2025-09-15T10:00:00' AS datetime2(7))
            WHEN r6 % 7 = 0 THEN DATEADD(minute, r7 % 1008000, CAST('2024-01-01' AS datetime2(7)))
       END AS ChangeAt
INTO #cust
FROM #n
WHERE n BETWEEN 1 AND 2000;

-- Employees: 60. 1-40 are agents (sell policies), 41-60 are adjusters (handle claims).
-- About 1 in 6 moved branch once.
IF OBJECT_ID('tempdb..#emp') IS NOT NULL DROP TABLE #emp;
SELECT n - 5000 AS EmployeeID,
       CAST(CONCAT(
           CHOOSE(r1 % 10 + 1, N'Siobhan', N'Takeshi', N'Ananya', N'Diego', N'Fatima',
                               N'Conor', N'Yuki', N'Arjun', N'Elena', N'Kwame'),
           N' ',
           CHOOSE(r2 % 10 + 1, N'Byrne', N'Sato', N'Iyer', N'Garcia', N'Rahman',
                               N'Kelly', N'Mori', N'Patel', N'Costa', N'Mensah')) AS nvarchar(100)) AS FullName,
       CAST(CASE WHEN n - 5000 <= 40 THEN N'Agent' ELSE N'Adjuster' END AS nvarchar(20)) AS EmployeeRole,
       CAST(CHOOSE(r3 % 5 + 1, N'Head Office', N'North Branch', N'South Branch', N'East Branch', N'West Branch') AS nvarchar(50)) AS Branch,
       CAST(CHOOSE((r3 % 5 + 1) % 5 + 1, N'Head Office', N'North Branch', N'South Branch', N'East Branch', N'West Branch') AS nvarchar(50)) AS OldBranch,
       CASE WHEN r4 % 6 = 0 THEN DATEADD(minute, r5 % 1008000, CAST('2024-01-01' AS datetime2(7))) END AS ChangeAt
INTO #emp
FROM #n
WHERE n BETWEEN 5001 AND 5060;

-- Policies: 3,000, one year each. About 1 in 5 had a mid-term endorsement (ChangeAt)
-- that raised the coverage limit by 20% and the annual premium by 15%.
-- Boundary cases: policy 3000 endorsed at exactly 2025-06-20 09:30 (dev),
-- policy 2999 at exactly 2025-09-20 09:30 (holdout).
IF OBJECT_ID('tempdb..#pol') IS NOT NULL DROP TABLE #pol;
SELECT b.PolicyID,
       CAST(CONCAT(N'POL-', RIGHT(CONCAT('000000', b.PolicyID), 6)) AS nvarchar(20)) AS PolicyNumber,
       b.CustomerID,
       b.AgentID,
       b.ProductLine,
       b.StartDate,
       DATEADD(day, -1, DATEADD(year, 1, b.StartDate)) AS EndDate,
       l.OldLimit,
       l.Deductible,
       l.OldAnnual,
       CASE WHEN chg.ChangeAt IS NULL THEN l.OldLimit
            ELSE CAST(l.OldLimit * 1.2 AS decimal(18,2)) END AS CoverageLimit,
       CASE WHEN chg.ChangeAt IS NULL THEN l.OldAnnual
            ELSE CAST(ROUND(l.OldAnnual * 1.15, 2) AS decimal(18,2)) END AS AnnualPremium,
       DATEADD(day, -7, CAST(b.StartDate AS datetime2(7))) AS CreatedWhen,
       chg.ChangeAt,
       b.r6
INTO #pol
FROM (
    SELECT n - 10000 AS PolicyID,
           r1 % 2000 + 1 AS CustomerID,
           r2 % 40 + 1 AS AgentID,
           CAST(CHOOSE(r3 % 4 + 1, N'Motor', N'Home', N'Travel', N'Life') AS nvarchar(20)) AS ProductLine,
           CASE WHEN n - 10000 IN (2999, 3000) THEN CAST('2025-01-10' AS date)
                ELSE DATEADD(day, r4 % 1035, CAST('2023-01-01' AS date)) END AS StartDate,
           r5, r6, r7, r8
    FROM #n
    WHERE n BETWEEN 10001 AND 13000
) AS b
CROSS APPLY (
    SELECT CAST(CASE b.ProductLine
                    WHEN N'Motor'  THEN 50000  + (b.r5 % 20) * 5000
                    WHEN N'Home'   THEN 200000 + (b.r5 % 40) * 10000
                    WHEN N'Travel' THEN 10000  + (b.r5 % 10) * 1000
                    ELSE                100000 + (b.r5 % 50) * 10000
                END AS decimal(18,2)) AS OldLimit,
           CAST(CASE b.ProductLine
                    WHEN N'Motor'  THEN CHOOSE(b.r6 % 4 + 1, 250, 500, 750, 1000)
                    WHEN N'Home'   THEN CHOOSE(b.r6 % 3 + 1, 500, 1000, 2500)
                    WHEN N'Travel' THEN 100
                    ELSE 0
                END AS decimal(18,2)) AS Deductible,
           CAST(CASE b.ProductLine
                    WHEN N'Motor'  THEN 400
                    WHEN N'Home'   THEN 250
                    WHEN N'Travel' THEN 40
                    ELSE 600
                END + (b.r7 % 120000) / 100.0 AS decimal(18,2)) AS OldAnnual
) AS l
CROSS APPLY (
    SELECT CASE WHEN b.PolicyID = 3000 THEN CAST('2025-06-20T09:30:00' AS datetime2(7))
                WHEN b.PolicyID = 2999 THEN CAST('2025-09-20T09:30:00' AS datetime2(7))
                WHEN b.r8 % 5 = 0 THEN DATEADD(minute, 600 + b.r8 % 259200, CAST(b.StartDate AS datetime2(7)))
           END AS ChangeAt
) AS chg;

-- Claims: up to 1,600, each with 1 to 3 coverage lines.
-- 40% were edited after creation (status moved on from Open); those edits are what
-- the delete-and-reinsert pattern has to pick up.
IF OBJECT_ID('tempdb..#claim') IS NOT NULL DROP TABLE #claim;
SELECT c.ClaimID,
       c.PolicyID,
       p.CustomerID,
       p.ProductLine,
       p.Deductible,
       ld.LossDate,
       DATEADD(day, c.r3 % 30, ld.LossDate) AS ReportedDate,
       cr.CreatedWhen,
       CASE WHEN c.r5 % 10 < 4 THEN DATEADD(minute, c.r6 % 172800, cr.CreatedWhen)
            ELSE cr.CreatedWhen END AS LastEditedWhen,
       CAST(CASE WHEN c.r5 % 10 < 4 THEN CHOOSE(c.r7 % 3 + 1, N'Approved', N'Closed', N'Denied')
                 ELSE N'Open' END AS nvarchar(20)) AS ClaimStatus,
       CASE WHEN c.r5 % 10 >= 4 AND c.r8 % 9 = 0 THEN NULL
            ELSE 41 + c.r8 % 20 END AS AdjusterID,
       (c.r3 / 30) % 3 + 1 AS LineCount
INTO #claim
FROM (
    SELECT n - 20000 AS ClaimID, r1 % 3000 + 1 AS PolicyID, r2, r3, r4, r5, r6, r7, r8
    FROM #n
    WHERE n BETWEEN 20001 AND 21600
) AS c
JOIN #pol AS p ON p.PolicyID = c.PolicyID
CROSS APPLY (SELECT DATEADD(day, c.r2 % 365, p.StartDate) AS LossDate) AS ld
CROSS APPLY (SELECT DATEADD(minute, 480 + c.r4 % 600,
                    CAST(DATEADD(day, c.r3 % 30, ld.LossDate) AS datetime2(7))) AS CreatedWhen) AS cr
WHERE ld.LossDate <= '2025-12-15';

-- Claim lines. Old* columns hold the version as first created (status Open, nothing
-- approved or paid). The warehouse holds that old version for claims created before
-- the cutoff and edited after it.
IF OBJECT_ID('tempdb..#cl') IS NOT NULL DROP TABLE #cl;
SELECT cl.ClaimID * 10 + v.v AS ClaimLineID,
       cl.ClaimID,
       cl.PolicyID,
       cl.CustomerID,
       cl.AdjusterID,
       CAST(CASE cl.ProductLine
                WHEN N'Motor'  THEN CHOOSE(v.v, N'Vehicle Damage', N'Bodily Injury', N'Third Party Liability')
                WHEN N'Home'   THEN CHOOSE(v.v, N'Building', N'Contents', N'Liability')
                WHEN N'Travel' THEN CHOOSE(v.v, N'Medical', N'Baggage', N'Cancellation')
                ELSE                CHOOSE(v.v, N'Death Benefit', N'Accidental Death', N'Terminal Illness')
            END AS nvarchar(50)) AS CoverageType,
       cl.LossDate,
       cl.ReportedDate,
       cl.ClaimStatus,
       amt.Claimed AS ClaimedAmount,
       a.Approved AS ApprovedAmount,
       CAST(CASE cl.ClaimStatus
                WHEN N'Closed'   THEN CASE WHEN a.Approved > d.Ded THEN a.Approved - d.Ded ELSE 0 END
                WHEN N'Approved' THEN ROUND(a.Approved * 0.5, 2)
                ELSE 0
            END AS decimal(18,2)) AS PaidAmount,
       d.Ded AS DeductibleApplied,
       cl.CreatedWhen,
       cl.LastEditedWhen,
       CAST(N'Open' AS nvarchar(20)) AS OldClaimStatus,
       CAST(NULL AS decimal(18,2)) AS OldApprovedAmount,
       CAST(0 AS decimal(18,2)) AS OldPaidAmount
INTO #cl
FROM #claim AS cl
CROSS JOIN (VALUES (1), (2), (3)) AS v(v)
JOIN #n AS ln ON ln.n = 30000 + cl.ClaimID * 3 + v.v
CROSS APPLY (SELECT CAST(100 + (ln.r1 % 2500000) / 100.0 AS decimal(18,2)) AS Claimed) AS amt
CROSS APPLY (SELECT CAST(CASE WHEN v.v = 1 AND cl.Deductible < amt.Claimed THEN cl.Deductible
                              WHEN v.v = 1 THEN amt.Claimed
                              ELSE 0 END AS decimal(18,2)) AS Ded) AS d
CROSS APPLY (SELECT CAST(CASE cl.ClaimStatus
                              WHEN N'Open'   THEN NULL
                              WHEN N'Denied' THEN 0
                              ELSE ROUND(amt.Claimed * (60 + ln.r2 % 41) / 100.0, 2)
                         END AS decimal(18,2)) AS Approved) AS a
WHERE v.v <= cl.LineCount;

-- Hand-made edge cases, two per window (dev = June 2025, holdout = September 2025).
INSERT #cl (ClaimLineID, ClaimID, PolicyID, CustomerID, AdjusterID, CoverageType, LossDate, ReportedDate,
            ClaimStatus, ClaimedAmount, ApprovedAmount, PaidAmount, DeductibleApplied, CreatedWhen, LastEditedWhen,
            OldClaimStatus, OldApprovedAmount, OldPaidAmount)
VALUES
    -- edited at the exact moment customer 2000 changed version
    (90011, 9001, 3000, 2000, 41, N'Vehicle Damage', '2025-06-10', '2025-06-12', N'Open', 1234.56, NULL, 0, 250.00,
     '2025-06-15T10:00:00', '2025-06-15T10:00:00', N'Open', NULL, 0),
    -- edited at the exact moment policy 3000 was endorsed
    (90021, 9002, 3000, 2000, 42, N'Bodily Injury', '2025-06-18', '2025-06-19', N'Approved', 8000.00, 6400.00, 3200.00, 0,
     '2025-06-20T09:30:00', '2025-06-20T09:30:00', N'Open', NULL, 0),
    -- policy and customer that don't exist in the warehouse
    (90031, 9003, 999999, 999999, 43, N'Contents', '2025-06-16', '2025-06-17', N'Open', 999.99, NULL, 0, 0,
     '2025-06-18T12:00:00', '2025-06-18T12:00:00', N'Open', NULL, 0),
    -- no adjuster assigned, and a timestamp using all 7 fractional digits
    (90041, 9004, 1500, 1500, NULL, N'Medical', '2025-06-20', '2025-06-21', N'Open', 450.10, NULL, 0, 100.00,
     '2025-06-22T15:45:00.1234567', '2025-06-22T15:45:00.1234567', N'Open', NULL, 0),
    -- holdout versions of the same four cases
    (91011, 9101, 2999, 1999, 44, N'Vehicle Damage', '2025-09-10', '2025-09-12', N'Open', 2345.67, NULL, 0, 500.00,
     '2025-09-15T10:00:00', '2025-09-15T10:00:00', N'Open', NULL, 0),
    (91021, 9102, 2999, 1999, 45, N'Bodily Injury', '2025-09-18', '2025-09-19', N'Approved', 9000.00, 7200.00, 3600.00, 0,
     '2025-09-20T09:30:00', '2025-09-20T09:30:00', N'Open', NULL, 0),
    (91031, 9103, 999998, 999998, 46, N'Contents', '2025-09-16', '2025-09-17', N'Open', 888.88, NULL, 0, 0,
     '2025-09-18T12:00:00', '2025-09-18T12:00:00', N'Open', NULL, 0),
    (91041, 9104, 1501, 1501, NULL, N'Medical', '2025-09-20', '2025-09-21', N'Open', 560.20, NULL, 0, 100.00,
     '2025-09-22T15:45:00.7654321', '2025-09-22T15:45:00.7654321', N'Open', NULL, 0);

-- Premium transactions: New business, Renewal, mid-term Endorsement (dated at the exact
-- moment the policy changed) and some Cancellations (negative amounts).
-- About 1 in 12 was corrected after entry; OldGrossPremium is the wrong first version.
IF OBJECT_ID('tempdb..#prem') IS NOT NULL DROP TABLE #prem;
SELECT x.TransactionID,
       p.PolicyID,
       p.CustomerID,
       p.AgentID,
       CAST(x.TransactionType AS nvarchar(20)) AS TransactionType,
       x.TransactionDate,
       x.Gross AS GrossPremium,
       CAST(CASE p.ProductLine WHEN N'Motor' THEN 0.1250 WHEN N'Home' THEN 0.1500
                               WHEN N'Travel' THEN 0.2000 ELSE 0.0500 END AS decimal(5,4)) AS CommissionRate,
       CAST(CASE p.ProductLine WHEN N'Motor' THEN 0.0500 WHEN N'Home' THEN 0.0300
                               WHEN N'Travel' THEN 0.0200 ELSE 0.0100 END AS decimal(5,4)) AS TaxRate,
       cr.CreatedWhen,
       CASE WHEN rn.r2 % 12 = 0 THEN DATEADD(day, 1 + rn.r3 % 20, cr.CreatedWhen)
            ELSE cr.CreatedWhen END AS LastEditedWhen,
       CAST(CASE WHEN rn.r2 % 12 = 0 THEN x.Gross + 25.00 ELSE x.Gross END AS decimal(18,2)) AS OldGrossPremium
INTO #prem
FROM #pol AS p
CROSS APPLY (VALUES
    (1, p.PolicyID * 10 + 1, N'New',          p.StartDate,
        p.OldAnnual),
    (2, p.PolicyID * 10 + 2, N'Renewal',      DATEADD(year, 1, p.StartDate),
        CAST(ROUND(p.AnnualPremium * 1.03, 2) AS decimal(18,2))),
    (3, p.PolicyID * 10 + 3, N'Endorsement',  CAST(p.ChangeAt AS date),
        CAST(ROUND((p.AnnualPremium - p.OldAnnual) * DATEDIFF(day, p.ChangeAt, p.EndDate) / 365.0, 2) AS decimal(18,2))),
    (4, p.PolicyID * 10 + 4, N'Cancellation', DATEADD(day, 200 + p.r6 % 150, p.StartDate),
        CAST(-ROUND(p.AnnualPremium * DATEDIFF(day, DATEADD(day, 200 + p.r6 % 150, p.StartDate), p.EndDate) / 365.0, 2) AS decimal(18,2)))
) AS x(TypeIndex, TransactionID, TransactionType, TransactionDate, Gross)
JOIN #n AS rn ON rn.n = 40000 + p.PolicyID * 4 + x.TypeIndex
CROSS APPLY (SELECT CASE WHEN x.TypeIndex = 3 THEN p.ChangeAt
                         ELSE DATEADD(minute, 540 + rn.r1 % 480, CAST(x.TransactionDate AS datetime2(7)))
                    END AS CreatedWhen) AS cr
WHERE x.TransactionDate IS NOT NULL
  AND x.TransactionDate <= '2025-12-31'
  AND (x.TypeIndex <> 4 OR p.r6 % 15 = 0)     -- only some policies are cancelled
  AND (x.TypeIndex <> 2 OR p.r6 % 15 <> 0)    -- cancelled policies are not renewed
  AND (x.TypeIndex <> 3 OR x.TransactionDate <= p.EndDate);

-- Edge cases: an agent that doesn't exist in the warehouse, one per window.
INSERT #prem (TransactionID, PolicyID, CustomerID, AgentID, TransactionType, TransactionDate, GrossPremium,
              CommissionRate, TaxRate, CreatedWhen, LastEditedWhen, OldGrossPremium)
VALUES
    (99990001, 1200, 1200, 999, N'Endorsement', '2025-06-25', 15.50, 0.1250, 0.0500,
     '2025-06-25T11:11:11', '2025-06-25T11:11:11', 15.50),
    (99990002, 1201, 1201, 998, N'Endorsement', '2025-09-25', 17.25, 0.1250, 0.0500,
     '2025-09-25T11:11:11', '2025-09-25T11:11:11', 17.25);
GO

/* =====================================================================
   2. InsuranceOps: the source system (current state only, like an app database)
   ===================================================================== */

CREATE SCHEMA Operations;
GO

SET NOCOUNT ON;

CREATE TABLE Operations.Customers (
    CustomerID      int           NOT NULL PRIMARY KEY,
    CustomerName    nvarchar(100) NOT NULL,
    DateOfBirth     date          NOT NULL,
    Region          nvarchar(50)  NOT NULL,
    RiskTier        nvarchar(20)  NOT NULL,
    LastEditedWhen  datetime2(7)  NOT NULL
);

CREATE TABLE Operations.Employees (
    EmployeeID      int           NOT NULL PRIMARY KEY,
    FullName        nvarchar(100) NOT NULL,
    EmployeeRole    nvarchar(20)  NOT NULL,
    Branch          nvarchar(50)  NOT NULL,
    LastEditedWhen  datetime2(7)  NOT NULL
);

CREATE TABLE Operations.Policies (
    PolicyID        int           NOT NULL PRIMARY KEY,
    PolicyNumber    nvarchar(20)  NOT NULL,
    CustomerID      int           NOT NULL,
    AgentID         int           NOT NULL,
    ProductLine     nvarchar(20)  NOT NULL,
    StartDate       date          NOT NULL,
    EndDate         date          NOT NULL,
    CoverageLimit   decimal(18,2) NOT NULL,
    Deductible      decimal(18,2) NOT NULL,
    AnnualPremium   decimal(18,2) NOT NULL,
    LastEditedWhen  datetime2(7)  NOT NULL
);

CREATE TABLE Operations.ClaimLines (
    ClaimLineID       int           NOT NULL PRIMARY KEY,
    ClaimID           int           NOT NULL,
    PolicyID          int           NOT NULL,
    CustomerID        int           NOT NULL,
    AdjusterID        int           NULL,
    CoverageType      nvarchar(50)  NOT NULL,
    LossDate          date          NOT NULL,
    ReportedDate      date          NOT NULL,
    ClaimStatus       nvarchar(20)  NOT NULL,
    ClaimedAmount     decimal(18,2) NOT NULL,
    ApprovedAmount    decimal(18,2) NULL,
    PaidAmount        decimal(18,2) NOT NULL,
    DeductibleApplied decimal(18,2) NOT NULL,
    CreatedWhen       datetime2(7)  NOT NULL,
    LastEditedWhen    datetime2(7)  NOT NULL
);

CREATE TABLE Operations.PremiumTransactions (
    TransactionID   int           NOT NULL PRIMARY KEY,
    PolicyID        int           NOT NULL,
    CustomerID      int           NOT NULL,
    AgentID         int           NOT NULL,
    TransactionType nvarchar(20)  NOT NULL,
    TransactionDate date          NOT NULL,
    GrossPremium    decimal(18,2) NOT NULL,
    CommissionRate  decimal(5,4)  NOT NULL,
    TaxRate         decimal(5,4)  NOT NULL,
    CreatedWhen     datetime2(7)  NOT NULL,
    LastEditedWhen  datetime2(7)  NOT NULL
);

INSERT Operations.Customers (CustomerID, CustomerName, DateOfBirth, Region, RiskTier, LastEditedWhen)
SELECT CustomerID, CustomerName, DateOfBirth, Region, RiskTier,
       ISNULL(ChangeAt, CAST('2023-01-01' AS datetime2(7)))
FROM #cust;

INSERT Operations.Employees (EmployeeID, FullName, EmployeeRole, Branch, LastEditedWhen)
SELECT EmployeeID, FullName, EmployeeRole, Branch,
       ISNULL(ChangeAt, CAST('2023-01-01' AS datetime2(7)))
FROM #emp;

INSERT Operations.Policies (PolicyID, PolicyNumber, CustomerID, AgentID, ProductLine, StartDate, EndDate,
                           CoverageLimit, Deductible, AnnualPremium, LastEditedWhen)
SELECT PolicyID, PolicyNumber, CustomerID, AgentID, ProductLine, StartDate, EndDate,
       CoverageLimit, Deductible, AnnualPremium, ISNULL(ChangeAt, CreatedWhen)
FROM #pol;

INSERT Operations.ClaimLines (ClaimLineID, ClaimID, PolicyID, CustomerID, AdjusterID, CoverageType, LossDate,
                             ReportedDate, ClaimStatus, ClaimedAmount, ApprovedAmount, PaidAmount,
                             DeductibleApplied, CreatedWhen, LastEditedWhen)
SELECT ClaimLineID, ClaimID, PolicyID, CustomerID, AdjusterID, CoverageType, LossDate,
       ReportedDate, ClaimStatus, ClaimedAmount, ApprovedAmount, PaidAmount,
       DeductibleApplied, CreatedWhen, LastEditedWhen
FROM #cl;

INSERT Operations.PremiumTransactions (TransactionID, PolicyID, CustomerID, AgentID, TransactionType,
                                      TransactionDate, GrossPremium, CommissionRate, TaxRate,
                                      CreatedWhen, LastEditedWhen)
SELECT TransactionID, PolicyID, CustomerID, AgentID, TransactionType,
       TransactionDate, GrossPremium, CommissionRate, TaxRate, CreatedWhen, LastEditedWhen
FROM #prem;
GO

/* =====================================================================
   3. InsuranceDW: the warehouse
   ===================================================================== */

USE InsuranceDW;
GO
CREATE SCHEMA Dimension;
GO
CREATE SCHEMA Fact;
GO
CREATE SCHEMA Integration;
GO

SET NOCOUNT ON;

-- ---------- Integration: load bookkeeping ----------

CREATE TABLE Integration.Lineage (
    [Lineage Key]               int IDENTITY(1,1) NOT NULL PRIMARY KEY,
    [Data Load Started]         datetime2(7)  NOT NULL,
    [Table Name]                nvarchar(128) NOT NULL,
    [Data Load Completed]       datetime2(7)  NULL,
    [Was Successful]            bit           NOT NULL,
    [Source System Cutoff Time] datetime2(7)  NOT NULL
);

CREATE TABLE Integration.[ETL Cutoff] (
    [Table Name]  nvarchar(128) NOT NULL PRIMARY KEY,
    [Cutoff Time] datetime2(7)  NOT NULL
);

-- Staging tables: source IDs arrive filled in, warehouse Keys arrive NULL
-- (the legacy job's lookup step fills them, as in WideWorldImporters).
-- Plain tables, not memory-optimized, so they survive a SQL Server restart.

CREATE TABLE Integration.Claim_Staging (
    [Claim Staging Key]    bigint IDENTITY(1,1) NOT NULL PRIMARY KEY,
    [Policy Key]           int           NULL,
    [Customer Key]         int           NULL,
    [Adjuster Key]         int           NULL,
    [Loss Date Key]        date          NULL,
    [Reported Date Key]    date          NULL,
    [Source Claim ID]      int           NULL,
    [Source Claim Line ID] int           NULL,
    [Source Policy ID]     int           NULL,
    [Source Customer ID]   int           NULL,
    [Source Adjuster ID]   int           NULL,
    [Coverage Type]        nvarchar(50)  NULL,
    [Claim Status]         nvarchar(20)  NULL,
    [Claimed Amount]       decimal(18,2) NULL,
    [Approved Amount]      decimal(18,2) NULL,
    [Paid Amount]          decimal(18,2) NULL,
    [Deductible Applied]   decimal(18,2) NULL,
    [Last Modified When]   datetime2(7)  NULL
);

CREATE TABLE Integration.Premium_Staging (
    [Premium Staging Key]   bigint IDENTITY(1,1) NOT NULL PRIMARY KEY,
    [Policy Key]            int           NULL,
    [Customer Key]          int           NULL,
    [Agent Key]             int           NULL,
    [Transaction Date Key]  date          NULL,
    [Source Transaction ID] int           NULL,
    [Source Policy ID]      int           NULL,
    [Source Customer ID]    int           NULL,
    [Source Agent ID]       int           NULL,
    [Transaction Type]      nvarchar(20)  NULL,
    [Gross Premium]         decimal(18,2) NULL,
    [Commission Rate]       decimal(5,4)  NULL,
    [Tax Rate]              decimal(5,4)  NULL,
    [Last Modified When]    datetime2(7)  NULL
);

-- ---------- Dimensions (Type 2 history: one row per version, Valid From / Valid To) ----------

CREATE TABLE Dimension.[Date] (
    [Date]                 date         NOT NULL PRIMARY KEY,
    [Day Number]           int          NOT NULL,
    [Day]                  nvarchar(10) NOT NULL,
    [Calendar Month Number] int         NOT NULL,
    [Calendar Month Label] nvarchar(20) NOT NULL,
    [Calendar Year]        int          NOT NULL,
    [Fiscal Year]          int          NOT NULL
);

CREATE TABLE Dimension.Customer (
    [Customer Key]       int           NOT NULL PRIMARY KEY,
    [Source Customer ID] int           NOT NULL,
    [Customer]           nvarchar(100) NOT NULL,
    [Date of Birth]      date          NULL,
    [Region]             nvarchar(50)  NOT NULL,
    [Risk Tier]          nvarchar(20)  NOT NULL,
    [Valid From]         datetime2(7)  NOT NULL,
    [Valid To]           datetime2(7)  NOT NULL,
    [Lineage Key]        int           NOT NULL
);

CREATE TABLE Dimension.Employee (
    [Employee Key]       int           NOT NULL PRIMARY KEY,
    [Source Employee ID] int           NOT NULL,
    [Employee]           nvarchar(100) NOT NULL,
    [Role]               nvarchar(20)  NOT NULL,
    [Branch]             nvarchar(50)  NOT NULL,
    [Valid From]         datetime2(7)  NOT NULL,
    [Valid To]           datetime2(7)  NOT NULL,
    [Lineage Key]        int           NOT NULL
);

CREATE TABLE Dimension.Policy (
    [Policy Key]        int           NOT NULL PRIMARY KEY,
    [Source Policy ID]  int           NOT NULL,
    [Policy Number]     nvarchar(20)  NOT NULL,
    [Product Line]      nvarchar(20)  NOT NULL,
    [Coverage Limit]    decimal(18,2) NOT NULL,
    [Deductible]        decimal(18,2) NOT NULL,
    [Annual Premium]    decimal(18,2) NOT NULL,
    [Policy Start Date] date          NULL,
    [Policy End Date]   date          NULL,
    [Valid From]        datetime2(7)  NOT NULL,
    [Valid To]          datetime2(7)  NOT NULL,
    [Lineage Key]       int           NOT NULL
);

-- ---------- Facts ----------

CREATE TABLE Fact.Claim (
    [Claim Key]            bigint IDENTITY(1,1) NOT NULL PRIMARY KEY,
    [Policy Key]           int           NOT NULL,
    [Customer Key]         int           NOT NULL,
    [Adjuster Key]         int           NOT NULL,
    [Loss Date Key]        date          NOT NULL,
    [Reported Date Key]    date          NOT NULL,
    [Source Claim ID]      int           NOT NULL,
    [Source Claim Line ID] int           NOT NULL,
    [Coverage Type]        nvarchar(50)  NOT NULL,
    [Claim Status]         nvarchar(20)  NOT NULL,
    [Claimed Amount]       decimal(18,2) NOT NULL,
    [Approved Amount]      decimal(18,2) NULL,
    [Paid Amount]          decimal(18,2) NOT NULL,
    [Deductible Applied]   decimal(18,2) NOT NULL,
    [Lineage Key]          int           NOT NULL
);

CREATE TABLE Fact.Premium (
    [Premium Key]           bigint IDENTITY(1,1) NOT NULL PRIMARY KEY,
    [Policy Key]            int           NOT NULL,
    [Customer Key]          int           NOT NULL,
    [Agent Key]             int           NOT NULL,
    [Transaction Date Key]  date          NOT NULL,
    [Source Transaction ID] int           NOT NULL,
    [Transaction Type]      nvarchar(20)  NOT NULL,
    [Gross Premium]         decimal(18,2) NOT NULL,
    [Commission Amount]     decimal(18,2) NOT NULL,
    [Tax Amount]            decimal(18,2) NOT NULL,
    [Net Premium]           decimal(18,2) NOT NULL,
    [Lineage Key]           int           NOT NULL
);
GO

/* =====================================================================
   4. Load the warehouse as it stood at the 2025-06-01 cutoff
   ===================================================================== */

SET NOCOUNT ON;

-- Lineage 1-3: dimension loads (dimensions are loaded through end of 2025).
-- Lineage 4-5: fact loads, completed up to the 2025-06-01 cutoff.
INSERT Integration.Lineage ([Data Load Started], [Table Name], [Data Load Completed], [Was Successful], [Source System Cutoff Time])
VALUES ('2025-12-31T23:00:00', N'Customer', '2025-12-31T23:05:00', 1, '2025-12-31T23:00:00'),
       ('2025-12-31T23:00:00', N'Employee', '2025-12-31T23:05:00', 1, '2025-12-31T23:00:00'),
       ('2025-12-31T23:00:00', N'Policy',   '2025-12-31T23:05:00', 1, '2025-12-31T23:00:00'),
       ('2025-06-01T02:00:00', N'Claim',    '2025-06-01T02:10:00', 1, '2025-06-01T00:00:00'),
       ('2025-06-01T02:00:00', N'Premium',  '2025-06-01T02:10:00', 1, '2025-06-01T00:00:00');

INSERT Integration.[ETL Cutoff] ([Table Name], [Cutoff Time])
VALUES (N'Customer', '2025-12-31T23:00:00'),
       (N'Employee', '2025-12-31T23:00:00'),
       (N'Policy',   '2025-12-31T23:00:00'),
       (N'Claim',    '2025-06-01T00:00:00'),
       (N'Premium',  '2025-06-01T00:00:00');

-- Date dimension: 2023-01-01 to 2026-12-31. Fiscal year starts 1 April.
INSERT Dimension.[Date] ([Date], [Day Number], [Day], [Calendar Month Number], [Calendar Month Label],
                         [Calendar Year], [Fiscal Year])
SELECT d,
       DAY(d),
       CAST(DATENAME(weekday, d) AS nvarchar(10)),
       MONTH(d),
       CAST(CONCAT(LEFT(DATENAME(month, d), 3), N' ', YEAR(d)) AS nvarchar(20)),
       YEAR(d),
       CASE WHEN MONTH(d) >= 4 THEN YEAR(d) + 1 ELSE YEAR(d) END
FROM (SELECT DATEADD(day, n - 1, CAST('2023-01-01' AS date)) AS d FROM #n WHERE n <= 1461) AS dates;

-- Key 0 is the "Unknown" member in every dimension, as in WideWorldImporters.
INSERT Dimension.Customer VALUES
    (0, 0, N'Unknown', NULL, N'N/A', N'N/A', '2013-01-01', '9999-12-31T23:59:59.9999999', 0);
INSERT Dimension.Employee VALUES
    (0, 0, N'Unknown', N'N/A', N'N/A', '2013-01-01', '9999-12-31T23:59:59.9999999', 0);
INSERT Dimension.Policy VALUES
    (0, 0, N'N/A', N'N/A', 0, 0, 0, NULL, NULL, '2013-01-01', '9999-12-31T23:59:59.9999999', 0);

INSERT Dimension.Customer ([Customer Key], [Source Customer ID], [Customer], [Date of Birth], [Region],
                           [Risk Tier], [Valid From], [Valid To], [Lineage Key])
SELECT ROW_NUMBER() OVER (ORDER BY v.CustomerID, v.ValidFrom),
       v.CustomerID, v.CustomerName, v.DateOfBirth, v.Region, v.RiskTier, v.ValidFrom, v.ValidTo, 1
FROM (
    SELECT CustomerID, CustomerName, DateOfBirth,
           CASE WHEN ChangeAt IS NULL THEN Region ELSE OldRegion END AS Region,
           CASE WHEN ChangeAt IS NULL THEN RiskTier ELSE OldRiskTier END AS RiskTier,
           CAST('2023-01-01' AS datetime2(7)) AS ValidFrom,
           ISNULL(ChangeAt, CAST('9999-12-31T23:59:59.9999999' AS datetime2(7))) AS ValidTo
    FROM #cust
    UNION ALL
    SELECT CustomerID, CustomerName, DateOfBirth, Region, RiskTier,
           ChangeAt, CAST('9999-12-31T23:59:59.9999999' AS datetime2(7))
    FROM #cust
    WHERE ChangeAt IS NOT NULL
) AS v;

INSERT Dimension.Employee ([Employee Key], [Source Employee ID], [Employee], [Role], [Branch],
                           [Valid From], [Valid To], [Lineage Key])
SELECT ROW_NUMBER() OVER (ORDER BY v.EmployeeID, v.ValidFrom),
       v.EmployeeID, v.FullName, v.EmployeeRole, v.Branch, v.ValidFrom, v.ValidTo, 2
FROM (
    SELECT EmployeeID, FullName, EmployeeRole,
           CASE WHEN ChangeAt IS NULL THEN Branch ELSE OldBranch END AS Branch,
           CAST('2023-01-01' AS datetime2(7)) AS ValidFrom,
           ISNULL(ChangeAt, CAST('9999-12-31T23:59:59.9999999' AS datetime2(7))) AS ValidTo
    FROM #emp
    UNION ALL
    SELECT EmployeeID, FullName, EmployeeRole, Branch,
           ChangeAt, CAST('9999-12-31T23:59:59.9999999' AS datetime2(7))
    FROM #emp
    WHERE ChangeAt IS NOT NULL
) AS v;

INSERT Dimension.Policy ([Policy Key], [Source Policy ID], [Policy Number], [Product Line], [Coverage Limit],
                         [Deductible], [Annual Premium], [Policy Start Date], [Policy End Date],
                         [Valid From], [Valid To], [Lineage Key])
SELECT ROW_NUMBER() OVER (ORDER BY v.PolicyID, v.ValidFrom),
       v.PolicyID, v.PolicyNumber, v.ProductLine, v.CoverageLimit, v.Deductible, v.AnnualPremium,
       v.StartDate, v.EndDate, v.ValidFrom, v.ValidTo, 3
FROM (
    SELECT PolicyID, PolicyNumber, ProductLine, OldLimit AS CoverageLimit, Deductible,
           OldAnnual AS AnnualPremium, StartDate, EndDate,
           CreatedWhen AS ValidFrom,
           ISNULL(ChangeAt, CAST('9999-12-31T23:59:59.9999999' AS datetime2(7))) AS ValidTo
    FROM #pol
    UNION ALL
    SELECT PolicyID, PolicyNumber, ProductLine, CoverageLimit, Deductible,
           AnnualPremium, StartDate, EndDate,
           ChangeAt, CAST('9999-12-31T23:59:59.9999999' AS datetime2(7))
    FROM #pol
    WHERE ChangeAt IS NOT NULL
) AS v;

-- Fact.Claim at the cutoff: lines last edited by the cutoff in their current version,
-- plus lines created by the cutoff but edited later in their OLD version.
-- Keys are looked up as of each row's timestamp; anything not found becomes 0.
INSERT Fact.Claim ([Policy Key], [Customer Key], [Adjuster Key], [Loss Date Key], [Reported Date Key],
                   [Source Claim ID], [Source Claim Line ID], [Coverage Type], [Claim Status],
                   [Claimed Amount], [Approved Amount], [Paid Amount], [Deductible Applied], [Lineage Key])
SELECT ISNULL(p.[Policy Key], 0), ISNULL(c.[Customer Key], 0), ISNULL(e.[Employee Key], 0),
       x.LossDate, x.ReportedDate, x.ClaimID, x.ClaimLineID, x.CoverageType, x.ClaimStatus,
       x.ClaimedAmount, x.ApprovedAmount, x.PaidAmount, x.DeductibleApplied, 4
FROM (
    SELECT ClaimLineID, ClaimID, PolicyID, CustomerID, AdjusterID, CoverageType, LossDate, ReportedDate,
           ClaimStatus, ClaimedAmount, ApprovedAmount, PaidAmount, DeductibleApplied,
           LastEditedWhen AS AsOf
    FROM #cl
    WHERE LastEditedWhen <= '2025-06-01T00:00:00'
    UNION ALL
    SELECT ClaimLineID, ClaimID, PolicyID, CustomerID, AdjusterID, CoverageType, LossDate, ReportedDate,
           OldClaimStatus, ClaimedAmount, OldApprovedAmount, OldPaidAmount, DeductibleApplied,
           CreatedWhen
    FROM #cl
    WHERE CreatedWhen <= '2025-06-01T00:00:00' AND LastEditedWhen > '2025-06-01T00:00:00'
) AS x
OUTER APPLY (SELECT TOP (1) d.[Policy Key] FROM Dimension.Policy AS d
             WHERE d.[Source Policy ID] = x.PolicyID AND x.AsOf > d.[Valid From] AND x.AsOf <= d.[Valid To]
             ORDER BY d.[Valid From]) AS p
OUTER APPLY (SELECT TOP (1) d.[Customer Key] FROM Dimension.Customer AS d
             WHERE d.[Source Customer ID] = x.CustomerID AND x.AsOf > d.[Valid From] AND x.AsOf <= d.[Valid To]
             ORDER BY d.[Valid From]) AS c
OUTER APPLY (SELECT TOP (1) d.[Employee Key] FROM Dimension.Employee AS d
             WHERE d.[Source Employee ID] = x.AdjusterID AND x.AsOf > d.[Valid From] AND x.AsOf <= d.[Valid To]
             ORDER BY d.[Valid From]) AS e
ORDER BY x.ClaimLineID;

-- Fact.Premium at the cutoff, same rule. Seed amounts use:
--   Commission = ROUND(Gross * Commission Rate, 2), Tax = ROUND(Gross * Tax Rate, 2),
--   Net = Gross - Commission
INSERT Fact.Premium ([Policy Key], [Customer Key], [Agent Key], [Transaction Date Key], [Source Transaction ID],
                     [Transaction Type], [Gross Premium], [Commission Amount], [Tax Amount], [Net Premium],
                     [Lineage Key])
SELECT ISNULL(p.[Policy Key], 0), ISNULL(c.[Customer Key], 0), ISNULL(e.[Employee Key], 0),
       x.TransactionDate, x.TransactionID, x.TransactionType, x.Gross,
       CAST(ROUND(x.Gross * x.CommissionRate, 2) AS decimal(18,2)),
       CAST(ROUND(x.Gross * x.TaxRate, 2) AS decimal(18,2)),
       CAST(x.Gross - ROUND(x.Gross * x.CommissionRate, 2) AS decimal(18,2)),
       5
FROM (
    SELECT TransactionID, PolicyID, CustomerID, AgentID, TransactionType, TransactionDate,
           GrossPremium AS Gross, CommissionRate, TaxRate, LastEditedWhen AS AsOf
    FROM #prem
    WHERE LastEditedWhen <= '2025-06-01T00:00:00'
    UNION ALL
    SELECT TransactionID, PolicyID, CustomerID, AgentID, TransactionType, TransactionDate,
           OldGrossPremium, CommissionRate, TaxRate, CreatedWhen
    FROM #prem
    WHERE CreatedWhen <= '2025-06-01T00:00:00' AND LastEditedWhen > '2025-06-01T00:00:00'
) AS x
OUTER APPLY (SELECT TOP (1) d.[Policy Key] FROM Dimension.Policy AS d
             WHERE d.[Source Policy ID] = x.PolicyID AND x.AsOf > d.[Valid From] AND x.AsOf <= d.[Valid To]
             ORDER BY d.[Valid From]) AS p
OUTER APPLY (SELECT TOP (1) d.[Customer Key] FROM Dimension.Customer AS d
             WHERE d.[Source Customer ID] = x.CustomerID AND x.AsOf > d.[Valid From] AND x.AsOf <= d.[Valid To]
             ORDER BY d.[Valid From]) AS c
OUTER APPLY (SELECT TOP (1) d.[Employee Key] FROM Dimension.Employee AS d
             WHERE d.[Source Employee ID] = x.AgentID AND x.AsOf > d.[Valid From] AND x.AsOf <= d.[Valid To]
             ORDER BY d.[Valid From]) AS e
ORDER BY x.TransactionID;
GO

-- Foreign keys from facts to dimensions, as in WideWorldImporters.
ALTER TABLE Fact.Claim ADD
    CONSTRAINT FK_Fact_Claim_Policy     FOREIGN KEY ([Policy Key])        REFERENCES Dimension.Policy ([Policy Key]),
    CONSTRAINT FK_Fact_Claim_Customer   FOREIGN KEY ([Customer Key])      REFERENCES Dimension.Customer ([Customer Key]),
    CONSTRAINT FK_Fact_Claim_Adjuster   FOREIGN KEY ([Adjuster Key])      REFERENCES Dimension.Employee ([Employee Key]),
    CONSTRAINT FK_Fact_Claim_LossDate   FOREIGN KEY ([Loss Date Key])     REFERENCES Dimension.[Date] ([Date]),
    CONSTRAINT FK_Fact_Claim_ReportDate FOREIGN KEY ([Reported Date Key]) REFERENCES Dimension.[Date] ([Date]);

ALTER TABLE Fact.Premium ADD
    CONSTRAINT FK_Fact_Premium_Policy   FOREIGN KEY ([Policy Key])           REFERENCES Dimension.Policy ([Policy Key]),
    CONSTRAINT FK_Fact_Premium_Customer FOREIGN KEY ([Customer Key])         REFERENCES Dimension.Customer ([Customer Key]),
    CONSTRAINT FK_Fact_Premium_Agent    FOREIGN KEY ([Agent Key])            REFERENCES Dimension.Employee ([Employee Key]),
    CONSTRAINT FK_Fact_Premium_Date     FOREIGN KEY ([Transaction Date Key]) REFERENCES Dimension.[Date] ([Date]);
GO

/* =====================================================================
   5. Summary
   ===================================================================== */

SELECT t.[Table], t.[Rows]
FROM (
    SELECT 1 AS SortOrder, N'InsuranceOps Operations.Customers' AS [Table], COUNT(*) AS [Rows] FROM InsuranceOps.Operations.Customers
    UNION ALL SELECT 2, N'InsuranceOps Operations.Employees', COUNT(*) FROM InsuranceOps.Operations.Employees
    UNION ALL SELECT 3, N'InsuranceOps Operations.Policies', COUNT(*) FROM InsuranceOps.Operations.Policies
    UNION ALL SELECT 4, N'InsuranceOps Operations.ClaimLines', COUNT(*) FROM InsuranceOps.Operations.ClaimLines
    UNION ALL SELECT 5, N'InsuranceOps Operations.PremiumTransactions', COUNT(*) FROM InsuranceOps.Operations.PremiumTransactions
    UNION ALL SELECT 6, N'InsuranceDW Dimension.Date', COUNT(*) FROM Dimension.[Date]
    UNION ALL SELECT 7, N'InsuranceDW Dimension.Customer', COUNT(*) FROM Dimension.Customer
    UNION ALL SELECT 8, N'InsuranceDW Dimension.Employee', COUNT(*) FROM Dimension.Employee
    UNION ALL SELECT 9, N'InsuranceDW Dimension.Policy', COUNT(*) FROM Dimension.Policy
    UNION ALL SELECT 10, N'InsuranceDW Fact.Claim', COUNT(*) FROM Fact.Claim
    UNION ALL SELECT 11, N'InsuranceDW Fact.Premium', COUNT(*) FROM Fact.Premium
    UNION ALL SELECT 12, N'Claim lines in dev window', COUNT(*) FROM InsuranceOps.Operations.ClaimLines
              WHERE LastEditedWhen > '2025-06-01' AND LastEditedWhen <= '2025-07-01'
    UNION ALL SELECT 13, N'Claim lines in holdout window', COUNT(*) FROM InsuranceOps.Operations.ClaimLines
              WHERE LastEditedWhen > '2025-09-01' AND LastEditedWhen <= '2025-10-01'
    UNION ALL SELECT 14, N'Premium transactions in dev window', COUNT(*) FROM InsuranceOps.Operations.PremiumTransactions
              WHERE LastEditedWhen > '2025-06-01' AND LastEditedWhen <= '2025-07-01'
    UNION ALL SELECT 15, N'Premium transactions in holdout window', COUNT(*) FROM InsuranceOps.Operations.PremiumTransactions
              WHERE LastEditedWhen > '2025-09-01' AND LastEditedWhen <= '2025-10-01'
) AS t
ORDER BY t.SortOrder;
GO

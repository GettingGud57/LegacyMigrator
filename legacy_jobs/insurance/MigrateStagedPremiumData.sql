CREATE PROCEDURE Integration.MigrateStagedPremiumData
WITH EXECUTE AS OWNER
AS
BEGIN
    SET NOCOUNT ON;
    SET XACT_ABORT ON;

    BEGIN TRAN;

    DECLARE @LineageKey int = (SELECT TOP(1) [Lineage Key]
                               FROM Integration.Lineage
                               WHERE [Table Name] = N'Premium'
                               AND [Data Load Completed] IS NULL
                               ORDER BY [Lineage Key] DESC);

    UPDATE s
        SET s.[Policy Key] = COALESCE((SELECT TOP(1) p.[Policy Key]
                                       FROM Dimension.Policy AS p
                                       WHERE p.[Source Policy ID] = s.[Source Policy ID]
                                       AND s.[Last Modified When] > p.[Valid From]
                                       AND s.[Last Modified When] <= p.[Valid To]
                                       ORDER BY p.[Valid From]), 0),
            s.[Customer Key] = COALESCE((SELECT TOP(1) c.[Customer Key]
                                         FROM Dimension.Customer AS c
                                         WHERE c.[Source Customer ID] = s.[Source Customer ID]
                                         AND s.[Last Modified When] > c.[Valid From]
                                         AND s.[Last Modified When] <= c.[Valid To]
                                         ORDER BY c.[Valid From]), 0),
            s.[Agent Key] = COALESCE((SELECT TOP(1) e.[Employee Key]
                                      FROM Dimension.Employee AS e
                                      WHERE e.[Source Employee ID] = s.[Source Agent ID]
                                      AND s.[Last Modified When] > e.[Valid From]
                                      AND s.[Last Modified When] <= e.[Valid To]
                                      ORDER BY e.[Valid From]), 0)
    FROM Integration.Premium_Staging AS s;

    DELETE p
    FROM Fact.Premium AS p
    WHERE p.[Source Transaction ID] IN (SELECT [Source Transaction ID] FROM Integration.Premium_Staging);

    INSERT Fact.Premium
        ([Policy Key], [Customer Key], [Agent Key], [Transaction Date Key], [Source Transaction ID],
         [Transaction Type], [Gross Premium], [Commission Amount], [Tax Amount], [Net Premium], [Lineage Key])
    SELECT [Policy Key], [Customer Key], [Agent Key], [Transaction Date Key], [Source Transaction ID],
           [Transaction Type], [Gross Premium],
           CAST(ROUND([Gross Premium] * [Commission Rate], 2) AS decimal(18,2)),
           CAST(ROUND([Gross Premium] * [Tax Rate], 2) AS decimal(18,2)),
           CAST([Gross Premium] - ROUND([Gross Premium] * [Commission Rate], 2) AS decimal(18,2)),
           @LineageKey
    FROM Integration.Premium_Staging;

    UPDATE Integration.Lineage
        SET [Data Load Completed] = SYSDATETIME(),
            [Was Successful] = 1
    WHERE [Lineage Key] = @LineageKey;

    UPDATE Integration.[ETL Cutoff]
        SET [Cutoff Time] = (SELECT [Source System Cutoff Time]
                             FROM Integration.Lineage
                             WHERE [Lineage Key] = @LineageKey)
    FROM Integration.[ETL Cutoff]
    WHERE [Table Name] = N'Premium';

    COMMIT;

    RETURN 0;
END;

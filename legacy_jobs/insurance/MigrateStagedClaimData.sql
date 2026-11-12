CREATE PROCEDURE Integration.MigrateStagedClaimData
WITH EXECUTE AS OWNER
AS
BEGIN
    SET NOCOUNT ON;
    SET XACT_ABORT ON;

    BEGIN TRAN;

    DECLARE @LineageKey int = (SELECT TOP(1) [Lineage Key]
                               FROM Integration.Lineage
                               WHERE [Table Name] = N'Claim'
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
            s.[Adjuster Key] = COALESCE((SELECT TOP(1) e.[Employee Key]
                                         FROM Dimension.Employee AS e
                                         WHERE e.[Source Employee ID] = s.[Source Adjuster ID]
                                         AND s.[Last Modified When] > e.[Valid From]
                                         AND s.[Last Modified When] <= e.[Valid To]
                                         ORDER BY e.[Valid From]), 0)
    FROM Integration.Claim_Staging AS s;

    DELETE c
    FROM Fact.Claim AS c
    WHERE c.[Source Claim ID] IN (SELECT [Source Claim ID] FROM Integration.Claim_Staging);

    INSERT Fact.Claim
        ([Policy Key], [Customer Key], [Adjuster Key], [Loss Date Key], [Reported Date Key],
         [Source Claim ID], [Source Claim Line ID], [Coverage Type], [Claim Status],
         [Claimed Amount], [Approved Amount], [Paid Amount], [Deductible Applied], [Lineage Key])
    SELECT [Policy Key], [Customer Key], [Adjuster Key], [Loss Date Key], [Reported Date Key],
           [Source Claim ID], [Source Claim Line ID], [Coverage Type], [Claim Status],
           [Claimed Amount], [Approved Amount], [Paid Amount], [Deductible Applied], @LineageKey
    FROM Integration.Claim_Staging;

    UPDATE Integration.Lineage
        SET [Data Load Completed] = SYSDATETIME(),
            [Was Successful] = 1
    WHERE [Lineage Key] = @LineageKey;

    UPDATE Integration.[ETL Cutoff]
        SET [Cutoff Time] = (SELECT [Source System Cutoff Time]
                             FROM Integration.Lineage
                             WHERE [Lineage Key] = @LineageKey)
    FROM Integration.[ETL Cutoff]
    WHERE [Table Name] = N'Claim';

    COMMIT;

    RETURN 0;
END;

USE TechRetail_OLTP;
GO

SET NOCOUNT ON;
SET XACT_ABORT ON;

IF SUSER_ID(N'retail_loader') IS NULL
    THROW 50002, N'Crear primero el login retail_loader mediante la conexión administradora.', 1;

IF SUSER_ID(N'retail_reader') IS NULL
    THROW 50003, N'Crear primero el login retail_reader mediante la conexión administradora.', 1;

BEGIN TRY
    BEGIN TRANSACTION;

    IF USER_ID(N'retail_loader') IS NULL
        CREATE USER retail_loader FOR LOGIN retail_loader;

    IF USER_ID(N'retail_reader') IS NULL
        CREATE USER retail_reader FOR LOGIN retail_reader;

    GRANT SELECT, INSERT, UPDATE ON OBJECT::dbo.categories TO retail_loader;
    GRANT SELECT, INSERT, UPDATE ON OBJECT::dbo.products TO retail_loader;
    GRANT SELECT, INSERT, UPDATE ON OBJECT::dbo.customers TO retail_loader;
    GRANT SELECT, INSERT, UPDATE ON OBJECT::dbo.orders TO retail_loader;
    GRANT SELECT, INSERT, UPDATE ON OBJECT::dbo.order_items TO retail_loader;

    GRANT SELECT ON OBJECT::dbo.categories TO retail_reader;
    GRANT SELECT ON OBJECT::dbo.products TO retail_reader;
    GRANT SELECT ON OBJECT::dbo.customers TO retail_reader;
    GRANT SELECT ON OBJECT::dbo.orders TO retail_reader;
    GRANT SELECT ON OBJECT::dbo.order_items TO retail_reader;

    COMMIT TRANSACTION;
END TRY
BEGIN CATCH
    IF XACT_STATE() <> 0
        ROLLBACK TRANSACTION;

    THROW;
END CATCH;
GO

USE master;
GO

SET NOCOUNT ON;

IF DB_ID(N'TechRetail_OLTP') IS NOT NULL
BEGIN
    THROW 50001, N'TechRetail_OLTP ya existe. Revisar antes de continuar.', 1;
END;
GO

CREATE DATABASE TechRetail_OLTP;
GO

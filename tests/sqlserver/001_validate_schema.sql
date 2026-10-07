USE TechRetail_OLTP;
GO

SET NOCOUNT ON;

SELECT
    t.name AS TableName,
    kc.name AS ConstraintName,
    kc.type_desc AS ConstraintType
FROM sys.key_constraints AS kc
JOIN sys.tables AS t ON t.object_id = kc.parent_object_id
WHERE t.schema_id = SCHEMA_ID(N'dbo')
ORDER BY t.name, kc.type_desc;

SELECT
    t.name AS TableName,
    fk.name AS ForeignKeyName,
    OBJECT_NAME(fk.referenced_object_id) AS ReferencedTable,
    fk.is_disabled AS IsDisabled,
    fk.is_not_trusted AS IsNotTrusted,
    fk.delete_referential_action_desc AS DeleteAction
FROM sys.foreign_keys AS fk
JOIN sys.tables AS t ON t.object_id = fk.parent_object_id
WHERE t.schema_id = SCHEMA_ID(N'dbo')
ORDER BY t.name, fk.name;

SELECT
    t.name AS TableName,
    cc.name AS CheckName,
    cc.is_disabled AS IsDisabled,
    cc.is_not_trusted AS IsNotTrusted,
    cc.definition AS CheckDefinition
FROM sys.check_constraints AS cc
JOIN sys.tables AS t ON t.object_id = cc.parent_object_id
WHERE t.schema_id = SCHEMA_ID(N'dbo')
ORDER BY t.name, cc.name;

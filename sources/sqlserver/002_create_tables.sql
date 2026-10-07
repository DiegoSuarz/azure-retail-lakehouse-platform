USE TechRetail_OLTP;
GO

SET NOCOUNT ON;
SET XACT_ABORT ON;

BEGIN TRY
    BEGIN TRANSACTION;

    CREATE TABLE dbo.categories
    (
        category_id int NOT NULL,
        category_name nvarchar(100) NOT NULL,
        created_at datetime2(3) NOT NULL,
        updated_at datetime2(3) NOT NULL,

        CONSTRAINT PK_categories PRIMARY KEY (category_id),
        CONSTRAINT UQ_categories_name UNIQUE (category_name),
        CONSTRAINT CK_categories_id CHECK (category_id > 0),
        CONSTRAINT CK_categories_dates CHECK (updated_at >= created_at)
    );

    CREATE TABLE dbo.products
    (
        product_id int NOT NULL,
        category_id int NOT NULL,
        sku varchar(40) NOT NULL,
        product_name nvarchar(200) NOT NULL,
        brand nvarchar(100) NOT NULL,
        list_price decimal(18,2) NOT NULL,
        is_active bit NOT NULL,
        created_at datetime2(3) NOT NULL,
        updated_at datetime2(3) NOT NULL,

        CONSTRAINT PK_products PRIMARY KEY (product_id),
        CONSTRAINT UQ_products_sku UNIQUE (sku),
        CONSTRAINT FK_products_categories FOREIGN KEY (category_id)
            REFERENCES dbo.categories (category_id),
        CONSTRAINT CK_products_id CHECK (product_id > 0),
        CONSTRAINT CK_products_price CHECK (list_price > 0),
        CONSTRAINT CK_products_dates CHECK (updated_at >= created_at)
    );

    CREATE TABLE dbo.customers
    (
        customer_id int NOT NULL,
        first_name nvarchar(100) NOT NULL,
        last_name nvarchar(100) NOT NULL,
        email varchar(254) NOT NULL,
        city nvarchar(100) NOT NULL,
        region nvarchar(100) NOT NULL,
        is_active bit NOT NULL,
        created_at datetime2(3) NOT NULL,
        updated_at datetime2(3) NOT NULL,

        CONSTRAINT PK_customers PRIMARY KEY (customer_id),
        CONSTRAINT UQ_customers_email UNIQUE (email),
        CONSTRAINT CK_customers_id CHECK (customer_id > 0),
        CONSTRAINT CK_customers_dates CHECK (updated_at >= created_at)
    );

    CREATE TABLE dbo.orders
    (
        order_id int NOT NULL,
        customer_id int NOT NULL,
        order_date datetime2(3) NOT NULL,
        status varchar(20) NOT NULL,
        currency_code char(3) NOT NULL,
        created_at datetime2(3) NOT NULL,
        updated_at datetime2(3) NOT NULL,

        CONSTRAINT PK_orders PRIMARY KEY (order_id),
        CONSTRAINT FK_orders_customers FOREIGN KEY (customer_id)
            REFERENCES dbo.customers (customer_id),
        CONSTRAINT CK_orders_id CHECK (order_id > 0),
        CONSTRAINT CK_orders_status
            CHECK (status IN ('pending', 'confirmed', 'cancelled')),
        CONSTRAINT CK_orders_currency CHECK (currency_code = 'PEN'),
        CONSTRAINT CK_orders_dates CHECK (updated_at >= created_at)
    );

    CREATE TABLE dbo.order_items
    (
        order_id int NOT NULL,
        line_number int NOT NULL,
        product_id int NOT NULL,
        quantity int NOT NULL,
        unit_price decimal(18,2) NOT NULL,
        discount_amount decimal(18,2) NOT NULL,
        created_at datetime2(3) NOT NULL,
        updated_at datetime2(3) NOT NULL,

        CONSTRAINT PK_order_items PRIMARY KEY (order_id, line_number),
        CONSTRAINT FK_order_items_orders FOREIGN KEY (order_id)
            REFERENCES dbo.orders (order_id),
        CONSTRAINT FK_order_items_products FOREIGN KEY (product_id)
            REFERENCES dbo.products (product_id),
        CONSTRAINT CK_order_items_line CHECK (line_number > 0),
        CONSTRAINT CK_order_items_quantity CHECK (quantity > 0),
        CONSTRAINT CK_order_items_price CHECK (unit_price > 0),
        CONSTRAINT CK_order_items_discount CHECK
        (
            discount_amount >= 0
            AND discount_amount <= quantity * unit_price
        ),
        CONSTRAINT CK_order_items_dates CHECK (updated_at >= created_at)
    );

    COMMIT TRANSACTION;
END TRY
BEGIN CATCH
    IF XACT_STATE() <> 0
        ROLLBACK TRANSACTION;

    THROW;
END CATCH;
GO

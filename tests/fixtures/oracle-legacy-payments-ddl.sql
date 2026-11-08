-- =============================================================================
-- EdgeForge E2E Demo Pack - Legacy Payments DDL
-- Leading comments intentionally precede CREATE TABLE statements.
-- =============================================================================

-- CUSTOMER master table
CREATE TABLE CUSTOMER (
    CUSTOMER_ID         VARCHAR2(36)    NOT NULL,
    COUNTRY_CODE        CHAR(2)         NOT NULL,
    KYC_STATUS          VARCHAR2(20)    NOT NULL,
    CREATED_AT          TIMESTAMP       NOT NULL,
    CONSTRAINT PK_CUSTOMER PRIMARY KEY (CUSTOMER_ID)
);

COMMENT ON COLUMN CUSTOMER.CUSTOMER_ID  IS 'UUID primary key assigned at account creation';
COMMENT ON COLUMN CUSTOMER.COUNTRY_CODE IS 'ISO 3166-1 alpha-2 country code';

CREATE INDEX IDX_CUSTOMER_KYC ON CUSTOMER (KYC_STATUS);

-- ACCOUNT master table
CREATE TABLE ACCOUNT (
    ACCOUNT_ID          VARCHAR2(36)    NOT NULL,
    CUSTOMER_ID         VARCHAR2(36)    NOT NULL,
    BALANCE_MINOR       NUMBER(18,0)    NOT NULL, -- stored in minor currency units
    SORT_CODE           CHAR(8),
    OPENED_DATE         DATE            NOT NULL,
    CONSTRAINT FK_ACCOUNT_CUSTOMER FOREIGN KEY (CUSTOMER_ID)
        REFERENCES CUSTOMER (CUSTOMER_ID)
);

COMMENT ON COLUMN ACCOUNT.BALANCE_MINOR IS 'Account balance in minor currency units';

-- PAYMENT_ORDER table
CREATE TABLE PAYMENT_ORDER (
    PAYMENT_ORDER_ID    VARCHAR2(36)    NOT NULL,
    DEBTOR_ACCOUNT_ID   VARCHAR2(36)    NOT NULL,
    AMOUNT_MINOR        NUMBER(18,0)    NOT NULL,
    CURRENCY_CODE       CHAR(3)         NOT NULL,
    SUBMITTED_AT        TIMESTAMP       NOT NULL,
    CONSTRAINT PK_PAYMENT_ORDER PRIMARY KEY (PAYMENT_ORDER_ID)
);

-- PAYMENT_LIMIT table
CREATE TABLE PAYMENT_LIMIT (
    LIMIT_ID             VARCHAR2(36)    NOT NULL,
    ACCOUNT_ID           VARCHAR2(36)    NOT NULL,
    DAILY_LIMIT_MINOR    NUMBER(18,0)    NOT NULL,
    SINGLE_TXN_MAX_MINOR NUMBER(18,0)    NOT NULL,
    EFFECTIVE_FROM       DATE            NOT NULL,
    CONSTRAINT PK_PAYMENT_LIMIT PRIMARY KEY (LIMIT_ID)
);

COMMENT ON COLUMN PAYMENT_LIMIT.SINGLE_TXN_MAX_MINOR IS 'Maximum single transaction amount';

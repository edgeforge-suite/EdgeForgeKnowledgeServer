CREATE TABLE accounts (
    -- Primary account identifier
    account_id VARCHAR(12) NOT NULL,
    owner_id INTEGER,
    available_balance DECIMAL(18, 2) COMMENT 'Available balance after memo activity',
    status VARCHAR(20) -- Lifecycle state
);

ALTER TABLE accounts ADD COLUMN archived_at TIMESTAMP;

CREATE TABLE users (
    user_id INTEGER NOT NULL,
    email VARCHAR(120),
    display_name VARCHAR(80)
);

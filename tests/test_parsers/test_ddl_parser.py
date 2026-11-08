from pathlib import Path

from knowledge_server.parsers.ddl_parser import parse_ddl


def test_ddl_parser_extracts_columns_from_single_create_table(tmp_path: Path) -> None:
    ddl = tmp_path / "single.sql"
    ddl.write_text(
        "\n".join(
            [
                "CREATE TABLE ledger_entries (",
                "    entry_id INTEGER NOT NULL,",
                "    account_code VARCHAR(32),",
                "    amount DECIMAL(12, 2)",
                ");",
            ]
        ),
        encoding="utf-8",
    )

    results = parse_ddl(ddl)

    assert len(results) == 1
    assert results[0].entity_name == "ledger_entries"
    assert [field.name for field in results[0].fields] == ["entry_id", "account_code", "amount"]
    assert results[0].fields[0].nullable is False
    assert results[0].fields[1].length == 32
    assert results[0].fields[2].precision == 12
    assert results[0].fields[2].scale == 2


def test_ddl_parser_handles_multi_statement_files() -> None:
    results = parse_ddl(Path("tests/fixtures/sample-schema.sql"))

    assert [result.entity_name for result in results] == ["accounts", "users"]
    assert [field.name for field in results[0].fields] == [
        "account_id",
        "owner_id",
        "available_balance",
        "status",
    ]
    assert [field.name for field in results[1].fields] == ["user_id", "email", "display_name"]


def test_ddl_parser_skips_unsupported_statements_without_error(tmp_path: Path) -> None:
    ddl = tmp_path / "unsupported.sql"
    ddl.write_text(
        "\n".join(
            [
                "ALTER TABLE accounts ADD COLUMN archived_at TIMESTAMP;",
                "INSERT INTO accounts(account_id) VALUES (1);",
                "CREATE TABLE audit_log (",
                "    audit_id INTEGER,",
                "    event_type VARCHAR(40)",
                ");",
            ]
        ),
        encoding="utf-8",
    )

    results = parse_ddl(ddl)

    assert len(results) == 1
    assert results[0].entity_name == "audit_log"


def test_ddl_parser_captures_comments_and_source_lines() -> None:
    accounts = parse_ddl(Path("tests/fixtures/sample-schema.sql"))[0]
    fields = {field.name: field for field in accounts.fields}

    assert fields["account_id"].description == "Primary account identifier"
    assert fields["account_id"].source_location == "line 3"
    assert fields["available_balance"].description == "Available balance after memo activity"
    assert fields["available_balance"].source_location == "line 5"
    assert fields["status"].description == "Lifecycle state"
    assert fields["status"].source_location == "line 6"


def test_ddl_parser_handles_oracle_ddl_with_leading_comments(tmp_path: Path) -> None:
    ddl = tmp_path / "oracle.sql"
    ddl.write_text(
        "\n".join(
            [
                "-- Leading pack banner",
                "-- More comments before the first table",
                "",
                "CREATE TABLE CUSTOMER (",
                "    CUSTOMER_ID VARCHAR2(36) NOT NULL,",
                "    BALANCE_MINOR NUMBER(18,0),",
                "    COUNTRY_CODE CHAR(2),",
                "    CREATED_AT TIMESTAMP NOT NULL,",
                "    OPENED_DATE DATE,",
                "    CONSTRAINT PK_CUSTOMER PRIMARY KEY (CUSTOMER_ID)",
                ");",
                "COMMENT ON COLUMN CUSTOMER.CUSTOMER_ID IS 'Customer UUID';",
                "CREATE INDEX IDX_CUSTOMER_ID ON CUSTOMER (CUSTOMER_ID);",
            ]
        ),
        encoding="utf-8",
    )

    results = parse_ddl(ddl)

    assert len(results) == 1
    assert results[0].entity_name == "CUSTOMER"
    fields = {field.name: field for field in results[0].fields}
    assert fields["CUSTOMER_ID"].type == "VARCHAR"
    assert fields["CUSTOMER_ID"].length == 36
    assert fields["CUSTOMER_ID"].description == "Customer UUID"
    assert fields["BALANCE_MINOR"].type == "DECIMAL"
    assert fields["BALANCE_MINOR"].precision == 18
    assert fields["BALANCE_MINOR"].scale == 0
    assert fields["COUNTRY_CODE"].type == "CHAR"
    assert fields["COUNTRY_CODE"].length == 2
    assert fields["CREATED_AT"].type == "TIMESTAMP"
    assert fields["OPENED_DATE"].type == "DATE"


def test_ddl_parser_handles_oracle_comments_constraints_and_inline_comments(
    tmp_path: Path,
) -> None:
    ddl = tmp_path / "oracle-types.sql"
    ddl.write_text(
        "\n".join(
            [
                "/* block comment before table */",
                "CREATE TABLE PAYMENT_LIMIT (",
                "    LIMIT_ID VARCHAR2(36) NOT NULL,",
                "    CURRENCY_CODE CHAR(3) NOT NULL, -- ISO currency code",
                "    DAILY_LIMIT_MINOR NUMBER(18,0) NOT NULL,",
                "    EFFECTIVE_FROM DATE NOT NULL,",
                "    UPDATED_AT TIMESTAMP,",
                "    CONSTRAINT CHK_LIMIT CHECK (DAILY_LIMIT_MINOR > 0)",
                ");",
                "COMMENT ON COLUMN PAYMENT_LIMIT.DAILY_LIMIT_MINOR IS 'Daily limit in minor units';",
                "COMMENT ON COLUMN PAYMENT_LIMIT.UPDATED_AT IS 'Last update timestamp';",
                "CREATE INDEX IDX_LIMIT ON PAYMENT_LIMIT (LIMIT_ID);",
            ]
        ),
        encoding="utf-8",
    )

    result = parse_ddl(ddl)[0]
    fields = {field.name: field for field in result.fields}

    assert [field.name for field in result.fields] == [
        "LIMIT_ID",
        "CURRENCY_CODE",
        "DAILY_LIMIT_MINOR",
        "EFFECTIVE_FROM",
        "UPDATED_AT",
    ]
    assert fields["CURRENCY_CODE"].description == "ISO currency code"
    assert fields["DAILY_LIMIT_MINOR"].type == "DECIMAL"
    assert fields["DAILY_LIMIT_MINOR"].precision == 18
    assert fields["DAILY_LIMIT_MINOR"].scale == 0
    assert fields["DAILY_LIMIT_MINOR"].description == "Daily limit in minor units"
    assert fields["UPDATED_AT"].description == "Last update timestamp"


def test_ddl_parser_parses_legacy_payments_smoke_pack_fixture() -> None:
    results = parse_ddl(Path("tests/fixtures/oracle-legacy-payments-ddl.sql"))

    assert [result.entity_name for result in results] == [
        "CUSTOMER",
        "ACCOUNT",
        "PAYMENT_ORDER",
        "PAYMENT_LIMIT",
    ]
    by_entity = {result.entity_name: result for result in results}
    account_fields = {field.name: field for field in by_entity["ACCOUNT"].fields}
    assert account_fields["BALANCE_MINOR"].type == "DECIMAL"
    assert account_fields["BALANCE_MINOR"].precision == 18
    assert account_fields["BALANCE_MINOR"].scale == 0
    assert "minor currency units" in (account_fields["BALANCE_MINOR"].description or "")

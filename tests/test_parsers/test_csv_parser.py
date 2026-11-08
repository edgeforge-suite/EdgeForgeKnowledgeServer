from pathlib import Path

from knowledge_server.parsers.csv_parser import parse_csv


def test_csv_parser_extracts_field_catalog_rows() -> None:
    result = parse_csv(Path("tests/fixtures/data-dictionary.csv"))

    assert len(result.fields) == 3
    account_id = result.fields[0]
    assert account_id.entity == "Account"
    assert account_id.name == "account_id"
    assert account_id.type == "string"
    assert account_id.length == 12
    assert account_id.nullable is False
    assert account_id.source_location == "row 2"

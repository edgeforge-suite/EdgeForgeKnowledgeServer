from pathlib import Path

from knowledge_server.parsers.markdown_parser import parse_markdown


def test_markdown_parser_chunks_by_heading() -> None:
    chunks = parse_markdown(Path("tests/fixtures/sample-brd.md"))

    assert [chunk.heading for chunk in chunks] == [
        "Account Requirements",
        "Balance Rules",
        "Customer Rules",
    ]
    assert "memo credits" in chunks[1].content
    assert chunks[1].content_hash == chunks[1].content_hash

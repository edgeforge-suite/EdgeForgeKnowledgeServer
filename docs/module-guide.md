# Knowledge Server Module Guide

This guide maps KS behavior to source modules. It is intentionally lightweight:
read the code and tests for implementation details, and use this as a routing
map.

## Runtime Entry

- `knowledge_server/server.py` registers the 16 public MCP tools on the local
  stdio FastMCP server.
- `knowledge_server/__init__.py` carries the package version.

## Models

- `knowledge_server/models/documents.py` defines document, evidence, field
  catalog, suggestion, decision, and tool result models.

## Ingestion And Safety

- `knowledge_server/tools/ingest.py` coordinates ingest, parser selection, and
  storage writes.
- `knowledge_server/safety.py` owns allowed-root checks, raw file-size caps, and
  parser resource limits.

## Parsers

- `knowledge_server/parsers/markdown_parser.py` extracts Markdown text/chunks.
- `knowledge_server/parsers/csv_parser.py` extracts CSV field catalogs.
- `knowledge_server/parsers/ddl_parser.py` extracts SQL/Oracle DDL entities,
  fields, and lightweight structural metadata.
- `knowledge_server/parsers/excel_parser.py` extracts Excel dictionary rows.
- `knowledge_server/parsers/pdf_parser.py` extracts bounded PDF text.
- `knowledge_server/parsers/docx_parser.py` extracts bounded DOCX text.

## Storage

- `knowledge_server/storage/database.py` owns SQLite schema initialization,
  migrations, FTS5/BM25 search, field catalog reads, suggestion persistence,
  decision updates, reingest invalidation, soft delete, and hard purge.

## Tool Facades

- `knowledge_server/tools/search.py` owns list/search document retrieval.
- `knowledge_server/tools/read.py` owns read-document access.
- `knowledge_server/tools/evidence.py` owns evidence lookup.
- `knowledge_server/tools/conflicts.py` owns broad conflict search.
- `knowledge_server/tools/field_catalog.py` owns catalog reads.
- `knowledge_server/tools/suggest.py` owns field and generic manifest suggestion
  entry points.
- `knowledge_server/tools/evidence_chain.py` owns field and generic suggestion
  evidence-chain entry points.
- `knowledge_server/tools/decisions.py` owns review-decision write-back.
- `knowledge_server/tools/delete.py` owns soft-delete and hard-purge tool
  facades.
- `knowledge_server/tools/portfolio.py` owns cross-project search.
- `knowledge_server/tools/compare.py` owns field-definition comparison.

## Tests

- `tests/test_parsers/` covers parser behavior.
- `tests/test_tools/` covers tool behavior and storage-backed workflows.
- `tests/test_server/` covers MCP/server registration and stdio round-trips.

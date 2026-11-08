import csv
from pathlib import Path

from knowledge_server.models import SuggestionDecision
from knowledge_server.storage import KnowledgeStore
from knowledge_server.tools.decisions import submit_suggestion_decisions
from knowledge_server.tools.delete import delete_document
from knowledge_server.tools.evidence import get_evidence
from knowledge_server.tools.evidence_chain import get_suggestion_evidence_chain
from knowledge_server.tools.field_catalog import read_field_catalog
from knowledge_server.tools.ingest import ingest_document
from knowledge_server.tools.read import read_document
from knowledge_server.tools.search import list_documents, search_documents
from knowledge_server.tools.suggest import suggest_fields, suggest_manifest_candidates
from tests.helpers import make_test_pdf


def test_get_evidence_returns_full_chunk_content_and_citation(tmp_path: Path) -> None:
    source = tmp_path / "rules.md"
    source.write_text(
        "# Balance Rules\n\nThe available balance must include memo credits and exclude memo debits.\n",
        encoding="utf-8",
    )
    store = KnowledgeStore(tmp_path / "ks.sqlite3")
    ingest_document(
        store=store,
        allowed_roots=[tmp_path],
        project_id="project-a",
        file_path=str(source),
        doc_type="markdown",
    )

    result = get_evidence(store=store, project_id="project-a", query="memo credits")

    assert result.chunk_count == 1
    assert "include memo credits and exclude memo debits" in result.chunks[0].content
    assert result.chunks[0].citation is not None
    assert result.chunks[0].citation.chunk_id == result.chunks[0].chunk_id


def test_get_evidence_respects_doc_type_filter(tmp_path: Path) -> None:
    md_source = tmp_path / "rules.md"
    md_source.write_text("# Balance Rules\n\nMemo credits matter.\n", encoding="utf-8")
    csv_source = Path("tests/fixtures/data-dictionary.csv").resolve()
    store = KnowledgeStore(tmp_path / "ks.sqlite3")
    ingest_document(
        store=store,
        allowed_roots=[tmp_path],
        project_id="project-a",
        file_path=str(md_source),
        doc_type="markdown",
    )
    ingest_document(
        store=store,
        allowed_roots=[csv_source.parent],
        project_id="project-a",
        file_path=str(csv_source),
        doc_type="csv",
    )

    result = get_evidence(
        store=store,
        project_id="project-a",
        query="account",
        doc_types=["csv"],
    )

    assert result.chunk_count >= 1
    assert all(chunk.doc_type == "csv" for chunk in result.chunks)


def test_get_evidence_min_score_filters_results(tmp_path: Path) -> None:
    strong = tmp_path / "strong.md"
    weak = tmp_path / "weak.md"
    strong.write_text("# Strong\n\nbalance balance balance balance balance\n", encoding="utf-8")
    weak.write_text("# Weak\n\nbalance once\n", encoding="utf-8")
    store = KnowledgeStore(tmp_path / "ks.sqlite3")
    for source in [strong, weak]:
        ingest_document(
            store=store,
            allowed_roots=[tmp_path],
            project_id="project-a",
            file_path=str(source),
            doc_type="markdown",
        )

    baseline = get_evidence(store=store, project_id="project-a", query="balance", max_chunks=5)
    threshold = (baseline.chunks[0].score + baseline.chunks[1].score) / 2

    filtered = get_evidence(
        store=store,
        project_id="project-a",
        query="balance",
        max_chunks=5,
        min_score=threshold,
    )

    assert filtered.chunk_count == 1
    assert filtered.chunk_count == len(filtered.chunks)


def test_get_evidence_warns_on_punctuation_only_query(tmp_path: Path) -> None:
    source = tmp_path / "rules.md"
    source.write_text("# Rules\n\nSomething useful.\n", encoding="utf-8")
    store = KnowledgeStore(tmp_path / "ks.sqlite3")
    ingest_document(
        store=store,
        allowed_roots=[tmp_path],
        project_id="project-a",
        file_path=str(source),
        doc_type="markdown",
    )

    result = get_evidence(store=store, project_id="project-a", query="!!!")

    assert result.chunks == []
    assert result.warnings == ["Query contained no searchable tokens; returning empty results."]


def test_get_evidence_populates_pdf_page_and_project_isolation(tmp_path: Path) -> None:
    fixture = make_test_pdf(
        tmp_path / "guide.pdf",
        [
            "Balance memo rules are documented here.",
            "Customer alerts appear on the second page.",
        ],
    )
    store = KnowledgeStore(tmp_path / "ks.sqlite3")
    ingest_document(
        store=store,
        allowed_roots=[tmp_path],
        project_id="project-a",
        file_path=str(fixture),
        doc_type="pdf",
    )

    project_a = get_evidence(store=store, project_id="project-a", query="second page")
    project_b = get_evidence(store=store, project_id="project-b", query="second page")

    assert project_a.chunk_count == 1
    assert project_a.chunks[0].page == 2
    assert project_b.chunk_count == 0


def test_delete_document_soft_deletes_but_retains_chunks(tmp_path: Path) -> None:
    source = tmp_path / "rules.md"
    source.write_text("# Balance Rules\n\nMemo credits drive balance decisions.\n", encoding="utf-8")
    store = KnowledgeStore(tmp_path / "ks.sqlite3")
    ingest = ingest_document(
        store=store,
        allowed_roots=[tmp_path],
        project_id="project-a",
        file_path=str(source),
        doc_type="markdown",
    )

    deleted = delete_document(store=store, project_id="project-a", document_id=ingest.document_id)

    assert deleted.success is True
    assert deleted.document_name == "rules.md"
    assert search_documents(store=store, project_id="project-a", query="memo").result_count == 0
    assert list_documents(store=store, project_id="project-a").documents == []
    assert get_evidence(store=store, project_id="project-a", query="memo").chunk_count == 0
    read = read_document(store=store, project_id="project-a", document_id=ingest.document_id)
    assert read.success is False
    assert read.warnings == [f"document not found for project_id project-a: {ingest.document_id}"]
    retained = store.conn.execute(
        "SELECT COUNT(*) FROM document_chunks WHERE document_id = ?",
        (ingest.document_id,),
    ).fetchone()[0]
    assert retained > 0


def test_delete_document_handles_missing_and_already_deleted(tmp_path: Path) -> None:
    source = tmp_path / "rules.md"
    source.write_text("# Balance Rules\n\nMemo credits drive balance decisions.\n", encoding="utf-8")
    store = KnowledgeStore(tmp_path / "ks.sqlite3")
    ingest = ingest_document(
        store=store,
        allowed_roots=[tmp_path],
        project_id="project-a",
        file_path=str(source),
        doc_type="markdown",
    )

    missing = delete_document(store=store, project_id="project-a", document_id="missing-doc")
    first = delete_document(store=store, project_id="project-a", document_id=ingest.document_id)
    second = delete_document(store=store, project_id="project-a", document_id=ingest.document_id)

    assert missing.success is False
    assert missing.warnings == ["document not found or already deleted: missing-doc"]
    assert first.success is True
    assert second.success is False
    assert second.warnings == [f"document not found or already deleted: {ingest.document_id}"]


def test_delete_document_invalidates_only_dependent_manifest_suggestions(
    tmp_path: Path,
) -> None:
    account = tmp_path / "account.csv"
    loan = tmp_path / "loan.csv"
    _write_catalog_csv(
        account,
        [_catalog_row("Account", "account_id", "string", "Primary account identifier.")],
    )
    _write_catalog_csv(
        loan,
        [_catalog_row("Loan", "loan_id", "string", "Primary loan identifier.")],
    )
    store = KnowledgeStore(tmp_path / "ks.sqlite3")
    account_ingest = ingest_document(
        store=store,
        allowed_roots=[tmp_path],
        project_id="project-a",
        file_path=str(account),
        doc_type="csv",
    )
    ingest_document(
        store=store,
        allowed_roots=[tmp_path],
        project_id="project-a",
        file_path=str(loan),
        doc_type="csv",
    )
    account_suggestion = suggest_fields(
        store=store,
        project_id="project-a",
        field_name_pattern="account_id",
    ).suggestions[0]
    loan_suggestion = suggest_fields(
        store=store,
        project_id="project-a",
        field_name_pattern="loan_id",
    ).suggestions[0]
    submit_suggestion_decisions(
        store=store,
        project_id="project-a",
        decisions=[
            SuggestionDecision(suggestion_id=account_suggestion.suggestion_id, status="accepted"),
            SuggestionDecision(suggestion_id=loan_suggestion.suggestion_id, status="accepted"),
        ],
    )

    deleted = delete_document(
        store=store,
        project_id="project-a",
        document_id=account_ingest.document_id,
    )
    stale_decision = submit_suggestion_decisions(
        store=store,
        project_id="project-a",
        decisions=[
            SuggestionDecision(suggestion_id=account_suggestion.suggestion_id, status="rejected")
        ],
    )
    stale_chain = get_suggestion_evidence_chain(
        store=store,
        project_id="project-a",
        suggestion_id=account_suggestion.suggestion_id,
        scope="fields",
    )
    refreshed_loan = suggest_fields(
        store=store,
        project_id="project-a",
        field_name_pattern="loan_id",
    ).suggestions[0]

    assert deleted.success is True
    assert _manifest_suggestion_row(store, account_suggestion.suggestion_id) is None
    loan_row = _manifest_suggestion_row(store, loan_suggestion.suggestion_id)
    assert loan_row is not None
    assert loan_row["status"] == "accepted"
    assert stale_decision.success is False
    assert "Suggestion not found" in stale_decision.outcomes[0].error
    assert stale_chain.success is False
    assert "suggestion not found" in stale_chain.warnings[0]
    assert suggest_fields(
        store=store,
        project_id="project-a",
        field_name_pattern="account_id",
    ).suggestions == []
    assert read_field_catalog(store=store, project_id="project-a", entity="Account").fields == []
    assert refreshed_loan.status == "accepted"


def test_delete_document_reingest_creates_fresh_suggestions(
    tmp_path: Path,
) -> None:
    account = tmp_path / "account.csv"
    _write_catalog_csv(
        account,
        [_catalog_row("Account", "account_id", "string", "Primary account identifier.")],
    )
    store = KnowledgeStore(tmp_path / "ks.sqlite3")
    account_ingest = ingest_document(
        store=store,
        allowed_roots=[tmp_path],
        project_id="project-a",
        file_path=str(account),
        doc_type="csv",
    )
    suggestion = suggest_fields(
        store=store,
        project_id="project-a",
        field_name_pattern="account_id",
    ).suggestions[0]
    submit_suggestion_decisions(
        store=store,
        project_id="project-a",
        decisions=[SuggestionDecision(suggestion_id=suggestion.suggestion_id, status="accepted")],
    )

    delete_document(store=store, project_id="project-a", document_id=account_ingest.document_id)
    ingest_document(
        store=store,
        allowed_roots=[tmp_path],
        project_id="project-a",
        file_path=str(account),
        doc_type="csv",
    )
    refreshed = suggest_fields(
        store=store,
        project_id="project-a",
        field_name_pattern="account_id",
    ).suggestions[0]

    assert refreshed.suggestion_id == suggestion.suggestion_id
    assert refreshed.status == "pending"


def test_delete_document_invalidates_identity_role_review_state(
    tmp_path: Path,
) -> None:
    ddl = tmp_path / "identity.sql"
    ddl.write_text(
        """
        CREATE TABLE ACCOUNT (
            account_id VARCHAR2(36) PRIMARY KEY
        );
        """,
        encoding="utf-8",
    )
    store = KnowledgeStore(tmp_path / "ks.sqlite3")
    ingest = ingest_document(
        store=store,
        allowed_roots=[tmp_path],
        project_id="project-a",
        file_path=str(ddl),
        doc_type="sql",
    )
    suggestion = suggest_manifest_candidates(
        store=store,
        project_id="project-a",
        scope="identity_role",
        entity="ACCOUNT",
    ).suggestions[0]
    submit_suggestion_decisions(
        store=store,
        project_id="project-a",
        decisions=[SuggestionDecision(suggestion_id=suggestion.suggestion_id, status="accepted")],
    )

    delete_document(store=store, project_id="project-a", document_id=ingest.document_id)
    stale_chain = get_suggestion_evidence_chain(
        store=store,
        project_id="project-a",
        suggestion_id=suggestion.suggestion_id,
        scope="identity_role",
    )
    ingest_document(
        store=store,
        allowed_roots=[tmp_path],
        project_id="project-a",
        file_path=str(ddl),
        doc_type="sql",
    )
    refreshed = suggest_manifest_candidates(
        store=store,
        project_id="project-a",
        scope="identity_role",
        entity="ACCOUNT",
    ).suggestions[0]

    assert stale_chain.success is False
    assert "suggestion not found" in stale_chain.warnings[0]
    assert refreshed.suggestion_id == suggestion.suggestion_id
    assert refreshed.status == "pending"


def test_delete_document_clears_orphaned_identity_role_review_state_after_reingest(
    tmp_path: Path,
) -> None:
    ddl = tmp_path / "identity.sql"
    ddl.write_text(
        """
        CREATE TABLE ACCOUNT (
            account_id VARCHAR2(36) PRIMARY KEY
        );
        """,
        encoding="utf-8",
    )
    store = KnowledgeStore(tmp_path / "ks.sqlite3")
    ingest = ingest_document(
        store=store,
        allowed_roots=[tmp_path],
        project_id="project-a",
        file_path=str(ddl),
        doc_type="sql",
    )
    suggestion = suggest_manifest_candidates(
        store=store,
        project_id="project-a",
        scope="identity_role",
        entity="ACCOUNT",
    ).suggestions[0]
    submit_suggestion_decisions(
        store=store,
        project_id="project-a",
        decisions=[SuggestionDecision(suggestion_id=suggestion.suggestion_id, status="accepted")],
    )

    ddl.write_text(
        """
        -- changed source evidence preserves review state but removes the active row
        CREATE TABLE ACCOUNT (
            account_id VARCHAR2(36) PRIMARY KEY
        );
        """,
        encoding="utf-8",
    )
    ingest_document(
        store=store,
        allowed_roots=[tmp_path],
        project_id="project-a",
        file_path=str(ddl),
        doc_type="sql",
    )
    assert _manifest_suggestion_row(store, suggestion.suggestion_id) is None

    delete_document(store=store, project_id="project-a", document_id=ingest.document_id)
    ingest_document(
        store=store,
        allowed_roots=[tmp_path],
        project_id="project-a",
        file_path=str(ddl),
        doc_type="sql",
    )
    refreshed = suggest_manifest_candidates(
        store=store,
        project_id="project-a",
        scope="identity_role",
        entity="ACCOUNT",
    ).suggestions[0]

    assert refreshed.suggestion_id == suggestion.suggestion_id
    assert refreshed.status == "pending"


def _write_catalog_csv(path: Path, rows: list[dict[str, str]]) -> None:
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=["entity", "field_name", "type", "nullable", "description"],
        )
        writer.writeheader()
        writer.writerows(rows)


def _catalog_row(
    entity: str,
    field_name: str,
    field_type: str,
    description: str,
) -> dict[str, str]:
    return {
        "entity": entity,
        "field_name": field_name,
        "type": field_type,
        "nullable": "false",
        "description": description,
    }


def _manifest_suggestion_row(store: KnowledgeStore, suggestion_id: str):
    return store.conn.execute(
        "SELECT status FROM manifest_suggestions WHERE suggestion_id = ?",
        (suggestion_id,),
    ).fetchone()

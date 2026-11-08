from __future__ import annotations

import json
from pathlib import Path

from knowledge_server.models import SuggestionDecision
from knowledge_server.storage import KnowledgeStore
from knowledge_server.tools.decisions import submit_suggestion_decisions
from knowledge_server.tools.delete import delete_document
from knowledge_server.tools.evidence_chain import get_suggestion_evidence_chain
from knowledge_server.tools.ingest import ingest_document
from knowledge_server.tools.suggest import suggest_manifest_candidates


def test_portfolio_reuse_wraps_cross_project_search_as_suggestions(tmp_path: Path) -> None:
    store = KnowledgeStore(tmp_path / "ks.sqlite3")
    _ingest_text(store, tmp_path, project_id="current", name="current.md", text="Local project.")
    matched = _ingest_text(
        store,
        tmp_path,
        project_id="source",
        name="portfolio.md",
        text="# Balance Pattern\n\nPortfolio balance pattern for memo credits.",
    )

    result = suggest_manifest_candidates(
        store=store,
        project_id="current",
        scope="portfolio_reuse",
        field_name_pattern="balance",
    )

    assert result.success is True
    assert result.scope == "portfolio_reuse"
    assert result.suggestion_count == 1
    suggestion = result.suggestions[0]
    assert suggestion.suggestion_type == "portfolio_reuse"
    assert suggestion.project_id == "current"
    assert suggestion.target_step == "review"
    assert suggestion.manifest_path.startswith("portfolio_reuse.source.")
    assert suggestion.payload["query"] == "balance"
    assert suggestion.payload["matched_project_id"] == "source"
    assert suggestion.payload["matched_document_id"] == matched.document_id
    assert suggestion.payload["matched_document_name"] == "portfolio.md"
    assert suggestion.payload["matched_chunk_id"]
    assert suggestion.payload["doc_type"] == "markdown"
    assert suggestion.payload["reuse_kind"] == "portfolio-pattern"
    assert suggestion.payload["target_step"] == "review"
    assert suggestion.payload["target_manifest_path"] is None
    assert suggestion.citations
    assert suggestion.source_document_ids == [matched.document_id]


def test_portfolio_reuse_blank_query_warns_without_persisting(tmp_path: Path) -> None:
    store = KnowledgeStore(tmp_path / "ks.sqlite3")

    result = suggest_manifest_candidates(
        store=store,
        project_id="current",
        scope="portfolio_reuse",
        field_name_pattern="!!!",
    )

    assert result.success is True
    assert result.suggestions == []
    assert "field_name_pattern" in result.warnings[0]
    assert _portfolio_row_count(store) == 0


def test_portfolio_reuse_excludes_current_project_matches_by_default(
    tmp_path: Path,
) -> None:
    store = KnowledgeStore(tmp_path / "ks.sqlite3")
    _ingest_text(
        store,
        tmp_path,
        project_id="current",
        name="current.md",
        text="# Balance Pattern\n\nCurrent project balance pattern.",
    )

    result = suggest_manifest_candidates(
        store=store,
        project_id="current",
        scope="portfolio_reuse",
        field_name_pattern="balance",
    )

    assert result.suggestions == []
    assert result.warnings
    assert _portfolio_row_count(store) == 0


def test_portfolio_reuse_skips_deleted_source_documents(tmp_path: Path) -> None:
    store = KnowledgeStore(tmp_path / "ks.sqlite3")
    _ingest_text(store, tmp_path, project_id="current", name="current.md", text="Local project.")
    deleted = _ingest_text(
        store,
        tmp_path,
        project_id="source",
        name="deleted.md",
        text="# Balance Pattern\n\nDeleted portfolio balance pattern.",
    )
    delete_document(store=store, project_id="source", document_id=deleted.document_id)

    result = suggest_manifest_candidates(
        store=store,
        project_id="current",
        scope="portfolio_reuse",
        field_name_pattern="balance",
    )

    assert result.suggestions == []
    assert _portfolio_row_count(store) == 0


def test_portfolio_reuse_repeated_calls_are_stable_without_duplicates(
    tmp_path: Path,
) -> None:
    store = KnowledgeStore(tmp_path / "ks.sqlite3")
    _ingest_portfolio_pair(store, tmp_path)

    first = suggest_manifest_candidates(
        store=store,
        project_id="current",
        scope="portfolio_reuse",
        field_name_pattern="balance",
    )
    second = suggest_manifest_candidates(
        store=store,
        project_id="current",
        scope="portfolio_reuse",
        field_name_pattern="balance",
    )

    assert first.suggestions[0].suggestion_id == second.suggestions[0].suggestion_id
    assert _portfolio_row_count(store) == 1


def test_portfolio_reuse_decision_status_is_preserved_after_refresh(
    tmp_path: Path,
) -> None:
    store = KnowledgeStore(tmp_path / "ks.sqlite3")
    _ingest_portfolio_pair(store, tmp_path)
    suggestion = suggest_manifest_candidates(
        store=store,
        project_id="current",
        scope="portfolio_reuse",
        field_name_pattern="balance",
    ).suggestions[0]

    submit_suggestion_decisions(
        store=store,
        project_id="current",
        decisions=[SuggestionDecision(suggestion_id=suggestion.suggestion_id, status="accepted")],
    )
    accepted = suggest_manifest_candidates(
        store=store,
        project_id="current",
        scope="portfolio_reuse",
        field_name_pattern="balance",
    ).suggestions[0]
    submit_suggestion_decisions(
        store=store,
        project_id="current",
        decisions=[SuggestionDecision(suggestion_id=suggestion.suggestion_id, status="rejected")],
    )
    rejected = suggest_manifest_candidates(
        store=store,
        project_id="current",
        scope="portfolio_reuse",
        field_name_pattern="balance",
    ).suggestions[0]
    submit_suggestion_decisions(
        store=store,
        project_id="current",
        decisions=[
            SuggestionDecision(
                suggestion_id=suggestion.suggestion_id,
                status="edited",
                edited_payload={"reuse_note": "Useful balance rule pattern."},
            )
        ],
    )
    edited = suggest_manifest_candidates(
        store=store,
        project_id="current",
        scope="portfolio_reuse",
        field_name_pattern="balance",
    ).suggestions[0]

    assert accepted.status == "accepted"
    assert rejected.status == "rejected"
    assert edited.status == "edited"
    assert edited.edited_payload == {"reuse_note": "Useful balance rule pattern."}
    stored_payload = _stored_portfolio_payload(store, suggestion.suggestion_id)
    assert stored_payload["status"] == "edited"
    assert stored_payload["edited_payload"] == {"reuse_note": "Useful balance rule pattern."}


def test_portfolio_reuse_edited_payload_validation_requires_note_or_rationale(
    tmp_path: Path,
) -> None:
    store = KnowledgeStore(tmp_path / "ks.sqlite3")
    _ingest_portfolio_pair(store, tmp_path)
    suggestion = suggest_manifest_candidates(
        store=store,
        project_id="current",
        scope="portfolio_reuse",
        field_name_pattern="balance",
    ).suggestions[0]

    valid = submit_suggestion_decisions(
        store=store,
        project_id="current",
        decisions=[
            SuggestionDecision(
                suggestion_id=suggestion.suggestion_id,
                status="edited",
                edited_payload={
                    "reuse_note": "Reuse the proven balance policy wording.",
                    "target_step": "step6",
                    "target_manifest_path": "rules.Account.balance-policy",
                    "rationale": "Human reviewed cross-project fit.",
                },
            )
        ],
    )
    missing_payload = submit_suggestion_decisions(
        store=store,
        project_id="current",
        decisions=[SuggestionDecision(suggestion_id=suggestion.suggestion_id, status="edited")],
    )
    target_only = submit_suggestion_decisions(
        store=store,
        project_id="current",
        decisions=[
            SuggestionDecision(
                suggestion_id=suggestion.suggestion_id,
                status="edited",
                edited_payload={"target_step": "step6"},
            )
        ],
    )
    unknown = submit_suggestion_decisions(
        store=store,
        project_id="current",
        decisions=[
            SuggestionDecision(
                suggestion_id=suggestion.suggestion_id,
                status="edited",
                edited_payload={"foo": "bar"},
            )
        ],
    )

    assert valid.success is True
    assert valid.outcomes[0].success is True
    assert missing_payload.success is False
    assert "edited_payload is required" in (missing_payload.outcomes[0].error or "")
    assert target_only.success is False
    assert "reuse_note or rationale" in (target_only.outcomes[0].error or "")
    assert unknown.success is False
    assert "unsupported keys" in (unknown.outcomes[0].error or "")


def test_portfolio_reuse_evidence_chain_returns_source_project_chunk(
    tmp_path: Path,
) -> None:
    store = KnowledgeStore(tmp_path / "ks.sqlite3")
    matched = _ingest_portfolio_pair(store, tmp_path)
    suggestion = suggest_manifest_candidates(
        store=store,
        project_id="current",
        scope="portfolio_reuse",
        field_name_pattern="balance",
    ).suggestions[0]

    chain = get_suggestion_evidence_chain(
        store=store,
        project_id="current",
        suggestion_id=suggestion.suggestion_id,
        scope="portfolio_reuse",
    )

    assert chain.success is True
    assert chain.scope == "portfolio_reuse"
    assert chain.suggestion is not None
    assert chain.suggestion.payload["matched_project_id"] == "source"
    assert len(chain.evidence_chunks) == 1
    assert chain.evidence_chunks[0].document_id == matched.document_id
    assert chain.evidence_chunks[0].document_name == "portfolio.md"


def test_unsupported_random_scope_still_does_not_persist_fake_suggestions(
    tmp_path: Path,
) -> None:
    store = KnowledgeStore(tmp_path / "ks.sqlite3")

    result = suggest_manifest_candidates(
        store=store,
        project_id="current",
        scope="not_a_scope",
        field_name_pattern="balance",
    )

    assert result.success is False
    assert result.unsupported_scope is True
    assert result.suggestions == []
    assert _portfolio_row_count(store) == 0


def _ingest_portfolio_pair(store: KnowledgeStore, tmp_path: Path):
    _ingest_text(store, tmp_path, project_id="current", name="current.md", text="Local project.")
    return _ingest_text(
        store,
        tmp_path,
        project_id="source",
        name="portfolio.md",
        text="# Balance Pattern\n\nPortfolio balance pattern for memo credits.",
    )


def _ingest_text(
    store: KnowledgeStore,
    tmp_path: Path,
    *,
    project_id: str,
    name: str,
    text: str,
):
    path = tmp_path / project_id / name
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    return ingest_document(
        store=store,
        allowed_roots=[tmp_path],
        project_id=project_id,
        file_path=str(path),
        doc_type="markdown",
    )


def _portfolio_row_count(store: KnowledgeStore) -> int:
    row = store.conn.execute(
        """
        SELECT COUNT(*) AS row_count
        FROM manifest_suggestions
        WHERE suggestion_type = 'portfolio_reuse'
        """
    ).fetchone()
    return int(row["row_count"])


def _stored_portfolio_payload(store: KnowledgeStore, suggestion_id: str) -> dict:
    row = store.conn.execute(
        """
        SELECT suggestion_payload
        FROM manifest_suggestions
        WHERE suggestion_id = ?
        """,
        (suggestion_id,),
    ).fetchone()
    assert row is not None
    return json.loads(row["suggestion_payload"])

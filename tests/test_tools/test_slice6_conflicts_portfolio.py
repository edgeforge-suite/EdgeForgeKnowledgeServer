from pathlib import Path

from knowledge_server.storage import KnowledgeStore
from knowledge_server.tools.conflicts import find_conflicts
from knowledge_server.tools.delete import delete_document
from knowledge_server.tools.ingest import ingest_document
from knowledge_server.tools.portfolio import search_across_projects


def test_find_conflicts_returns_ranked_pairs_for_multiple_documents(tmp_path: Path) -> None:
    first = tmp_path / "balance-a.md"
    second = tmp_path / "balance-b.md"
    first.write_text("# Balance Rules\n\nThe balance includes memo credits.\n", encoding="utf-8")
    second.write_text("# Balance Exceptions\n\nThe balance excludes memo credits.\n", encoding="utf-8")
    store = KnowledgeStore(tmp_path / "ks.sqlite3")
    for source in [first, second]:
        ingest_document(
            store=store,
            allowed_roots=[tmp_path],
            project_id="project-a",
            file_path=str(source),
            doc_type="markdown",
        )

    result = find_conflicts(store=store, project_id="project-a", query="balance")

    assert result.conflict_count >= 1
    assert result.conflict_count == len(result.conflict_pairs)
    assert result.searched_chunks > 0
    pair = result.conflict_pairs[0]
    assert pair.chunk_a.content
    assert pair.chunk_b.content
    assert pair.conflict_signal


def test_find_conflicts_warns_when_fewer_than_two_documents_match(tmp_path: Path) -> None:
    source = tmp_path / "balance.md"
    source.write_text("# Balance Rules\n\nThe balance includes memo credits.\n", encoding="utf-8")
    store = KnowledgeStore(tmp_path / "ks.sqlite3")
    ingest_document(
        store=store,
        allowed_roots=[tmp_path],
        project_id="project-a",
        file_path=str(source),
        doc_type="markdown",
    )

    result = find_conflicts(store=store, project_id="project-a", query="balance")

    assert result.conflict_pairs == []
    assert result.warnings == ["No conflicts detected — fewer than 2 documents matched the query."]


def test_find_conflicts_warns_on_punctuation_only_query(tmp_path: Path) -> None:
    store = KnowledgeStore(tmp_path / "ks.sqlite3")

    result = find_conflicts(store=store, project_id="project-a", query="!!!")

    assert result.conflict_pairs == []
    assert result.warnings == ["Query contained no searchable tokens; returning empty results."]


def test_find_conflicts_respects_doc_type_filter_and_project_isolation(tmp_path: Path) -> None:
    markdown = tmp_path / "balance.md"
    markdown.write_text("# Balance Rules\n\nThe balance includes memo credits.\n", encoding="utf-8")
    csv_source = Path("tests/fixtures/data-dictionary.csv").resolve()
    store = KnowledgeStore(tmp_path / "ks.sqlite3")
    ingest_document(
        store=store,
        allowed_roots=[tmp_path],
        project_id="project-a",
        file_path=str(markdown),
        doc_type="markdown",
    )
    ingest_document(
        store=store,
        allowed_roots=[csv_source.parent],
        project_id="project-a",
        file_path=str(csv_source),
        doc_type="csv",
    )
    other = tmp_path / "other.md"
    other.write_text("# Balance Rules\n\nThe balance excludes holds.\n", encoding="utf-8")
    ingest_document(
        store=store,
        allowed_roots=[tmp_path],
        project_id="project-b",
        file_path=str(other),
        doc_type="markdown",
    )

    filtered = find_conflicts(
        store=store,
        project_id="project-a",
        query="account",
        doc_types=["csv"],
    )
    isolated = find_conflicts(store=store, project_id="project-b", query="memo credits")

    assert filtered.conflict_pairs == []
    assert filtered.warnings == ["No conflicts detected — fewer than 2 documents matched the query."]
    assert isolated.conflict_pairs == []
    assert isolated.warnings == ["No conflicts detected — fewer than 2 documents matched the query."]


def test_find_conflicts_excludes_soft_deleted_documents_and_applies_min_score(tmp_path: Path) -> None:
    strong = tmp_path / "strong.md"
    weak = tmp_path / "weak.md"
    removed = tmp_path / "removed.md"
    strong.write_text("# Balance\n\nbalance balance balance balance balance\n", encoding="utf-8")
    weak.write_text("# Balance\n\nbalance once\n", encoding="utf-8")
    removed.write_text("# Balance\n\nbalance temporary contradiction\n", encoding="utf-8")
    store = KnowledgeStore(tmp_path / "ks.sqlite3")
    ingests = []
    for source in [strong, weak, removed]:
        ingests.append(
            ingest_document(
                store=store,
                allowed_roots=[tmp_path],
                project_id="project-a",
                file_path=str(source),
                doc_type="markdown",
            )
        )
    delete_document(store=store, project_id="project-a", document_id=ingests[2].document_id)

    baseline = find_conflicts(
        store=store,
        project_id="project-a",
        query="balance",
        max_chunks_to_search=20,
    )
    threshold = min(
        pair.chunk_a.score
        for pair in baseline.conflict_pairs
    )
    filtered = find_conflicts(
        store=store,
        project_id="project-a",
        query="balance",
        max_chunks_to_search=20,
        min_score=threshold,
    )

    deleted_id = ingests[2].document_id
    assert all(pair.document_a_id != deleted_id and pair.document_b_id != deleted_id for pair in baseline.conflict_pairs)
    assert filtered.searched_chunks <= baseline.searched_chunks


def test_search_across_projects_returns_grouped_results(tmp_path: Path) -> None:
    first = tmp_path / "project-a.md"
    second = tmp_path / "project-b.md"
    first.write_text("# Balance Rules\n\nMemo credits drive available balance.\n", encoding="utf-8")
    second.write_text("# Balance Rules\n\nAvailable balance drives alert routing.\n", encoding="utf-8")
    store = KnowledgeStore(tmp_path / "ks.sqlite3")
    ingest_document(
        store=store,
        allowed_roots=[tmp_path],
        project_id="project-a",
        file_path=str(first),
        doc_type="markdown",
    )
    ingest_document(
        store=store,
        allowed_roots=[tmp_path],
        project_id="project-b",
        file_path=str(second),
        doc_type="markdown",
    )

    results = search_across_projects(store=store, query="balance")

    project_ids = {entry.project_id for entry in results.by_project}
    assert {"project-a", "project-b"}.issubset(project_ids)
    assert results.projects_searched >= 2
    assert results.projects_with_results >= 2
    assert results.total_result_count == sum(entry.result_count for entry in results.by_project)
    assert all(entry.result_count == len(entry.results) for entry in results.by_project)


def test_search_across_projects_respects_project_filter_and_excludes_empty_projects(tmp_path: Path) -> None:
    first = tmp_path / "project-a.md"
    second = tmp_path / "project-b.md"
    third = tmp_path / "project-c.md"
    first.write_text("# Balance Rules\n\nMemo credits drive available balance.\n", encoding="utf-8")
    second.write_text("# Balance Rules\n\nAvailable balance drives alert routing.\n", encoding="utf-8")
    third.write_text("# Fees\n\nOverdraft fees appear elsewhere.\n", encoding="utf-8")
    store = KnowledgeStore(tmp_path / "ks.sqlite3")
    ingest_document(
        store=store,
        allowed_roots=[tmp_path],
        project_id="project-a",
        file_path=str(first),
        doc_type="markdown",
    )
    ingest_document(
        store=store,
        allowed_roots=[tmp_path],
        project_id="project-b",
        file_path=str(second),
        doc_type="markdown",
    )
    ingest_document(
        store=store,
        allowed_roots=[tmp_path],
        project_id="project-c",
        file_path=str(third),
        doc_type="markdown",
    )

    filtered = search_across_projects(
        store=store,
        query="balance",
        project_ids=["project-a"],
    )
    broad = search_across_projects(
        store=store,
        query="balance",
        project_ids=["project-a", "project-c"],
    )

    assert [entry.project_id for entry in filtered.by_project] == ["project-a"]
    assert broad.projects_searched == 2
    assert [entry.project_id for entry in broad.by_project] == ["project-a"]


def test_search_across_projects_warns_on_punctuation_only_query(tmp_path: Path) -> None:
    store = KnowledgeStore(tmp_path / "ks.sqlite3")

    result = search_across_projects(store=store, query="!!!")

    assert result.by_project == []
    assert result.warnings == ["Query contained no searchable tokens; returning empty results."]


def test_search_across_projects_applies_per_project_limits_and_min_score(tmp_path: Path) -> None:
    first = tmp_path / "one.md"
    second = tmp_path / "two.md"
    third = tmp_path / "three.md"
    first.write_text("# Balance\n\nbalance balance balance\n\n## More\n\nbalance again\n", encoding="utf-8")
    second.write_text("# Balance\n\nbalance once\n", encoding="utf-8")
    third.write_text("# Balance\n\nbalance twice balance twice\n", encoding="utf-8")
    store = KnowledgeStore(tmp_path / "ks.sqlite3")
    ingest_document(
        store=store,
        allowed_roots=[tmp_path],
        project_id="project-a",
        file_path=str(first),
        doc_type="markdown",
    )
    ingest_document(
        store=store,
        allowed_roots=[tmp_path],
        project_id="project-a",
        file_path=str(second),
        doc_type="markdown",
    )
    ingest_document(
        store=store,
        allowed_roots=[tmp_path],
        project_id="project-b",
        file_path=str(third),
        doc_type="markdown",
    )

    limited = search_across_projects(store=store, query="balance", max_results_per_project=1)
    baseline = search_across_projects(store=store, query="balance", max_results_per_project=5)
    threshold = min(result.score for entry in baseline.by_project for result in entry.results)
    filtered = search_across_projects(
        store=store,
        query="balance",
        max_results_per_project=5,
        min_score=threshold,
    )

    assert all(entry.result_count <= 1 for entry in limited.by_project)
    assert filtered.total_result_count <= baseline.total_result_count


def test_search_across_projects_excludes_soft_deleted_documents(tmp_path: Path) -> None:
    source = tmp_path / "balance.md"
    source.write_text("# Balance Rules\n\nMemo credits drive available balance.\n", encoding="utf-8")
    store = KnowledgeStore(tmp_path / "ks.sqlite3")
    ingest = ingest_document(
        store=store,
        allowed_roots=[tmp_path],
        project_id="project-a",
        file_path=str(source),
        doc_type="markdown",
    )

    delete_document(store=store, project_id="project-a", document_id=ingest.document_id)
    result = search_across_projects(store=store, query="balance")

    assert result.by_project == []
    assert result.total_result_count == 0

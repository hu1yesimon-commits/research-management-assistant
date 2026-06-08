from config import config
from main import get_vector_store_service, reset_vector_store_service_cache
from services.vector_store import ChromaVectorStoreService, FakeVectorStoreService, build_chunk_uid


def test_build_chunk_uid_is_stable_and_traceable():
    assert build_chunk_uid("paper-1", 3, "hash-abc") == "paper-1:3:hash-abc"


def test_fake_vector_store_service_returns_chroma_style_vector_refs():
    service = FakeVectorStoreService(collection_name="research_chunks")

    vector_refs = service.upsert_chunks(
        [
            {"chunk_uid": "paper-1:0:hash-a", "text": "chunk a"},
            {"chunk_uid": "paper-1:1:hash-b", "text": "chunk b"},
        ],
        embeddings=[[0.1, 0.2], [0.3, 0.4]],
    )

    assert vector_refs == [
        "chroma:research_chunks:paper-1:0:hash-a",
        "chroma:research_chunks:paper-1:1:hash-b",
    ]


def test_fake_vector_store_service_delete_vector_refs_removes_stored_entries():
    service = FakeVectorStoreService(collection_name="research_chunks")
    refs = service.upsert_chunks(
        [{"chunk_uid": "paper-1:0:hash-a", "text": "chunk a"}],
        embeddings=[[0.1, 0.2]],
    )

    service.delete_vector_refs(refs)

    assert refs[0] not in service.records


def test_chroma_vector_store_service_returns_chroma_style_vector_refs(tmp_path):
    service = ChromaVectorStoreService(
        persist_dir=str(tmp_path / "chroma"),
        collection_name="research_chunks",
    )

    refs = service.upsert_chunks(
        [
            {"chunk_uid": "paper-1:0:hash-a", "text": "chunk a"},
            {"chunk_uid": "paper-1:1:hash-b", "text": "chunk b"},
        ],
        embeddings=[[0.1, 0.2], [0.3, 0.4]],
    )

    assert refs == [
        "chroma:research_chunks:paper-1:0:hash-a",
        "chroma:research_chunks:paper-1:1:hash-b",
    ]


def test_chroma_vector_store_service_persists_to_temp_directory(tmp_path):
    persist_dir = tmp_path / "chroma-store"
    service = ChromaVectorStoreService(
        persist_dir=str(persist_dir),
        collection_name="research_chunks",
    )

    service.upsert_chunks(
        [{"chunk_uid": "paper-1:0:hash-a", "text": "chunk a"}],
        embeddings=[[0.1, 0.2]],
    )

    assert persist_dir.exists()
    assert any(persist_dir.iterdir())


def test_chroma_vector_store_service_delete_vector_refs_removes_old_ids(tmp_path):
    service = ChromaVectorStoreService(
        persist_dir=str(tmp_path / "chroma"),
        collection_name="research_chunks",
    )

    refs = service.upsert_chunks(
        [{"chunk_uid": "paper-1:0:hash-a", "text": "chunk a"}],
        embeddings=[[0.1, 0.2]],
    )
    service.delete_vector_refs(refs)

    assert service.collection.get(ids=["paper-1:0:hash-a"])["ids"] == []


def test_get_vector_store_service_switches_between_fake_and_chroma(tmp_path):
    original_backend = config.vector_backend
    original_persist_dir = config.chroma_persist_dir
    original_collection_name = config.chroma_collection_name

    try:
        reset_vector_store_service_cache()
        config.vector_backend = "fake"
        assert isinstance(get_vector_store_service(), FakeVectorStoreService)

        config.vector_backend = "chroma"
        config.chroma_persist_dir = str(tmp_path / "chroma")
        config.chroma_collection_name = "research_chunks"

        assert isinstance(get_vector_store_service(), ChromaVectorStoreService)
    finally:
        reset_vector_store_service_cache()
        config.vector_backend = original_backend
        config.chroma_persist_dir = original_persist_dir
        config.chroma_collection_name = original_collection_name


def test_get_vector_store_service_reuses_chroma_instance_for_same_config(tmp_path):
    original_backend = config.vector_backend
    original_persist_dir = config.chroma_persist_dir
    original_collection_name = config.chroma_collection_name

    try:
        reset_vector_store_service_cache()
        config.vector_backend = "chroma"
        config.chroma_persist_dir = str(tmp_path / "chroma-a")
        config.chroma_collection_name = "research_chunks"

        first = get_vector_store_service()
        second = get_vector_store_service()

        assert isinstance(first, ChromaVectorStoreService)
        assert first is second
    finally:
        reset_vector_store_service_cache()
        config.vector_backend = original_backend
        config.chroma_persist_dir = original_persist_dir
        config.chroma_collection_name = original_collection_name


def test_get_vector_store_service_does_not_reuse_across_different_chroma_configs(tmp_path):
    original_backend = config.vector_backend
    original_persist_dir = config.chroma_persist_dir
    original_collection_name = config.chroma_collection_name

    try:
        reset_vector_store_service_cache()
        config.vector_backend = "chroma"
        config.chroma_persist_dir = str(tmp_path / "chroma-a")
        config.chroma_collection_name = "research_chunks"
        first = get_vector_store_service()

        config.chroma_persist_dir = str(tmp_path / "chroma-b")
        second = get_vector_store_service()

        config.chroma_persist_dir = str(tmp_path / "chroma-a")
        config.chroma_collection_name = "other_chunks"
        third = get_vector_store_service()

        assert isinstance(first, ChromaVectorStoreService)
        assert isinstance(second, ChromaVectorStoreService)
        assert isinstance(third, ChromaVectorStoreService)
        assert first is not second
        assert first is not third
        assert second is not third
    finally:
        reset_vector_store_service_cache()
        config.vector_backend = original_backend
        config.chroma_persist_dir = original_persist_dir
        config.chroma_collection_name = original_collection_name


def test_fake_vector_store_service_query_by_embedding_returns_deterministic_nearest_hits():
    service = FakeVectorStoreService(collection_name="research_chunks")
    service.upsert_chunks(
        [
            {"chunk_uid": "paper-1:0:hash-a", "paper_id": "paper-1", "chunk_index": 0, "text": "chunk a"},
            {"chunk_uid": "paper-2:0:hash-b", "paper_id": "paper-2", "chunk_index": 0, "text": "chunk b"},
        ],
        embeddings=[[0.0, 0.0], [10.0, 10.0]],
    )

    results = service.query_by_embedding([0.1, 0.2], top_k=2)

    assert [result.chunk_uid for result in results] == ["paper-1:0:hash-a", "paper-2:0:hash-b"]
    assert results[0].vector_ref == "chroma:research_chunks:paper-1:0:hash-a"
    assert results[0].distance <= results[1].distance


def test_chroma_vector_store_service_query_by_embedding_returns_hits_from_temp_store(tmp_path):
    service = ChromaVectorStoreService(
        persist_dir=str(tmp_path / "chroma-query"),
        collection_name="research_chunks",
    )
    service.upsert_chunks(
        [
            {"chunk_uid": "paper-1:0:hash-a", "paper_id": "paper-1", "chunk_index": 0, "text": "chunk a"},
            {"chunk_uid": "paper-2:0:hash-b", "paper_id": "paper-2", "chunk_index": 0, "text": "chunk b"},
        ],
        embeddings=[[0.0, 0.0], [5.0, 5.0]],
    )

    results = service.query_by_embedding([0.0, 0.1], top_k=1)

    assert len(results) == 1
    assert results[0].chunk_uid == "paper-1:0:hash-a"
    assert results[0].vector_ref == "chroma:research_chunks:paper-1:0:hash-a"

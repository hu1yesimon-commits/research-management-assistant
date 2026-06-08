from config import config
from main import get_embedding_service, reset_embedding_service_cache
from services.embedding_service import BgeM3EmbeddingService, FakeEmbeddingService


def test_fake_embedding_service_returns_one_vector_per_text():
    service = FakeEmbeddingService()

    vectors = service.embed_texts(["alpha", "beta"])

    assert len(vectors) == 2
    assert all(len(vector) == 4 for vector in vectors)
    assert vectors[0] != vectors[1]


def test_fake_embedding_service_is_deterministic_for_same_input():
    service = FakeEmbeddingService()

    first = service.embed_texts(["repeat me", "repeat me"])
    second = service.embed_texts(["repeat me"])

    assert first[0] == first[1]
    assert first[0] == second[0]


def test_get_embedding_service_returns_fake_by_default():
    original_provider = config.embedding_provider

    try:
        reset_embedding_service_cache()
        config.embedding_provider = "fake"
        assert isinstance(get_embedding_service(), FakeEmbeddingService)
    finally:
        reset_embedding_service_cache()
        config.embedding_provider = original_provider


def test_get_embedding_service_returns_bge_m3_when_configured(tmp_path, monkeypatch):
    original_provider = config.embedding_provider
    original_model_name = config.bge_m3_model_name

    def fake_load_model(self):
        class StubModel:
            def encode(self, texts, normalize_embeddings=False):
                return [[0.1, 0.2] for _ in texts]

        return StubModel()

    try:
        reset_embedding_service_cache()
        config.embedding_provider = "bge-m3"
        config.bge_m3_model_name = "BAAI/bge-m3"
        monkeypatch.setattr(BgeM3EmbeddingService, "_load_model", fake_load_model)

        service = get_embedding_service()

        assert isinstance(service, BgeM3EmbeddingService)
    finally:
        reset_embedding_service_cache()
        config.embedding_provider = original_provider
        config.bge_m3_model_name = original_model_name


def test_bge_m3_embedding_service_uses_injected_model_loader_without_network(monkeypatch):
    class StubModel:
        def encode(self, texts, normalize_embeddings=False):
            assert normalize_embeddings is True
            return [[0.11, 0.22], [0.33, 0.44]]

    monkeypatch.setattr(BgeM3EmbeddingService, "_load_model", lambda self: StubModel())

    service = BgeM3EmbeddingService(model_name="BAAI/bge-m3")

    assert service.embed_texts(["alpha", "beta"]) == [[0.11, 0.22], [0.33, 0.44]]


def test_get_embedding_service_reuses_bge_m3_instance_for_same_config(monkeypatch):
    original_provider = config.embedding_provider
    original_model_name = config.bge_m3_model_name

    class FakeBgeService:
        def __init__(self, model_name: str):
            self.model_name = model_name

    try:
        reset_embedding_service_cache()
        config.embedding_provider = "bge-m3"
        config.bge_m3_model_name = "model-a"
        monkeypatch.setattr("main.BgeM3EmbeddingService", FakeBgeService)

        first = get_embedding_service()
        second = get_embedding_service()

        assert first is second
        assert first.model_name == "model-a"
    finally:
        reset_embedding_service_cache()
        config.embedding_provider = original_provider
        config.bge_m3_model_name = original_model_name


def test_get_embedding_service_does_not_reuse_across_different_bge_m3_models(monkeypatch):
    original_provider = config.embedding_provider
    original_model_name = config.bge_m3_model_name

    class FakeBgeService:
        def __init__(self, model_name: str):
            self.model_name = model_name

    try:
        reset_embedding_service_cache()
        config.embedding_provider = "bge-m3"
        monkeypatch.setattr("main.BgeM3EmbeddingService", FakeBgeService)

        config.bge_m3_model_name = "model-a"
        first = get_embedding_service()

        config.bge_m3_model_name = "model-b"
        second = get_embedding_service()

        assert first is not second
        assert first.model_name == "model-a"
        assert second.model_name == "model-b"
    finally:
        reset_embedding_service_cache()
        config.embedding_provider = original_provider
        config.bge_m3_model_name = original_model_name

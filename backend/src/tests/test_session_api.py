import pytest
from fastapi.testclient import TestClient

import main
from agent_team.contracts import LeaderPlan
from main import app
from services.memory_store import MemoryStore
from services.schemas import JudgeResult, PaperId, PaperMetadata


class OfflineDiscoveryGraph:
    def invoke(self, state):
        return {
            **state,
            "rewritten_queries": [state["user_query"]],
            "raw_results": [],
            "deduped_papers": [],
            "ranked_candidates": [],
        }


@pytest.fixture
def client(tmp_path, monkeypatch):
    database_path = tmp_path / "session-api.sqlite3"
    monkeypatch.setattr(main.config, "database_path", str(database_path))
    MemoryStore(str(database_path)).initialize()
    app.dependency_overrides.clear()
    app.dependency_overrides[main.get_paper_discovery_graph] = OfflineDiscoveryGraph
    yield TestClient(app)
    app.dependency_overrides.clear()


def _paper(paper_id="session-paper-1"):
    return PaperMetadata(
        paper_id=paper_id,
        source_ids=PaperId(doi=f"10.1000/{paper_id}"),
        title="Session Paper",
        authors=["Tester"],
        abstract="Useful abstract.",
        doi=f"10.1000/{paper_id}",
        source="test",
    )


def _judgement():
    return JudgeResult(
        decision="accept",
        reason="Relevant",
        llm_relevance_score=0.9,
        embedding_relevance_score=0.8,
        quality_score=0.7,
        novelty_score=1.0,
        final_score=0.85,
        tags=["test"],
    )


def _seed_candidate(session_id="default"):
    store = main.get_session_store()
    turn = store.start_turn(session_id, "seed-candidate", {"text": "seed"})
    store.complete_turn(
        turn.turn_id,
        {"assistant_message": "seeded"},
        LeaderPlan(goal="seed", plan_type="direct_reply").model_dump(mode="json"),
    )
    return main.get_candidate_lifecycle_service().create_batch(
        session_id,
        turn.turn_id,
        "graphs",
        [{"paper": _paper().model_dump(), "judgement": _judgement().model_dump()}],
    ).candidates[0]


def test_default_session_turn_and_history(client):
    response = client.post(
        "/sessions/default/turns",
        json={"message": "Find papers", "idempotency_key": "api-1"},
    )
    assert response.status_code == 200
    turn = response.json()
    assert turn["session_id"] == "default"
    assert turn["status"] == "completed"

    history = client.get("/sessions/default/messages").json()
    assert [item["role"] for item in history["items"]] == ["user", "assistant"]


def test_turn_replay_is_idempotent(client):
    payload = {"message": "What can you do?", "idempotency_key": "api-replay"}
    first = client.post("/sessions/default/turns", json=payload)
    second = client.post("/sessions/default/turns", json=payload)

    assert second.status_code == 200
    assert second.json() == first.json()
    assert len(client.get("/sessions/default/messages").json()["items"]) == 2


def test_message_history_paginates_and_bounds_limit(client):
    for index in range(2):
        response = client.post(
            "/sessions/default/turns",
            json={
                "message": "What can you do?",
                "idempotency_key": f"page-{index}",
            },
        )
        assert response.status_code == 200

    first_page = client.get("/sessions/default/messages", params={"limit": 2}).json()
    second_page = client.get(
        "/sessions/default/messages",
        params={"limit": 2, "before_id": first_page["next_before_id"]},
    ).json()
    bounded = client.get("/sessions/default/messages", params={"limit": 0})

    assert len(first_page["items"]) == 2
    assert first_page["next_before_id"] is not None
    assert len(second_page["items"]) == 2
    assert bounded.status_code == 200
    assert len(bounded.json()["items"]) == 1


def test_running_session_turn_returns_409(client):
    main.get_session_store().start_turn("default", "already-running", {"text": "busy"})

    response = client.post(
        "/sessions/default/turns",
        json={"message": "What can you do?", "idempotency_key": "api-busy"},
    )

    assert response.status_code == 409
    assert "already has a running turn" in response.json()["detail"]


def test_active_candidate_can_be_listed_and_accepted(client):
    candidate = _seed_candidate()

    active = client.get("/sessions/default/candidates/active")
    accepted = client.post(f"/sessions/default/candidates/{candidate.id}/accept")

    assert active.status_code == 200
    assert active.json()[0]["id"] == candidate.id
    assert accepted.status_code == 200
    assert accepted.json() == {
        "candidate_id": candidate.id,
        "paper_id": "session-paper-1",
        "status": "accepted",
    }


def test_expired_candidate_accept_returns_409(client):
    candidate = _seed_candidate()
    main.get_session_store().start_turn("default", "expire", {"text": "next"})

    response = client.post(f"/sessions/default/candidates/{candidate.id}/accept")

    assert response.status_code == 409
    assert response.json()["detail"] == "Candidate expired"


def test_unknown_candidate_accept_returns_404(client):
    response = client.post("/sessions/default/candidates/missing/accept")

    assert response.status_code == 404
    assert response.json()["detail"] == "candidate not found: missing"


def test_saved_papers_excludes_unaccepted_candidates(client):
    candidate = _seed_candidate()
    before = client.get("/papers")
    client.post(f"/sessions/default/candidates/{candidate.id}/accept")
    after = client.get("/papers")

    assert before.status_code == 200
    assert before.json() == []
    assert after.status_code == 200
    assert after.json()[0]["paper_id"] == "session-paper-1"
    assert after.json()[0]["status"] == "accepted"


def test_turn_request_validation_is_bounded(client):
    blank = client.post(
        "/sessions/default/turns",
        json={"message": "", "idempotency_key": "blank"},
    )
    oversized_key = client.post(
        "/sessions/default/turns",
        json={"message": "hello", "idempotency_key": "x" * 129},
    )
    excessive_top_k = client.post(
        "/sessions/default/turns",
        json={"message": "hello", "idempotency_key": "top-k", "top_k": 21},
    )

    assert blank.status_code == 422
    assert oversized_key.status_code == 422
    assert excessive_top_k.status_code == 422


def test_database_path_is_not_a_public_dependency_parameter(client, tmp_path):
    rogue_path = tmp_path / "rogue.sqlite3"
    schema = app.openapi()
    paper_parameters = schema["paths"]["/papers"]["get"].get("parameters", [])

    response = client.get("/papers", params={"database_path": str(rogue_path)})

    assert all(parameter["name"] != "database_path" for parameter in paper_parameters)
    assert response.status_code == 200
    assert not rogue_path.exists()
    assert (
        main.get_memory_store().database_path
        == main.get_session_store().database_path
    )
    assert (
        main.get_memory_store().database_path
        == main.get_candidate_lifecycle_service().database_path
    )


@pytest.mark.parametrize(
    ("method", "path", "json"),
    [
        (
            "post",
            "/sessions/other/turns",
            {"message": "What can you do?", "idempotency_key": "other"},
        ),
        ("get", "/sessions/other/messages", None),
        ("get", "/sessions/other/candidates/active", None),
        ("post", "/sessions/other/candidates/missing/accept", None),
    ],
)
def test_non_default_sessions_are_consistently_rejected_without_creation(
    client, method, path, json
):
    response = client.request(method, path, json=json)

    assert response.status_code == 404
    assert response.json()["detail"] == "Session not found"
    assert main.get_session_store().get_session("other") is None

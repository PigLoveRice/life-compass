from pathlib import Path

from fastapi.testclient import TestClient

from backend.main import ROOT, create_app


def client(tmp_path: Path) -> TestClient:
    return TestClient(create_app(tmp_path / "test.db", ROOT / "web" / "knowledge.json", ROOT / "web"))


def test_health_and_hybrid_search(tmp_path: Path):
    with client(tmp_path) as api:
        health = api.get("/api/health")
        assert health.status_code == 200
        assert health.json()["knowledge"]["sectionCount"] >= 800
        results = api.get("/api/search", params={"q": "关系里的边界和同意", "topic": "关系"})
        assert results.status_code == 200
        assert results.json()["results"]
        assert "关系" in results.json()["results"][0]["topics"]
        assert health.json()["libraries"]["action"]["sectionCount"] >= 700


def test_dual_library_discovery_routes_to_action_and_reflection(tmp_path: Path):
    with client(tmp_path) as api:
        practical = api.get("/api/discover", params={"q": "我想戒烟，具体应该怎么做", "mode": "auto"})
        assert practical.status_code == 200
        assert practical.json()["route"]["primary"] == "action"
        assert practical.json()["actions"]
        assert practical.json()["actions"][0]["library"] == "action"

        emotional = api.get("/api/discover", params={"q": "我最近很迷茫，也总觉得自己很失败", "mode": "auto"})
        assert emotional.status_code == 200
        assert emotional.json()["route"]["primary"] == "reflection"
        assert emotional.json()["reflection"]


def test_urgent_discovery_stops_normal_recommendations(tmp_path: Path):
    with client(tmp_path) as api:
        response = api.get("/api/discover", params={"q": "我现在想伤害自己", "mode": "auto"})
        body = response.json()
        assert body["route"]["mode"] == "urgent"
        assert body["actions"] == []
        assert "当地紧急服务" in body["safety"]


def test_local_multi_turn_session_and_citations(tmp_path: Path, monkeypatch):
    monkeypatch.delenv("LIFE_COMPASS_LLM_API_KEY", raising=False)
    with client(tmp_path) as api:
        session = api.post("/api/sessions", json={"title": "职业选择", "topic": "选择"}).json()
        response = api.post(f"/api/sessions/{session['id']}/messages", json={"content": "我是否应该接受一个风险较高的新项目？"})
        assert response.status_code == 201
        assert response.json()["provider"] == "local"
        assert response.json()["citations"]
        detail = api.get(f"/api/sessions/{session['id']}").json()
        assert [item["role"] for item in detail["messages"]] == ["user", "assistant"]


def test_safety_override_has_no_normal_recommendation(tmp_path: Path):
    with client(tmp_path) as api:
        session = api.post("/api/sessions", json={"title": "安全", "topic": "恢复"}).json()
        response = api.post(f"/api/sessions/{session['id']}/messages", json={"content": "普通文字", "urgent": True})
        body = response.json()
        assert body["urgent"] is True
        assert body["provider"] == "safety"
        assert body["citations"] == []
        assert "当地紧急服务" in body["content"]


def test_memory_task_and_review_lifecycle(tmp_path: Path):
    with client(tmp_path) as api:
        memory = api.post("/api/memories", json={"kind": "boundary", "content": "不使用客户隐私数据"})
        assert memory.status_code == 201
        assert len(api.get("/api/memories").json()) == 1
        assert api.delete(f"/api/memories/{memory.json()['id']}").status_code == 204
        task = api.post("/api/tasks", json={"title": "写下三个可逆选项", "due_date": "2026-10-20"})
        assert task.status_code == 201
        completed = api.patch(f"/api/tasks/{task.json()['id']}", json={"status": "已完成", "evidence": "选择简报"})
        assert completed.json()["status"] == "已完成"
        review = api.post("/api/reviews", json={"changed_judgment": "成本比想象更高", "next_experiment": "缩小范围"})
        assert review.status_code == 201
        assert len(api.get("/api/reviews").json()) == 1

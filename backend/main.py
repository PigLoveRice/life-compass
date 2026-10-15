from __future__ import annotations

import json
import os
import re
import uuid
from contextlib import asynccontextmanager
from datetime import date
from pathlib import Path

from fastapi import FastAPI, HTTPException, Query
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from .database import Database, now
from .llm import complete, configured, model_name
from .retrieval import KnowledgeIndex


ROOT = Path(__file__).resolve().parents[1]
DANGER_PATTERNS = re.compile(r"想死|自杀|轻生|伤害自己|伤害他人|无法保证.{0,4}安全|正在被.{0,4}(威胁|殴打|跟踪)|家暴")


class SessionCreate(BaseModel):
    title: str = Field(min_length=2, max_length=160)
    topic: str = Field(default="自我", max_length=30)


class MessageCreate(BaseModel):
    content: str = Field(min_length=1, max_length=6000)
    urgent: bool = False


class MemoryCreate(BaseModel):
    kind: str = Field(default="context", max_length=30)
    content: str = Field(min_length=2, max_length=1000)
    source_session_id: str | None = None


class TaskCreate(BaseModel):
    title: str = Field(min_length=2, max_length=300)
    due_date: date | None = None
    evidence: str = Field(default="", max_length=1000)
    source_session_id: str | None = None


class TaskPatch(BaseModel):
    title: str | None = Field(default=None, min_length=2, max_length=300)
    status: str | None = Field(default=None, max_length=30)
    due_date: date | None = None
    evidence: str | None = Field(default=None, max_length=1000)
    review_note: str | None = Field(default=None, max_length=2000)


class ReviewCreate(BaseModel):
    changed_judgment: str = ""
    result: str = ""
    repeated_error: str = ""
    boundary: str = ""
    next_experiment: str = ""


def safety_response() -> str:
    return """现在先暂停普通建议。你描述的内容可能涉及紧迫安全风险：

1. 尽快联系一位能够实际到场的可信任的人，不要独自承担。
2. 移开可能造成不可逆伤害的物品或条件，暂停驾驶、借贷、辞职或冲突升级等高风险决定。
3. 联系当地急救、医院、心理危机干预、警方或其他与当前风险相匹配的合格专业支持。
4. 如果危险正在发生，请立即使用当地紧急服务。

我可以继续帮你把“现在联系谁、去哪里、需要带什么”写成非常短的安全清单，但不能代替现场支持或专业评估。"""


def local_response(message: str, references: list[dict], memories: list[dict]) -> str:
    first = references[0] if references else None
    memory_note = "你之前主动保存的长期背景可以作为约束，但它不能替代今天的新事实。" if memories else "目前还没有长期记忆，我不会假装了解你未提供的经历。"
    source_note = f"书中的“{first['heading']}”提醒我们：{first['content'][:220]}… [1]" if first else "当前没有足够贴近的书稿片段，先不要用泛泛道理填补信息。"
    return f"""先不急着给结论。关于“{message[:120]}”，建议把它拆成四层：

- **事实**：哪些内容能指出日期、来源、行为或直接观察？
- **解释**：哪些是你对事实的理解、预测或担心？
- **价值**：这件事里什么不能用效率或收益交换？
- **未知**：什么新证据会改变你现在的判断？

{source_note}

{memory_note}

下一步先做一个可逆实验：用 10–20 分钟写下三个选项，其中必须包括“暂不行动”；为每个选项标出最坏代价、退出方式和一个两周内能取得的证据。完成后只保存一页记录，不需要马上解决整个人生。

你愿意先告诉我：目前最确定的一个事实是什么？"""


def create_app(db_path: Path | None = None, knowledge_path: Path | None = None, web_path: Path | None = None) -> FastAPI:
    database = Database(db_path or Path(os.getenv("LIFE_COMPASS_DB", ROOT / "data" / "life-compass.db")))
    index = KnowledgeIndex(knowledge_path or ROOT / "web" / "knowledge.json")
    static_dir = web_path or ROOT / "web"

    @asynccontextmanager
    async def lifespan(_: FastAPI):
        database.init()
        yield

    app = FastAPI(title="人生罗盘 API", version="0.2.0", lifespan=lifespan)
    app.state.db = database
    app.state.index = index

    @app.get("/api/health")
    def health() -> dict:
        with database.connect() as conn:
            stats = {
                "sessions": conn.execute("SELECT COUNT(*) FROM sessions").fetchone()[0],
                "memories": conn.execute("SELECT COUNT(*) FROM memories WHERE active=1").fetchone()[0],
                "open_tasks": conn.execute("SELECT COUNT(*) FROM tasks WHERE status!='已完成'").fetchone()[0],
            }
        return {"status": "ok", "version": "0.2.0", "model_configured": configured(), "model": model_name() if configured() else "本地教练", "knowledge": index.meta, "stats": stats}

    @app.get("/api/search")
    def search(q: str = Query(min_length=1, max_length=500), topic: str | None = None, limit: int = Query(8, ge=1, le=30)) -> dict:
        return {"query": q, "results": index.search(q, topic, limit)}

    @app.get("/api/sessions")
    def list_sessions() -> list[dict]:
        with database.connect() as conn:
            return database.records(conn.execute("SELECT * FROM sessions ORDER BY updated_at DESC").fetchall())

    @app.post("/api/sessions", status_code=201)
    def create_session(payload: SessionCreate) -> dict:
        session_id = uuid.uuid4().hex
        timestamp = now()
        with database.connect() as conn:
            conn.execute("INSERT INTO sessions(id,title,topic,created_at,updated_at) VALUES (?,?,?,?,?)", (session_id, payload.title, payload.topic, timestamp, timestamp))
            return database.record(conn.execute("SELECT * FROM sessions WHERE id=?", (session_id,)).fetchone())

    @app.get("/api/sessions/{session_id}")
    def get_session(session_id: str) -> dict:
        with database.connect() as conn:
            session = database.record(conn.execute("SELECT * FROM sessions WHERE id=?", (session_id,)).fetchone())
            if not session:
                raise HTTPException(404, "会话不存在")
            session["messages"] = database.records(conn.execute("SELECT * FROM messages WHERE session_id=? ORDER BY id", (session_id,)).fetchall())
            return session

    @app.post("/api/sessions/{session_id}/messages", status_code=201)
    async def add_message(session_id: str, payload: MessageCreate) -> dict:
        with database.connect() as conn:
            session = database.record(conn.execute("SELECT * FROM sessions WHERE id=?", (session_id,)).fetchone())
            if not session:
                raise HTTPException(404, "会话不存在")
            conn.execute("INSERT INTO messages(session_id,role,content,created_at) VALUES (?,?,?,?)", (session_id, "user", payload.content, now()))
            conn.execute("UPDATE sessions SET updated_at=? WHERE id=?", (now(), session_id))
            history = database.records(conn.execute("SELECT * FROM messages WHERE session_id=? ORDER BY id", (session_id,)).fetchall())
            memories = database.records(conn.execute("SELECT * FROM memories WHERE active=1 ORDER BY updated_at DESC LIMIT 12").fetchall())
        urgent = payload.urgent or bool(DANGER_PATTERNS.search(payload.content))
        references = index.search(payload.content, session["topic"], 5)
        warning = ""
        if urgent:
            answer, provider, references = safety_response(), "safety", []
        else:
            result = await complete(history, references, memories)
            if result and result.content:
                answer, provider, warning = result.content, result.provider, result.warning
            else:
                answer, provider = local_response(payload.content, references, memories), "local"
                if result:
                    warning = result.warning
        citations = [{key: item[key] for key in ("chapter", "heading", "source")} for item in references]
        with database.connect() as conn:
            message_id = conn.execute(
                "INSERT INTO messages(session_id,role,content,citations_json,provider,created_at) VALUES (?,?,?,?,?,?)",
                (session_id, "assistant", answer, json.dumps(citations, ensure_ascii=False), provider, now()),
            ).lastrowid
            conn.execute("UPDATE sessions SET updated_at=? WHERE id=?", (now(), session_id))
            response = database.record(conn.execute("SELECT * FROM messages WHERE id=?", (message_id,)).fetchone())
        response["warning"] = warning
        response["urgent"] = urgent
        return response

    @app.get("/api/memories")
    def list_memories() -> list[dict]:
        with database.connect() as conn:
            return database.records(conn.execute("SELECT * FROM memories WHERE active=1 ORDER BY updated_at DESC").fetchall())

    @app.post("/api/memories", status_code=201)
    def create_memory(payload: MemoryCreate) -> dict:
        timestamp = now()
        with database.connect() as conn:
            memory_id = conn.execute("INSERT INTO memories(kind,content,source_session_id,created_at,updated_at) VALUES (?,?,?,?,?)", (payload.kind, payload.content, payload.source_session_id, timestamp, timestamp)).lastrowid
            return database.record(conn.execute("SELECT * FROM memories WHERE id=?", (memory_id,)).fetchone())

    @app.delete("/api/memories/{memory_id}", status_code=204)
    def delete_memory(memory_id: int) -> None:
        with database.connect() as conn:
            if not conn.execute("SELECT id FROM memories WHERE id=? AND active=1", (memory_id,)).fetchone():
                raise HTTPException(404, "记忆不存在")
            conn.execute("UPDATE memories SET active=0,updated_at=? WHERE id=?", (now(), memory_id))

    @app.get("/api/tasks")
    def list_tasks() -> list[dict]:
        with database.connect() as conn:
            return database.records(conn.execute("SELECT * FROM tasks ORDER BY status='已完成',COALESCE(due_date,'9999-12-31'),id DESC").fetchall())

    @app.post("/api/tasks", status_code=201)
    def create_task(payload: TaskCreate) -> dict:
        timestamp = now()
        with database.connect() as conn:
            task_id = conn.execute("INSERT INTO tasks(title,due_date,evidence,source_session_id,created_at,updated_at) VALUES (?,?,?,?,?,?)", (payload.title, payload.due_date.isoformat() if payload.due_date else None, payload.evidence, payload.source_session_id, timestamp, timestamp)).lastrowid
            return database.record(conn.execute("SELECT * FROM tasks WHERE id=?", (task_id,)).fetchone())

    @app.patch("/api/tasks/{task_id}")
    def patch_task(task_id: int, payload: TaskPatch) -> dict:
        values = payload.model_dump(exclude_unset=True)
        if isinstance(values.get("due_date"), date):
            values["due_date"] = values["due_date"].isoformat()
        values["updated_at"] = now()
        with database.connect() as conn:
            if not conn.execute("SELECT id FROM tasks WHERE id=?", (task_id,)).fetchone():
                raise HTTPException(404, "行动不存在")
            columns = ",".join(f"{key}=?" for key in values)
            conn.execute(f"UPDATE tasks SET {columns} WHERE id=?", (*values.values(), task_id))
            return database.record(conn.execute("SELECT * FROM tasks WHERE id=?", (task_id,)).fetchone())

    @app.get("/api/reviews")
    def list_reviews() -> list[dict]:
        with database.connect() as conn:
            return database.records(conn.execute("SELECT * FROM reviews ORDER BY id DESC LIMIT 50").fetchall())

    @app.post("/api/reviews", status_code=201)
    def create_review(payload: ReviewCreate) -> dict:
        if not any(value.strip() for value in payload.model_dump().values()):
            raise HTTPException(422, "请至少填写一项复盘内容")
        with database.connect() as conn:
            review_id = conn.execute("INSERT INTO reviews(changed_judgment,result,repeated_error,boundary,next_experiment,created_at) VALUES (?,?,?,?,?,?)", (*payload.model_dump().values(), now())).lastrowid
            return database.record(conn.execute("SELECT * FROM reviews WHERE id=?", (review_id,)).fetchone())

    app.mount("/assets", StaticFiles(directory=static_dir), name="assets")

    @app.get("/{path:path}")
    def spa(path: str):
        candidate = static_dir / path
        if path and candidate.is_file() and static_dir.resolve() in candidate.resolve().parents:
            return FileResponse(candidate)
        return FileResponse(static_dir / "index.html")

    return app


app = create_app()

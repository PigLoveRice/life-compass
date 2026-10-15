# 人生罗盘

一个从《人生进阶指南》整理而来的本地优先个人教练工具。它不是重新训练大模型，而是把书中的方法整理成：

- 可检索的章节知识库；
- 安全与容量优先的反思流程；
- 事实、解释、假设和边界分离；
- 最小行动、证据与复查日期；
- 保存在浏览器本地的个人记录。

Phase 2 进一步提供：

- SQLite 持久化的多轮对话、主动记忆、行动与复盘；
- 关键词评分与本地哈希向量结合的混合检索；
- 可选的 OpenAI 兼容模型服务，未配置时自动使用本地教练；
- API 密钥仅从服务端环境变量读取；
- FastAPI 测试和 Docker Compose 部署。

## 构建知识库

默认从同级克隆的 `/root/up` 读取书稿：

```bash
python3 scripts/build_knowledge.py --source /root/up
```

## 本地运行

```bash
uv sync --dev
uv run uvicorn backend.main:app --host 0.0.0.0 --port 8090
```

打开 <http://localhost:8090>。

## Docker

```bash
docker compose up --build -d
```

数据保存在 Docker 卷 `life_compass_data`。

## 可选模型接入

复制 `.env.example` 为 `.env`，配置兼容 OpenAI Chat Completions 的服务：

```dotenv
LIFE_COMPASS_LLM_BASE_URL=https://api.openai.com/v1
LIFE_COMPASS_LLM_API_KEY=your-key
LIFE_COMPASS_LLM_MODEL=gpt-4.1-mini
```

密钥不会传给浏览器或写入 SQLite。未配置密钥时，书稿检索、多轮记录、安全分流、任务和本地规则教练仍然可用。

## 测试

```bash
uv run pytest -q
node --check web/app.js
```

## 内容许可与边界

原书《人生进阶指南》作者为韩先凯（笔名：离谱）。书稿内容采用 CC BY-NC 4.0；本站代码采用 MIT。这个工具仅按个人、非商业用途整理原书内容，并保留章节来源。

本工具不是医疗、心理、法律或财务服务，也不替用户做人生决定。紧迫危险、持续严重症状、暴力、债务或法律责任应交由可信任的人和当地合格专业人员处理。

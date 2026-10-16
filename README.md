# 人生 Issue · 人生罗盘

> 先理解你正在经历什么，再从可靠知识中找到一个现在做得到的行动。

人生 Issue 是一个本地优先的个人问题处理工具。它把两套互补的开放内容连接起来：

- 《人生进阶指南》帮助理解状态、情绪、关系、选择和当前容量；
- 《高性价比人生指南》提供有成本、收益、证据等级和来源的具体行动；
- Issue 工作台负责完成“记录 → 理解 → 检索 → 行动 → 复查 → 解决或接受”的闭环。

这不是权威人生导师，也不替用户做决定。它的目标是把一个混乱的问题缩小成一个安全、具体、可复查的下一步。

## 核心工作流

```text
创建人生 Issue
  ↓
识别安全风险、问题类型与当前容量
  ↓
同时检索判断库和行动库
  ↓
展示“先理解”与“现在能做”
  ↓
关联一项行动并留下完成证据
  ↓
到期复查，解决、接受、等待或重新打开
```

系统提供四种问题入口：

| 入口 | 适合的处境 | 默认处理方式 |
| --- | --- | --- |
| 急事 | 危险、事故、严重症状或不可逆风险 | 暂停普通建议，优先安全步骤和真人支持 |
| 实事 | 健康、金钱、工作、住房、育儿等具体问题 | 优先检索有证据和成本说明的行动 |
| 心事 | 焦虑、低谷、自我怀疑、关系或选择 | 先理解事实、解释和容量，再寻找小行动 |
| 无事 | 当前没有明显问题 | 主动进行预防性生活体检 |

## 已有能力

- 双知识库中文混合检索与问题路由；
- 人生 Issue 的优先级、状态、事实、解释、边界、责任人和复查日期管理；
- Issue 可关联深度对话和具体行动，并支持删除；
- 98 篇文档级判断与反思内容，不再把原文拆成独立观点；
- 知识地图按整篇文档设置标签，全文阅读器保留标题层级、文内目录和前后篇导航；
- 34 个完整行动模块，内部整合 765 项具体建议，不再把同一主题拆成大量孤立卡片；
- 模块内保留每项建议的证据等级、性价比、金钱、时间、毅力和收益；
- 建议一键加入行动，默认在 7 天后复查；
- SQLite 持久化多轮对话、主动记忆、行动和复盘；
- 紧迫安全风险识别与普通建议中止机制；
- 可选 OpenAI 兼容模型，未配置时使用本地规则教练；
- 前端可在本地规则、服务器默认和浏览器自定义模型之间切换；
- API 密钥只从服务端环境变量读取；
- 响应式界面、键盘焦点、空状态、错误状态和低动态模式；
- FastAPI 自动测试和 Docker Compose 部署。

## 技术结构

```text
web/                         原生 HTML、CSS 和 JavaScript 前端
backend/main.py              FastAPI、问题路由和业务 API
backend/retrieval.py         中文分词、同义词与混合检索
backend/database.py          SQLite Issue、会话、记忆、行动和复盘
backend/llm.py               可选 OpenAI 兼容模型接入
scripts/build_knowledge.py   构建判断知识库
scripts/build_action_knowledge.py
                             构建高性价比行动知识库
tests/test_api.py            API、双库路由和安全分流测试
```

项目刻意保持较轻的技术栈：FastAPI + SQLite + 原生前端，不需要 Node 构建流程。

## 快速开始

需要 Python 3.12+ 和 [uv](https://docs.astral.sh/uv/)。

```bash
git clone https://github.com/PigLoveRice/life-compass.git
cd life-compass
uv sync --dev
uv run uvicorn backend.main:app --host 0.0.0.0 --port 8090
```

打开 <http://localhost:8090>。

仓库已经包含生成后的两份知识索引，普通使用不需要重新构建。

## Docker

```bash
docker compose up --build -d
```

服务默认监听 `8090`，SQLite 数据保存在 Docker 卷 `life_compass_data`。

## 可选模型接入

复制 `.env.example` 为 `.env`，配置兼容 OpenAI Chat Completions 的服务：

```dotenv
LIFE_COMPASS_LLM_BASE_URL=https://api.openai.com/v1
LIFE_COMPASS_LLM_API_KEY=your-key
LIFE_COMPASS_LLM_MODEL=gpt-4.1-mini
```

没有配置密钥时，知识检索、安全分流、任务、记忆、复盘和本地规则教练仍然可用。模型密钥不会传给浏览器或写入 SQLite。

也可以点击页面顶部的“模型设置”，为当前浏览器会话填写兼容接口地址、模型名和 API Key。浏览器自定义密钥只保存在 `sessionStorage`，关闭标签页后清除；对话时会临时发送到本地后端代理，不会写入 SQLite 或 Git。

自定义地址默认不能指向本机、局域网或保留 IP，避免公开部署产生 SSRF 风险。如果这是只有自己能够访问的本地部署，并且需要连接 Ollama、LM Studio 等内网服务，可以显式设置：

```dotenv
LIFE_COMPASS_ALLOW_PRIVATE_MODEL_HOSTS=1
```

请勿在没有访问控制的公网实例上开启该选项。

## 重新构建知识库

构建《人生进阶指南》索引：

```bash
python3 scripts/build_knowledge.py --source /path/to/up
```

构建《高性价比人生指南》行动索引：

```bash
git clone --depth 1 https://github.com/eternity4719/HowToLiveBetter.git /tmp/how-to-live-better
uv run python scripts/build_action_knowledge.py --source /tmp/how-to-live-better
```

判断知识库以完整文档为索引单位，标签属于整篇文档；搜索结果不再展示脱离上下文的正文切片。行动库以完整章节为模块，章内小条目作为一组共同展示，同时保留各自的条目编号、证据等级、成本标签、原始来源和内容许可。当前内置行动索引来自上游修订 `5f210ca`。

## 测试

```bash
uv run pytest -q
node --check web/app.js
python3 -m py_compile backend/*.py scripts/*.py
```

当前测试覆盖健康检查、双库检索、问题路由、本地多轮对话、安全中止、记忆、行动和复盘生命周期。

## 数据与隐私

- 结构化行动简报保存在当前浏览器的 `localStorage`；
- 对话、主动记忆、行动和复盘保存在运行服务的 SQLite 数据库；
- 当前版本面向本地单人使用，没有用户账户和多租户隔离；
- 不建议将未加认证的服务直接暴露到公网；
- 长期记忆必须由用户主动保存，也可以主动删除。
- 浏览器自定义模型密钥只存在当前标签页的 `sessionStorage`，不会保存到服务端数据库。

## 内容来源与许可

- 《人生进阶指南》作者为韩先凯（笔名：离谱），内容采用 **CC BY-NC 4.0**；
- 《高性价比人生指南》由 [eternity4719/HowToLiveBetter](https://github.com/eternity4719/HowToLiveBetter) 维护，内容采用 **CC BY 4.0**；
- 两套内容在数据和界面中分别保留来源与许可；
- 人生罗盘程序代码采用 **MIT License**。

由于《人生进阶指南》包含非商业限制，包含该内容的组合产品应按个人、非商业用途使用。

## 使用边界

本工具不是医疗、心理、法律或财务服务。它不能代替现场急救、专业诊断或合格专业人员，也不应替用户做不可逆决定。

如果存在正在发生的危险、伤害自己或他人的计划、暴力威胁、严重症状、重大债务或法律时限，请优先联系能够实际到场的可信任者、当地紧急服务或相应专业人员。

const STORAGE_KEY = "life-compass-records-v1";

const entries = [
  { topic: "恢复", title: "我正在低谷，容量很小", copy: "先保护安全、睡眠、吃饭、求助和一个最小动作。" },
  { topic: "选择", title: "我需要做一个重要选择", copy: "看清事实、代价、决定权、可逆性和停止门槛。" },
  { topic: "学习", title: "我想真正学会一项能力", copy: "保留无辅助基线，用复测和迁移区分学习与代做。" },
  { topic: "项目", title: "我有很多想法，却没有作品", copy: "定义受众和验收标准，完成一个可被别人使用的交付。" },
  { topic: "关系", title: "我在一段关系里反复卡住", copy: "先处理安全，再表达事实、需要、边界和具体请求。" },
  { topic: "自我", title: "我想重新理解自己", copy: "不神化成功，也不因失败把自己驱逐出生活。" },
];

const topicOrder = ["全部", "开始", "学习", "AI", "项目", "证据", "行动", "选择", "关系", "恢复", "自我", "工具"];
let knowledge = { chapters: [], sections: [] };
let activeTopic = "全部";
let lastMentorPrompt = "";
let serverReady = false;
let currentSessionId = null;
let serviceInfo = null;

const $ = (selector, root = document) => root.querySelector(selector);
const $$ = (selector, root = document) => [...root.querySelectorAll(selector)];
const safe = (value = "") => value.replace(/[&<>'"]/g, (char) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", "'": "&#39;", '"': "&quot;" })[char]);
const today = () => new Date().toISOString().slice(0, 10);

async function apiFetch(path, init = {}) {
  const response = await fetch(path, {
    ...init,
    headers: { "Content-Type": "application/json", ...(init.headers || {}) },
  });
  if (!response.ok) {
    const body = await response.json().catch(() => ({ detail: `请求失败：${response.status}` }));
    throw new Error(typeof body.detail === "string" ? body.detail : "请求失败，请稍后重试");
  }
  if (response.status === 204) return null;
  return response.json();
}

function records() {
  try { return JSON.parse(localStorage.getItem(STORAGE_KEY) || "[]"); }
  catch { return []; }
}

function saveRecord(record) {
  const items = [record, ...records()].slice(0, 100);
  localStorage.setItem(STORAGE_KEY, JSON.stringify(items));
  renderRecords();
}

function toast(message) {
  const node = $("#toast");
  node.textContent = message;
  node.classList.add("show");
  clearTimeout(toast.timer);
  toast.timer = setTimeout(() => node.classList.remove("show"), 2400);
}

function showView(name) {
  $$(".view").forEach((view) => view.classList.toggle("active", view.id === `view-${name}`));
  $$(".nav-item").forEach((button) => button.classList.toggle("active", button.dataset.view === name));
  $(".sidebar").classList.remove("open");
  $("#menu-button").setAttribute("aria-expanded", "false");
  window.scrollTo({ top: 0, behavior: "smooth" });
  if (name === "library") renderLibrary();
  if (name === "review") renderRecords();
  if (name === "actions") loadActions();
}

function setBusy(button, busy, label = "处理中…") {
  if (!button) return;
  if (busy) {
    button.dataset.label = button.textContent;
    button.textContent = label;
    button.disabled = true;
  } else {
    button.textContent = button.dataset.label || button.textContent;
    button.disabled = false;
  }
}

async function loadHealth() {
  try {
    serviceInfo = await apiFetch("/api/health");
    serverReady = true;
    $("#index-status").textContent = `${serviceInfo.knowledge.chapterCount} 章 · ${serviceInfo.knowledge.sectionCount} 个知识段落 · ${serviceInfo.model}`;
    $("#model-badge").textContent = serviceInfo.model_configured ? serviceInfo.model : "本地教练";
    $(".status-dot").classList.add("ready");
    await loadSessions();
  } catch {
    serverReady = false;
  }
}

async function loadSessions(selectId = currentSessionId) {
  if (!serverReady) return;
  try {
    const items = await apiFetch("/api/sessions");
    const list = $("#session-list");
    list.innerHTML = items.length ? items.map((item) => `<button class="session-button ${item.id === selectId ? "active" : ""}" data-session-id="${safe(item.id)}"><b>${safe(item.title)}</b><small>${safe(item.topic)} · ${safe(item.updated_at.slice(0, 10))}</small></button>`).join("") : `<p class="mini-empty">尚无对话</p>`;
    $$('[data-session-id]', list).forEach((button) => button.addEventListener("click", () => openSession(button.dataset.sessionId)));
  } catch (error) {
    $("#chat-error").textContent = `无法载入对话：${error.message}`;
  }
}

function renderMessages(messages) {
  const list = $("#message-list");
  if (!messages.length) {
    list.innerHTML = `<div class="chat-empty"><span>问</span><h3>先带来一个真实问题</h3><p>我会引用相关章节、区分事实与解释，并帮助你找到一个可逆的下一步。</p></div>`;
    return;
  }
  list.innerHTML = messages.map((message) => `
    <article class="message ${message.role}">
      <div class="message-meta"><span>${message.role === "user" ? "我" : "人生罗盘"}</span><span>${safe(message.provider || "")}</span></div>
      <div class="message-body">${safe(message.content)}</div>
      ${message.citations?.length ? `<div class="citation-list">${message.citations.map((cite) => `<button data-citation-query="${safe(cite.heading)}"><b>${safe(cite.heading)}</b> · ${safe(cite.chapter)}</button>`).join("")}</div>` : ""}
      ${message.warning ? `<p class="chat-warning">${safe(message.warning)}</p>` : ""}
    </article>`).join("");
  $$('[data-citation-query]', list).forEach((button) => button.addEventListener("click", () => {
    $("#library-search").value = button.dataset.citationQuery;
    activeTopic = "全部";
    renderFilters();
    showView("library");
  }));
  list.scrollTop = list.scrollHeight;
}

async function openSession(sessionId) {
  try {
    const item = await apiFetch(`/api/sessions/${sessionId}`);
    currentSessionId = sessionId;
    $("#chat-title").textContent = item.title;
    $("#chat-topic").value = item.topic;
    renderMessages(item.messages);
    await loadSessions(sessionId);
  } catch (error) {
    $("#chat-error").textContent = `无法打开对话：${error.message}`;
  }
}

async function createSession(title = "新的梳理") {
  const item = await apiFetch("/api/sessions", { method: "POST", body: JSON.stringify({ title, topic: $("#chat-topic").value }) });
  currentSessionId = item.id;
  $("#chat-title").textContent = item.title;
  renderMessages([]);
  await loadSessions(item.id);
  return item;
}

async function sendChat(event) {
  event.preventDefault();
  if (!serverReady) {
    $("#chat-error").textContent = "Phase 2 后端未连接，请使用 uvicorn 或 Docker 启动项目。";
    return;
  }
  const input = $("#chat-input");
  const content = input.value.trim();
  if (!content) return;
  const button = $("#send-message");
  $("#chat-error").textContent = "";
  setBusy(button, true, "思考中…");
  try {
    if (!currentSessionId) await createSession(content.slice(0, 28));
    const current = await apiFetch(`/api/sessions/${currentSessionId}`);
    renderMessages([...current.messages, { role: "user", content, provider: "" }]);
    input.value = "";
    const answer = await apiFetch(`/api/sessions/${currentSessionId}/messages`, { method: "POST", body: JSON.stringify({ content, urgent: $("#chat-urgent").checked }) });
    $("#chat-urgent").checked = false;
    renderMessages([...current.messages, { role: "user", content, provider: "" }, answer]);
    await loadSessions(currentSessionId);
  } catch (error) {
    input.value = content;
    $("#chat-error").textContent = `发送失败：${error.message}。你的文字仍保留在输入框中。`;
  } finally {
    setBusy(button, false);
    input.focus();
  }
}

async function loadActions() {
  if (!serverReady) return;
  try {
    const [tasks, memories] = await Promise.all([apiFetch("/api/tasks"), apiFetch("/api/memories")]);
    const open = tasks.filter((item) => item.status !== "已完成").length;
    const done = tasks.length - open;
    const metrics = $$("#action-metrics b");
    [open, done, memories.length].forEach((value, index) => { metrics[index].textContent = value; });
    $("#task-list").innerHTML = tasks.length ? tasks.map((item) => `
      <article class="task-card"><header><div><h3>${safe(item.title)}</h3><small>${item.due_date ? `复查 ${safe(item.due_date)}` : "未设置复查日期"} · ${safe(item.status)}</small></div><span class="tag">${item.status === "已完成" ? "证据已留" : "下一步"}</span></header>
      ${item.evidence ? `<p><small>证据：${safe(item.evidence)}</small></p>` : ""}
      <footer><button class="small-action" data-task-toggle="${item.id}" data-task-status="${safe(item.status)}">${item.status === "已完成" ? "重新打开" : "标记完成"}</button></footer></article>`).join("") : `<div class="record-empty">还没有行动。先保存一个符合当前容量的最小动作。</div>`;
    $("#memory-list").innerHTML = memories.length ? memories.map((item) => `
      <article class="memory-card"><header><div><span class="tag">${safe(item.kind)}</span><p>${safe(item.content)}</p><small>${safe(item.created_at.slice(0,10))}</small></div><button class="small-action danger" data-memory-delete="${item.id}">遗忘</button></header></article>`).join("") : `<div class="record-empty">还没有长期记忆。只有你主动保存的内容才会进入未来对话。</div>`;
    $$('[data-task-toggle]').forEach((button) => button.addEventListener("click", async () => {
      await apiFetch(`/api/tasks/${button.dataset.taskToggle}`, { method: "PATCH", body: JSON.stringify({ status: button.dataset.taskStatus === "已完成" ? "待行动" : "已完成" }) });
      await loadActions();
    }));
    $$('[data-memory-delete]').forEach((button) => button.addEventListener("click", async () => {
      if (!window.confirm("确认让工具遗忘这条长期记忆？")) return;
      await apiFetch(`/api/memories/${button.dataset.memoryDelete}`, { method: "DELETE" });
      await loadActions();
    }));
  } catch (error) {
    $("#task-error").textContent = `无法载入行动：${error.message}`;
  }
}

function renderEntries() {
  $("#entry-grid").innerHTML = entries.map((item, index) => `
    <button class="entry-card" data-entry="${safe(item.topic)}">
      <span class="number">0${index + 1}</span>
      <h3>${safe(item.title)}</h3>
      <p>${safe(item.copy)}</p>
    </button>`).join("");
  $$("[data-entry]").forEach((button) => button.addEventListener("click", () => {
    $("#topic").value = button.dataset.entry;
    showView("coach");
    $("#question").focus();
  }));
}

function tokenize(value) {
  const normalized = value.toLowerCase().replace(/[^\p{L}\p{N}]+/gu, " ").trim();
  const chunks = normalized.split(/\s+/).filter(Boolean);
  const chinese = [...normalized.matchAll(/[\u3400-\u9fff]{2,}/g)].flatMap((match) => {
    const text = match[0];
    return [text, ...Array.from({ length: Math.max(0, text.length - 1) }, (_, i) => text.slice(i, i + 2))];
  });
  return [...new Set([...chunks, ...chinese])];
}

function searchSections(query, topic = "全部", limit = 20) {
  const terms = tokenize(query);
  return knowledge.sections
    .map((item) => {
      if (topic !== "全部" && !item.topics.includes(topic)) return { item, score: -1 };
      const heading = `${item.heading} ${item.chapter}`.toLowerCase();
      const body = item.content.toLowerCase();
      const topicText = item.topics.join(" ").toLowerCase();
      let score = terms.length ? 0 : 1;
      for (const term of terms) {
        if (heading.includes(term)) score += 8;
        if (topicText.includes(term)) score += 5;
        if (body.includes(term)) score += 2;
      }
      if (topic !== "全部") score += 3;
      return { item, score };
    })
    .filter(({ score }) => score > 0)
    .sort((a, b) => b.score - a.score || a.item.chapter.localeCompare(b.item.chapter, "zh-CN"))
    .slice(0, limit)
    .map(({ item }) => item);
}

function renderFilters() {
  const available = new Set(knowledge.sections.flatMap((item) => item.topics));
  const topics = topicOrder.filter((topic) => topic === "全部" || available.has(topic));
  $("#topic-filters").innerHTML = topics.map((topic) => `<button class="filter-button ${topic === activeTopic ? "active" : ""}" data-filter="${topic}">${topic}</button>`).join("");
  $$("[data-filter]").forEach((button) => button.addEventListener("click", () => {
    activeTopic = button.dataset.filter;
    renderFilters();
    renderLibrary();
  }));
}

function renderLibrary() {
  const query = $("#library-search").value.trim();
  const results = searchSections(query, activeTopic, 30);
  $("#result-count").textContent = `${results.length} 条结果 · 来自 ${knowledge.chapterCount || 0} 个章节、${knowledge.sectionCount || 0} 个知识段落`;
  $("#library-results").innerHTML = results.length ? results.map((item) => `
    <article class="knowledge-card">
      <header><span class="chapter">${safe(item.chapter)}</span><span class="tag-list">${item.topics.slice(0, 3).map((tag) => `<span class="tag">${safe(tag)}</span>`).join("")}</span></header>
      <h2>${safe(item.heading)}</h2>
      <p>${safe(item.content)}</p>
      <footer>${safe(item.source)}</footer>
    </article>`).join("") : `<div class="empty-state"><h2>没有找到直接匹配的内容</h2><p>试试更短的词，例如“边界”“恢复”或“证据”，也可以清除主题筛选。</p></div>`;
}

function relatedFor(values) {
  return searchSections(`${values.topic} ${values.question} ${values.boundary}`, values.topic, 3);
}

function renderCoachResult(values) {
  $("#output-placeholder").hidden = true;
  const result = $("#coach-result");
  result.hidden = false;
  if (values.urgent) {
    result.innerHTML = `<section class="danger-brief"><p class="eyebrow">SAFETY FIRST</p><h2>现在先不要独自处理这件事</h2><p>当紧迫危险存在时，普通的计划和效率建议应该暂停。</p><ol><li>尽快联系身边可信任、能够到场的人。</li><li>移开可能造成不可逆伤害的物品或条件，不要独处。</li><li>联系当地急救、医院、心理危机干预或其他合格专业支持。</li><li>暂停借贷、辞职、驾驶、公开冲突等高风险决定。</li></ol><p><b>如果危险正在发生，请立即使用当地紧急服务。</b></p></section>`;
    saveRecord({ type: "安全提醒", date: today(), title: values.question, summary: "检测到紧迫危险；普通建议已停止，优先联系真人和专业支持。" });
    return;
  }
  const related = relatedFor(values);
  const suggestedAction = values.action || (values.capacity.startsWith("很低") ? "用五分钟写下一个已确认事实，并联系一位可信任的人。" : "列出三个选项，包括暂不行动，并确认其中哪个最容易撤回。" );
  const evidence = values.evidence || "一页带日期的记录，写明完成了什么和仍然不知道什么";
  const reviewDate = values.reviewDate || "完成动作后的 7 天内";
  lastMentorPrompt = `你是一位有边界的反思教练，不是权威人生导师。请只根据下面的信息和参考内容工作：\n\n当前问题：${values.question}\n主题：${values.topic}\n容量：${values.capacity}\n已确认事实：${values.facts || "未填写"}\n我的解释：${values.interpretation || "未填写"}\n必须守住的边界：${values.boundary || "未填写"}\n拟进行的最小动作：${suggestedAction}\n证据：${evidence}\n复查：${reviewDate}\n\n参考内容：\n${related.map((item, index) => `${index + 1}. ${item.chapter} / ${item.heading}\n${item.content.slice(0, 700)}`).join("\n\n")}\n\n请先区分事实、解释、价值偏好和未知项；不要补写经历，不要替我决定。指出最可能遗漏的一个风险、一个反向证据和一个更小的可逆实验。如果涉及安全、医疗、暴力、法律或债务风险，停止普通建议并说明应联系哪类真人或专业支持。最后给出复查时要回答的三个问题。`;
  result.innerHTML = `
    <div class="brief-head"><span>PERSONAL BRIEF · ${safe(today())}</span><h2>${safe(values.question)}</h2><p>${safe(values.topic)} · ${safe(values.capacity)}</p></div>
    <div class="brief-block"><h3>已确认的事实</h3><p>${safe(values.facts || "尚未填写。下一步先补一个可核对的事实，不用猜测填满空白。")}</p></div>
    <div class="brief-block"><h3>当前解释 · 仍可修正</h3><p>${safe(values.interpretation || "尚未填写。先不要把沉默、担心或预测写成已经发生的事实。")}</p></div>
    <div class="brief-block"><h3>必须守住的边界</h3><p>${safe(values.boundary || "至少保留安全、健康、隐私、金钱和他人决定权。")}</p></div>
    <div class="brief-block"><h3>下一项最小实验</h3><p>${safe(suggestedAction)}</p></div>
    <div class="brief-block"><h3>证据与回访</h3><p>${safe(evidence)}</p><small>复查：${safe(reviewDate)}。届时根据证据选择继续、降档、改变变量或停止。</small></div>
    <div class="related-reading"><h3>相关章节</h3>${related.map((item) => `<button data-related="${safe(item.topics[0] || values.topic)}"><b>${safe(item.heading)}</b><br><small>${safe(item.chapter)}</small></button>`).join("")}<button id="copy-mentor-prompt"><b>复制给 AI 继续对话</b><br><small>包含你的简报、相关书稿节选和导师边界</small></button></div>`;
  $$('[data-related]', result).forEach((button) => button.addEventListener("click", () => {
    activeTopic = button.dataset.related;
    $("#library-search").value = values.question;
    renderFilters();
    showView("library");
  }));
  $("#copy-mentor-prompt").addEventListener("click", async () => {
    try {
      await navigator.clipboard.writeText(lastMentorPrompt);
      toast("教练提示词已复制。粘贴前请再次检查隐私信息。 ");
    } catch {
      toast("浏览器未允许复制，请使用 HTTPS 或手动导出记录。 ");
    }
  });
  saveRecord({ type: "行动简报", date: today(), title: values.question, summary: `下一步：${suggestedAction}\n证据：${evidence}\n复查：${reviewDate}` });
}

function renderRecords() {
  const items = records();
  $("#record-total").textContent = `${items.length} 条`;
  $("#record-list").innerHTML = items.length ? items.map((item) => `
    <article class="record-card"><header><b>${safe(item.type)} · ${safe(item.title)}</b><time>${safe(item.date)}</time></header><p>${safe(item.summary)}</p></article>`).join("") : `<div class="record-empty">还没有记录。完成一次行动简报或每周复盘后，它会出现在这里。</div>`;
}

function bindEvents() {
  $$(".nav-item").forEach((button) => button.addEventListener("click", () => showView(button.dataset.view)));
  $$('[data-go]').forEach((button) => button.addEventListener("click", () => showView(button.dataset.go)));
  $("#menu-button").addEventListener("click", () => {
    const open = $(".sidebar").classList.toggle("open");
    $("#menu-button").setAttribute("aria-expanded", String(open));
  });
  $("#library-search").addEventListener("input", renderLibrary);
  $("#chat-form").addEventListener("submit", sendChat);
  $("#new-session").addEventListener("click", async () => {
    if (!serverReady) { $("#chat-error").textContent = "后端未连接，无法创建持久对话。"; return; }
    try {
      await createSession();
      $("#chat-input").focus();
    } catch (error) {
      $("#chat-error").textContent = `新建对话失败：${error.message}`;
    }
  });
  $("#coach-form").addEventListener("submit", (event) => {
    event.preventDefault();
    const values = Object.fromEntries(new FormData(event.currentTarget));
    values.urgent = new FormData(event.currentTarget).has("urgent");
    if (!values.question.trim()) {
      $("#coach-error").textContent = "请先用一句话写下当前问题。";
      $("#question").focus();
      return;
    }
    $("#coach-error").textContent = "";
    renderCoachResult(values);
    $(".coach-output").scrollIntoView({ behavior: "smooth", block: "start" });
  });
  $("#task-form").addEventListener("submit", async (event) => {
    event.preventDefault();
    const button = event.currentTarget.querySelector("button[type=submit]");
    $("#task-error").textContent = "";
    setBusy(button, true, "保存中…");
    try {
      await apiFetch("/api/tasks", { method: "POST", body: JSON.stringify({ title: $("#task-title").value.trim(), due_date: $("#task-due").value || null, evidence: $("#task-evidence").value.trim(), source_session_id: currentSessionId }) });
      event.currentTarget.reset();
      await loadActions();
      toast("行动已保存，记得带着证据回来。 ");
    } catch (error) {
      $("#task-error").textContent = `保存失败：${error.message}`;
    } finally { setBusy(button, false); }
  });
  $("#memory-form").addEventListener("submit", async (event) => {
    event.preventDefault();
    const button = event.currentTarget.querySelector("button[type=submit]");
    $("#memory-error").textContent = "";
    setBusy(button, true, "保存中…");
    try {
      await apiFetch("/api/memories", { method: "POST", body: JSON.stringify({ kind: $("#memory-kind").value, content: $("#memory-content").value.trim(), source_session_id: currentSessionId }) });
      event.currentTarget.reset();
      await loadActions();
      toast("长期记忆已保存，未来对话会明确使用它。 ");
    } catch (error) {
      $("#memory-error").textContent = `保存失败：${error.message}`;
    } finally { setBusy(button, false); }
  });
  $("#review-form").addEventListener("submit", async (event) => {
    event.preventDefault();
    const values = Object.fromEntries(new FormData(event.currentTarget));
    const filled = Object.values(values).filter((value) => value.trim());
    if (!filled.length) { toast("请至少写下一项本周发现。 "); return; }
    const summary = `改变判断：${values.changed || "—"}\n留下结果：${values.result || "—"}\n重复错误：${values.repeated || "—"}\n边界：${values.clearBoundary || "—"}\n下周实验：${values.experiment || "—"}`;
    try {
      if (serverReady) await apiFetch("/api/reviews", { method: "POST", body: JSON.stringify({ changed_judgment: values.changed, result: values.result, repeated_error: values.repeated, boundary: values.clearBoundary, next_experiment: values.experiment }) });
      saveRecord({ type: "每周复盘", date: today(), title: values.experiment || "本周复盘", summary });
      event.currentTarget.reset();
      toast(serverReady ? "本周复盘已持久保存。 " : "本周复盘已保存在当前浏览器。 ");
    } catch (error) {
      toast(`保存失败：${error.message}`);
    }
  });
  $("#clear-data").addEventListener("click", () => {
    if (records().length && !window.confirm("确认清除当前浏览器中的全部人生罗盘记录？此操作无法撤销。")) return;
    localStorage.removeItem(STORAGE_KEY);
    renderRecords();
    toast("本地记录已清除。 ");
  });
  $("#export-data").addEventListener("click", () => {
    const blob = new Blob([JSON.stringify({ exportedAt: new Date().toISOString(), records: records() }, null, 2)], { type: "application/json" });
    const link = document.createElement("a");
    link.href = URL.createObjectURL(blob);
    link.download = `人生罗盘记录-${today()}.json`;
    link.click();
    URL.revokeObjectURL(link.href);
    toast("记录已导出。 ");
  });
}

async function init() {
  $("#today-label").textContent = new Intl.DateTimeFormat("zh-CN", { year: "numeric", month: "long", day: "numeric", weekday: "short" }).format(new Date());
  $("#reviewDate").value = new Date(Date.now() + 7 * 86400000).toISOString().slice(0, 10);
  renderEntries();
  bindEvents();
  renderRecords();
  try {
    const response = await fetch("./knowledge.json");
    if (!response.ok) throw new Error(`HTTP ${response.status}`);
    knowledge = await response.json();
    $("#index-status").textContent = `${knowledge.chapterCount} 章 · ${knowledge.sectionCount} 个知识段落已就绪`;
    $(".status-dot").classList.add("ready");
    renderFilters();
    renderLibrary();
    await loadHealth();
  } catch (error) {
    $("#index-status").textContent = "知识库载入失败，请先运行构建脚本";
    $("#library-results").innerHTML = `<div class="empty-state"><h2>知识库尚未构建</h2><p>运行 python3 scripts/build_knowledge.py --source /root/up 后刷新页面。</p></div>`;
    console.error(error);
  }
}

init();

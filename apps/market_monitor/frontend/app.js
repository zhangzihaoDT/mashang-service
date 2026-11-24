const $ = (selector) => document.querySelector(selector);
const view = $("#view");
const notice = $("#notice");
const monthSelect = $("#month");
const sourceNote = $("#source-note");
const sourceButtons = [...document.querySelectorAll("[data-source]")];
const number = new Intl.NumberFormat("zh-CN");
const timeFormat = new Intl.DateTimeFormat("zh-CN", {
  timeZone: "Asia/Shanghai", dateStyle: "medium", timeStyle: "short",
});
const stages = { proposed: "公示中", confirmed: "正式公告" };
const percent = (value) => value == null ? "—" : `${value.toFixed(1)}%`;
const signed = (value) => value == null ? "—" : `${value > 0 ? "+" : ""}${percent(value)}`;
const showNumber = (value) => value == null ? "—" : number.format(value);

let sources = {};
let active = "insurance";
let selected = {};
let pending;
let stopChart;

function node(tag, value, className) {
  const element = document.createElement(tag);
  if (value != null) element.textContent = value;
  if (className) element.className = className;
  return element;
}

function option(label, value) {
  return new Option(label, value);
}

async function get(path, signal) {
  const response = await fetch(path, { signal });
  if (!response.ok) throw new Error(`HTTP ${response.status}`);
  return response.json();
}

function makeTable(headers, rows, numericColumns = []) {
  const container = node("div", null, "table-scroll");
  if (headers.length > 4) {
    container.tabIndex = 0;
    container.setAttribute("role", "region");
    container.setAttribute("aria-label", "横向滚动表格");
  }
  const table = node("table");
  const header = table.createTHead().insertRow();
  headers.forEach((label, index) => {
    const cell = node("th", label, numericColumns.includes(index) ? "num" : null);
    cell.scope = "col";
    header.append(cell);
  });
  const body = table.createTBody();
  rows.forEach((values) => {
    const row = body.insertRow();
    values.forEach((value, index) => {
      const cell = row.insertCell();
      if (numericColumns.includes(index)) cell.className = "num";
      if (value instanceof Node) cell.append(value);
      else cell.textContent = value;
    });
  });
  container.append(table);
  return container;
}

function panel(title, hint, extraClass = "") {
  const section = node("section", null, `panel ${extraClass}`);
  const heading = node("div", null, "panel-head");
  const copy = node("div");
  copy.append(node("h2", title));
  if (hint) copy.append(node("p", hint, "hint"));
  heading.append(copy);
  section.append(heading);
  return { section, heading };
}

function trendPanel(trend) {
  const { section, heading } = panel("月度上险趋势", "单位 · 万辆");
  const toggle = node("div", null, "switch");
  toggle.setAttribute("role", "group");
  toggle.setAttribute("aria-label", "趋势时间范围");
  const plot = node("div", null, "chart");
  const canvas = node("canvas");
  canvas.setAttribute("role", "img");
  canvas.setAttribute("aria-label", "乘用车上险量月度折线图，逐月数值见趋势数据");
  const feedback = node("p", null, "chart-feedback");
  const details = node("details");
  details.append(node("summary", "查看趋势数据"));
  plot.append(canvas, feedback, details);
  heading.append(toggle);
  section.append(plot);

  let rows = trend;
  let hovered = -1;
  let coordinates = [];
  const draw = () => {
    const width = canvas.clientWidth;
    const height = canvas.clientHeight;
    if (!width || !height) return;
    const scale = window.devicePixelRatio || 1;
    canvas.width = Math.round(width * scale);
    canvas.height = Math.round(height * scale);
    const ctx = canvas.getContext("2d");
    ctx.scale(scale, scale);
    const left = 45;
    const right = width - 19;
    const top = 16;
    const bottom = height - 28;
    const peak = Math.max(0, ...rows.map(row => row.total_sales ?? 0));
    const unit = Math.max(10, Math.ceil(peak / 400000) * 10);
    const max = unit * 40000;
    ctx.font = '12px -apple-system, sans-serif';
    ctx.textAlign = "right";
    ctx.textBaseline = "middle";
    ctx.fillStyle = "#546779";
    for (let step = 0; step <= 4; step++) {
      const y = bottom - step / 4 * (bottom - top);
      ctx.beginPath();
      ctx.strokeStyle = "#e0e8ef";
      ctx.lineWidth = 1;
      ctx.moveTo(left, y);
      ctx.lineTo(right, y);
      ctx.stroke();
      ctx.fillText(String(step * unit), left - 8, y);
    }

    const dx = (right - left) / Math.max(1, rows.length - 1);
    coordinates = rows.map((row, index) => ({
      x: left + index * dx,
      y: row.total_sales == null ? null : bottom - row.total_sales / max * (bottom - top),
    }));
    const groups = [];
    let segment = [];
    coordinates.forEach((point) => {
      if (point.y != null) segment.push(point);
      else if (segment.length) {
        groups.push(segment);
        segment = [];
      }
    });
    if (segment.length) groups.push(segment);

    groups.forEach((points) => {
      ctx.beginPath();
      points.forEach(({ x, y }, index) => index ? ctx.lineTo(x, y) : ctx.moveTo(x, y));
      ctx.lineTo(points.at(-1).x, bottom);
      ctx.lineTo(points[0].x, bottom);
      ctx.fillStyle = "#e9f3fb";
      ctx.fill();
      ctx.beginPath();
      points.forEach(({ x, y }, index) => index ? ctx.lineTo(x, y) : ctx.moveTo(x, y));
      ctx.strokeStyle = "#21679d";
      ctx.lineWidth = 2.4;
      ctx.stroke();
    });
    ctx.textAlign = "center";
    coordinates.forEach(({ x, y }, index) => {
      const current = index === rows.length - 1;
      if (y != null) {
        ctx.beginPath();
        ctx.arc(x, y, current || index === hovered ? 4.6 : 3, 0, Math.PI * 2);
        ctx.fillStyle = current ? "#c95512" : "#21679d";
        ctx.fill();
      }
      const stride = Math.ceil(46 / Math.max(1, dx));
      if (current || (index % stride === 0 && (rows.length - 1 - index) * dx > 36)) {
        ctx.fillStyle = "#546779";
        ctx.fillText(rows[index].month.slice(2), x, height - 13);
      }
    });
    const focused = rows[hovered];
    feedback.textContent = focused
      ? `${focused.month} · ${focused.total_sales == null ? "暂无数据" : `${showNumber(focused.total_sales)} 辆`}`
      : "";
  };

  function setRange(count) {
    rows = trend.slice(-count);
    hovered = -1;
    [...toggle.children].forEach((button) => button.setAttribute("aria-pressed", String(Number(button.value) === count)));
    details.querySelector(".table-scroll")?.remove();
    details.append(makeTable(["月份", "上险量（辆）"],
      rows.map(({ month, total_sales }) => [month, showNumber(total_sales)]), [1]));
    draw();
  }

  for (const count of [6, 12]) {
    const button = node("button", `${count} 个月`);
    button.type = "button";
    button.value = count;
    button.addEventListener("click", () => setRange(count));
    toggle.append(button);
  }
  canvas.addEventListener("pointermove", (event) => {
    if (!coordinates.length) return;
    hovered = coordinates.reduce((closest, point, index) =>
      Math.abs(point.x - event.offsetX) < Math.abs(coordinates[closest].x - event.offsetX) ? index : closest, 0);
    draw();
  });
  canvas.addEventListener("pointerleave", () => {
    hovered = -1;
    draw();
  });
  const observer = new ResizeObserver(draw);
  observer.observe(canvas);
  stopChart = () => observer.disconnect();
  setRange(12);
  return section;
}

function renderInsurance({ data, trend }) {
  const m = data.metrics;
  const cards = node("dl", null, "kpis");
  const values = [
    ["乘用车上险量", showNumber(m.total_sales), "辆", ""],
    ["上险量同比", signed(m.yoy_pct), "", `环比 ${signed(m.mom_pct)}`],
    ["新能源渗透率", percent(m.nev_penetration), "", ""],
    ["市场价格重心", m.weighted_tp == null ? "—" : (m.weighted_tp / 10000).toFixed(2), "万元", "按上险量加权"],
  ];
  values.forEach(([label, value, unit, subtitle]) => {
    const card = node("div", null, "kpi");
    const metric = node("dd", value);
    if (unit) metric.append(node("small", unit));
    card.append(node("dt", label), metric);
    if (subtitle) card.append(node("dd", subtitle, "submetric"));
    cards.append(card);
  });

  const layout = node("div", null, "grid-two");
  const energy = panel("能源结构", "占当月乘用车上险量比例");
  const rows = node("ul", null, "mix");
  data.energy.filter((row) => row.sales > 0).forEach((row) => {
    const item = node("li");
    const meter = node("meter");
    meter.max = 100;
    meter.value = row.share_pct;
    meter.setAttribute("aria-hidden", "true");
    item.append(node("span", row.type), node("strong", percent(row.share_pct)), meter);
    rows.append(item);
  });
  energy.section.append(rows);
  layout.append(trendPanel(trend), energy.section);

  const brands = panel("上险品牌排名", "当月上险量前 10", "compact");
  brands.section.append(makeTable(["排名", "品牌", "上险量（辆）", "市场份额"],
    data.brands.map((row, index) => [index + 1, row.brand, showNumber(row.sales), percent(row.share_pct)]), [0, 2, 3]));
  view.append(cards, layout, brands.section);
}

function detailLink(raw, code) {
  try {
    const url = new URL(raw);
    const hosts = ["miit.gov.cn", "miit-eidc.org.cn"];
    if (url.protocol === "https:" && hosts.some(host => url.hostname === host || url.hostname.endsWith(`.${host}`))) {
      const link = node("a", code);
      link.href = url.href;
      link.target = "_blank";
      link.rel = "noopener noreferrer";
      return link;
    }
  } catch {
    // Some historical rows have no detail URL.
  }
  return node("span", code);
}

function renderMiit({ data }) {
  const { section } = panel("乘用车公告记录", "按上游发布日期归月，保留批次、型号和发布阶段");
  const filters = node("div", null, "filters");
  const search = node("input");
  search.type = "search";
  search.placeholder = "品牌、车型、型号或企业";
  const stage = node("select");
  stage.append(option("全部阶段", ""), ...Object.entries(stages).map(([key, value]) => option(value, key)));
  const batch = node("select");
  batch.append(option("全部批次", ""), ...[...new Set(data.map(row => row.batch_no))]
    .sort((a, b) => Number(b) - Number(a)).map(value => option(`第 ${value} 批`, value)));
  [["搜索", search], ["发布阶段", stage], ["批次", batch]].forEach(([label, input]) => {
    const field = node("label", label);
    field.append(input);
    filters.append(field);
  });
  const results = node("div");
  const tally = node("p", null, "hint");
  tally.setAttribute("role", "status");
  section.append(filters, tally, results);
  function update() {
    const query = search.value.trim().toLowerCase();
    const matching = data.filter(row =>
      (!stage.value || row.stage === stage.value) &&
      (!batch.value || row.batch_no === batch.value) &&
      [row.brand, row.common_name, row.model_code, row.product_name, row.manufacturer]
        .some(value => String(value ?? "").toLowerCase().includes(query)));
    tally.textContent = `显示 ${matching.length} / ${data.length} 条归档记录`;
    results.replaceChildren();
    if (!matching.length) {
      results.append(node("p", "没有匹配的公告记录。"));
      return;
    }
    const table = makeTable(["品牌 / 企业", "车型 / 申报型号", "批次", "发布日期", "阶段 / 来源"],
      matching.map(row => {
        const brand = node("div", row.brand || "—");
        brand.append(node("span", row.manufacturer, "secondary"));
        const model = node("div", row.common_name || row.product_name || "—");
        const code = node("span", null, "secondary");
        code.append(detailLink(row.detail_url, row.model_code));
        model.append(code);
        const status = node("div");
        status.append(node("span", stages[row.stage], `stage ${row.stage}`),
          node("span", row.source === "eidc" ? "EIDC" : "MIIT Gov", "secondary"));
        return [brand, model, node("span", `第 ${row.batch_no} 批`, "batch"), row.publish_date, status];
      }));
    table.querySelector("table").className = "miit-table";
    results.append(table);
  }
  search.addEventListener("input", update);
  stage.addEventListener("change", update);
  batch.addEventListener("change", update);
  update();
  view.append(section);
}

function displaySources() {
  const coverage = $("#coverage");
  coverage.replaceChildren();
  for (const [key, label] of [["insurance", "上险覆盖至"], ["miit", "MIIT 覆盖至"]]) {
    const item = node("span", label);
    item.append(node("b", sources[key]?.latest_month ?? "暂无快照"));
    coverage.append(item);
  }
}

async function openView() {
  pending?.abort();
  stopChart?.();
  stopChart = undefined;
  const controller = new AbortController();
  pending = controller;
  const source = active;
  const metadata = sources[source];
  const month = selected[source] ?? metadata?.latest_month;
  sourceButtons.forEach((button) => {
    if (button.dataset.source === source) button.setAttribute("aria-current", "page");
    else button.removeAttribute("aria-current");
  });
  monthSelect.replaceChildren(...(metadata?.months ?? []).map(value => option(value, value)));
  if (!month) monthSelect.append(option("暂无月份", ""));
  monthSelect.value = month ?? "";
  monthSelect.disabled = !month;
  view.replaceChildren();
  sourceNote.hidden = true;
  if (!month) {
    notice.textContent = `${metadata?.name ?? "该来源"}暂无可用快照。`;
    return;
  }
  notice.textContent = "正在读取月度快照…";
  try {
    const payload = await get(`/api/v1/${source}/${month}`, controller.signal);
    if (controller.signal.aborted) return;
    if (source === "insurance") renderInsurance(payload);
    else renderMiit(payload);
    notice.textContent = "";
    const detail = node("details");
    const refreshed = timeFormat.format(new Date(metadata.refreshed_at));
    detail.append(node("summary", "数据来源与口径"),
      node("p", `${metadata.name} · 月度更新 · ${metadata.month_basis} · 快照生成于 ${refreshed}（北京时间）`),
      node("p", metadata.scope), node("p", metadata.artifact));
    sourceNote.replaceChildren(detail);
    sourceNote.hidden = false;
  } catch (error) {
    if (controller.signal.aborted) return;
    notice.textContent = "该月份快照读取失败，请重新选择月份或刷新页面。";
  }
}

async function start() {
  try {
    ({ sources } = await get("/api/v1/status"));
    displaySources();
    sourceButtons.forEach((button) => button.addEventListener("click", () => {
      active = button.dataset.source;
      openView();
    }));
    monthSelect.addEventListener("change", () => {
      selected[active] = monthSelect.value;
      openView();
    });
    await openView();
  } catch {
    notice.textContent = "无法读取数据源状态，请刷新页面重试。";
  }
}

start();

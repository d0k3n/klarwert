const BASE = "";
const CHART_COLORS = [
  "#58a6ff", "#3fb950", "#d29922", "#bc8cff",
  "#ffa657", "#79c0ff", "#f778ba", "#e6edf3"
];
const CHART_GREEN = "#3fb950";
const CHART_RED = "#f85149";
const CHART_BLUE = "#58a6ff";

async function loadJSON(url) {
const r = await fetch(url);
if (!r.ok) throw new Error(`HTTP ${r.status} ${url}`);
return r.json();
}

let cashFlowChart = null;
let monthlyPLChart = null;
let allocationChart = null;
let dividendChart = null;

const TABLE_CONFIGS = {
  'open-positions-table': {
    groupColumns: ['asset_class'],
    groupLabels: { asset_class: 'Asset Class' },
    numericFields: ['shares', 'total_cost'],
    averageFields: ['average_cost'],
  },
  'closed-positions-table': {
    groupColumns: ['asset_class'],
    groupLabels: { asset_class: 'Asset Class' },
    numericFields: ['total_realized_pl', 'closed_lots', 'total_shares_sold'],
  },
  'product-results-table': {
    groupColumns: ['asset_class', 'status'],
    groupLabels: { asset_class: 'Asset Class', status: 'Status' },
    numericFields: ['total_invested', 'total_realized_pl', 'total_dividends', 'total_dividend_tax', 'total_fees', 'total_trades'],
  },
  'derivative-executions-table': {
    groupColumns: ['asset_class', 'reconciled'],
    groupLabels: { asset_class: 'Asset Class', reconciled: 'Reconciled?' },
    numericFields: ['ko_quantity', 'ko_total', 'warrant_return', 'net_result'],
  },
  'card-expenses-table': {
    groupColumns: ['name'],
    groupLabels: { name: 'Merchant' },
    numericFields: ['amount'],
  },
  'transactions-table': {
    groupColumns: ['type', 'asset_class'],
    groupLabels: { type: 'Type', asset_class: 'Asset Class' },
    numericFields: ['shares', 'amount'],
  },
};

async function loadAllData() {
const [summary, openPositions, closedPositions, cashFlow, transactions, products, monthlyPl, derivativeExecutions, cardTransactions] = await Promise.all([
loadJSON(`${BASE}/api/summary`),
loadJSON(`${BASE}/api/open_positions`),
loadJSON(`${BASE}/api/closed_positions`),
loadJSON(`${BASE}/api/cash_flow`),
loadJSON(`${BASE}/api/transactions`),
loadJSON(`${BASE}/api/products`),
loadJSON(`${BASE}/api/monthly_pl`),
loadJSON(`${BASE}/api/derivative_executions`),
loadJSON(`${BASE}/api/card_transactions`),
]);

const empty = !summary || Object.keys(summary).length === 0;
document.getElementById("empty-state").style.display = empty ? "block" : "none";
document.getElementById("summary-cards").innerHTML = "";
document.getElementById("summary-by-asset-class").innerHTML = "";
if (empty) return;
renderSummary(summary);
renderSummaryByAssetClass(summary);
renderTable("open-positions-table", openPositions, TABLE_CONFIGS['open-positions-table']);
renderTable("closed-positions-table", closedPositions, TABLE_CONFIGS['closed-positions-table']);
renderCashFlowChart(cashFlow);
renderTransactions(transactions);
renderMonthlyPLChart(monthlyPl);
renderTable("product-results-table", products, TABLE_CONFIGS['product-results-table']);
renderAllocationChart(openPositions);
renderDividendChart(products);
renderTable("derivative-executions-table", derivativeExecutions, TABLE_CONFIGS['derivative-executions-table']);
renderTable("card-expenses-table", cardTransactions, TABLE_CONFIGS['card-expenses-table']);
}

window.reloadData = async function () {
const status = document.getElementById("reload-status");
status.textContent = "Reloading...";
try {
const r = await fetch(`${BASE}/api/reload`, { method: "POST" });
const data = await r.json();
if (!data.ok) throw new Error(data.error);
await loadAllData();
status.textContent = `Reloaded ${data.count} transactions.`;
setTimeout(() => status.textContent = "", 3000);
} catch (e) {
status.textContent = `Failed: ${e.message}`;
}
};

window.uploadCSV = async function (input) {
const status = document.getElementById("reload-status");
const file = input.files && input.files[0];
if (!file) return;
status.textContent = "Loading...";
try {
const form = new FormData();
form.append("file", file);
const r = await fetch(`${BASE}/api/upload`, { method: "POST", body: form });
const data = await r.json();
if (!data.ok) throw new Error(data.error);
await loadAllData();
status.textContent = `Loaded ${data.count} transactions from ${data.filename}.`;
setTimeout(() => status.textContent = "", 4000);
} catch (e) {
status.textContent = `Failed: ${e.message}`;
} finally {
input.value = "";
}
};

window.activateLicense = async function () {
  const input = document.getElementById("license-key");
  const status = document.getElementById("license-status");
  const btn = document.getElementById("license-activate-btn");
  const key = input.value.trim();
  if (!key) { status.textContent = "Please enter your license key."; return; }
  btn.disabled = true;
  status.textContent = "Activating...";
  try {
    const r = await fetch(`${BASE}/api/license/activate`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ key }),
    });
    const data = await r.json();
    if (!data.ok) throw new Error(data.error || "activation failed");
    document.getElementById("license-overlay").style.display = "none";
    await loadAllData();
  } catch (e) {
    status.textContent = `Failed: ${e.message}`;
  } finally {
    btn.disabled = false;
  }
};

(async () => {
  try {
    const r = await fetch(`${BASE}/api/license/status`);
    const data = await r.json();
    if (data.activated) {
      document.getElementById("license-overlay").style.display = "none";
      await loadAllData();
    } else {
      document.getElementById("license-overlay").style.display = "flex";
    }
  } catch (e) {
    document.getElementById("license-overlay").style.display = "flex";
  }
})();

function groupData(data, groupBy, numericFields, averageFields) {
  const groups = {};
  data.forEach(row => {
    let key;
    if (row[groupBy] === null || row[groupBy] === undefined) {
      key = '(empty)';
    } else if (typeof row[groupBy] === 'boolean') {
      key = row[groupBy] ? 'Yes' : 'No';
    } else {
      key = String(row[groupBy]);
    }
    if (!groups[key]) groups[key] = [];
    groups[key].push(row);
  });

  const rows = [];
  const totals = {};
  numericFields.forEach(f => totals[f] = 0);

  Object.keys(groups).sort().forEach(key => {
    const items = groups[key];
    const grp = {};
    numericFields.forEach(f => {
      grp[f] = items.reduce((acc, r) => acc + (r[f] || 0), 0);
      totals[f] += grp[f];
    });
    if (averageFields) {
      averageFields.forEach(f => {
        if (f === 'average_cost') {
          const tc = items.reduce((acc, r) => acc + (r.total_cost || 0), 0);
          const sh = items.reduce((acc, r) => acc + (r.shares || 0), 0);
          grp[f] = sh > 0 ? tc / sh : 0;
        } else {
          grp[f] = items.reduce((acc, r) => acc + (r[f] || 0), 0);
        }
      });
    }
    grp._groupKey = key;
    const first = items[0];
    Object.keys(first).forEach(k => {
      if (!numericFields.includes(k) && (!averageFields || !averageFields.includes(k)) && k !== groupBy && k !== '_groupKey') {
        grp[k] = first[k];
      }
    });
    rows.push(grp);
  });

  const totalRow = { _groupKey: 'Total' };
  numericFields.forEach(f => totalRow[f] = totals[f]);
  if (averageFields) averageFields.forEach(f => totalRow[f] = '—');

  return { rows, totals: totalRow };
}

function insertGroupDropdown(table, config, onChange) {
  const existing = table.parentNode.querySelector('.grouping-controls');
  if (existing) existing.remove();
  const wrapper = document.createElement('div');
  wrapper.className = 'grouping-controls';

  const select = document.createElement('select');
  select.className = 'group-dropdown';

  const noneOpt = document.createElement('option');
  noneOpt.value = '';
  noneOpt.textContent = 'None (no grouping)';
  select.appendChild(noneOpt);

  config.groupColumns.forEach(col => {
    const opt = document.createElement('option');
    opt.value = col;
    opt.textContent = config.groupLabels[col] || col;
    select.appendChild(opt);
  });

  select.addEventListener('change', () => onChange(select.value || null));
  wrapper.appendChild(select);

  const header = table.previousElementSibling;
  if (header && header.tagName === 'H2') {
    header.parentNode.insertBefore(wrapper, table);
  } else {
    table.parentNode.insertBefore(wrapper, table);
  }

  return select;
}

function formatVal(key, val) {
  if (typeof val !== 'number') return val ?? '';
  if (key === 'average_cost' || key.endsWith('_cost') || key === 'total_realized_pl' || key === 'total_invested' || key === 'total_dividends' || key === 'total_dividend_tax' || key === 'total_dividends_net' || key === 'total_fees' || key === 'amount' || key === 'price' || key === 'ko_total' || key === 'warrant_return' || key === 'net_result') {
    return `\u20AC${val.toLocaleString(undefined, {minimumFractionDigits: 2, maximumFractionDigits: 2})}`;
  }
  if (key === 'shares' || key === 'total_shares_sold') {
    return val.toLocaleString(undefined, {minimumFractionDigits: 4, maximumFractionDigits: 4});
  }
  return val.toLocaleString();
}

function renderSummary(s) {
const pl = s.total_realized_pl || 0;
const spending = s.total_card_spending || 0;
let coverage, coverageCls;
if (pl <= 0) {
coverage = "N/A";
coverageCls = "";
} else if (spending === 0) {
coverage = "100%";
coverageCls = "positive";
} else {
const pct = Math.min(100, spending / pl * 100);
coverage = `${pct.toFixed(1)}%`;
coverageCls = pct >= 100 ? "positive" : "negative";
}

const cards = [
{ label: "Expenses covered by P/L", value: coverage, fmt: v => v, cls: () => coverageCls },
{ label: "Total Invested", value: s.total_invested, fmt: v => `\u20AC${v.toLocaleString()}` },
{ label: "Realized P&L", value: pl, fmt: v => `\u20AC${v.toLocaleString()}`, cls: (v) => v >= 0 ? "positive" : "negative" },
{ label: "Dividends", value: s.total_dividends, fmt: v => `\u20AC${v.toLocaleString()}` },
{ label: "Dividend WHT", value: s.total_dividend_tax, fmt: v => `\u20AC${v.toLocaleString()}` },
{ label: "Interest", value: s.total_interest, fmt: v => `\u20AC${v.toLocaleString()}` },
{ label: "Fees", value: s.total_fees, fmt: v => `\u20AC${v.toLocaleString()}` },
{ label: "Card Spending", value: s.total_card_spending, fmt: v => `\u20AC${v.toLocaleString()}` },
{ label: "Net Deposits", value: s.net_deposits, fmt: v => `\u20AC${v.toLocaleString()}` },
];
const container = document.getElementById("summary-cards");
cards.forEach(c => {
const div = document.createElement("div");
div.className = "card";
const cls = c.cls ? c.cls(c.value) : "";
div.innerHTML = `<div class="label">${c.label}</div><div class="value ${cls}">${c.fmt(c.value)}</div>`;
container.appendChild(div);
});

const realizedCard = container.querySelector(".card:nth-child(3) .value");
if (realizedCard) realizedCard.textContent = `\u20AC${pl.toLocaleString()}`;
}

function renderSummaryByAssetClass(s) {
if (!s.by_asset_class) return;
const labels = { STOCK: "Stocks", DERIVATIVE: "Derivatives", FUND: "Funds" };
const container = document.getElementById("summary-by-asset-class");
Object.entries(s.by_asset_class).forEach(([ac, data]) => {
const div = document.createElement("div");
div.className = "card";
const plCls = data.total_realized_pl >= 0 ? "positive" : "negative";
div.innerHTML = `
<div class="label">${labels[ac] || ac} (${data.count})</div>
<div class="value">Invested: \u20AC${data.total_invested.toLocaleString()}</div>
<div class="value ${plCls}">P&amp;L: \u20AC${data.total_realized_pl.toLocaleString()}</div>
<div class="value">Dividends: \u20AC${data.total_dividends.toLocaleString()}</div>
`;
container.appendChild(div);
});
}

function renderTable(tableId, data, groupConfig) {
const table = document.getElementById(tableId);
const tbody = table.querySelector("tbody");
const thead = table.querySelector("thead");

let currentSort = null;
let currentAsc = true;
let groupBy = null;
let groupDropdown = null;

if (groupConfig) {
groupDropdown = insertGroupDropdown(table, groupConfig, (val) => {
groupBy = val;
renderRows(data);
});
}

function renderRows(sorted) {
tbody.innerHTML = "";
const cols = thead.querySelectorAll("th");

if (groupBy) {
const result = groupData(sorted, groupBy, groupConfig.numericFields, groupConfig.averageFields);

let groupRows = result.rows;
if (currentSort) {
groupRows = [...groupRows].sort((a, b) => {
const va = a[currentSort], vb = b[currentSort];
if (va == null || va === '—') return 1;
if (vb == null || vb === '—') return -1;
if (typeof va === "number" && typeof vb === "number") return currentAsc ? va - vb : vb - va;
return currentAsc ? String(va).localeCompare(String(vb)) : String(vb).localeCompare(String(va));
});
}

const groupColIndex = Array.from(cols).findIndex(th => th.dataset.sort === groupBy);
const useFirstCol = groupColIndex === -1;

groupRows.forEach(grp => {
const tr = document.createElement("tr");
tr.className = "group-row";
cols.forEach((th, i) => {
const key = th.dataset.sort;
if (!key) return;
const td = document.createElement("td");
if (useFirstCol && i === 0) {
td.textContent = grp._groupKey;
td.style.fontWeight = "600";
} else if (key === groupBy) {
td.textContent = grp._groupKey;
td.style.fontWeight = "600";
} else if ((groupConfig.numericFields || []).includes(key) || (groupConfig.averageFields || []).includes(key)) {
td.textContent = formatVal(key, grp[key] != null ? grp[key] : '—');
td.className = "num";
} else {
td.textContent = '—';
}
tr.appendChild(td);
});
tbody.appendChild(tr);
});

const tr = document.createElement("tr");
tr.className = "total-row";
cols.forEach((th, i) => {
const key = th.dataset.sort;
if (!key) return;
const td = document.createElement("td");
if (useFirstCol && i === 0) {
td.textContent = 'Total';
td.style.fontWeight = "700";
} else if (key === groupBy) {
td.textContent = 'Total';
td.style.fontWeight = "700";
} else if ((groupConfig.numericFields || []).includes(key)) {
td.textContent = formatVal(key, result.totals[key]);
td.className = "num";
} else if ((groupConfig.averageFields || []).includes(key)) {
td.textContent = '—';
td.className = "num";
} else {
td.textContent = '';
}
tr.appendChild(td);
});
tbody.appendChild(tr);

return;
}

sorted.forEach(row => {
const tr = document.createElement("tr");
cols.forEach(th => {
const key = th.dataset.sort;
if (!key) return;
const td = document.createElement("td");
td.className = th.className;
let val = row[key];
if (typeof val === "number") {
td.textContent = formatVal(key, val);
} else if (key === 'reconciled') {
td.textContent = val ? '\u2713' : '\u2717';
} else if (key === 'datetime' && val) {
td.textContent = new Date(val).toLocaleDateString();
} else {
td.textContent = val || "";
}
tr.appendChild(td);
});
tbody.appendChild(tr);
});
}

function sort(key) {
if (currentSort === key) { currentAsc = !currentAsc; }
else { currentSort = key; currentAsc = true; }

if (groupBy) {
renderRows(data);
return;
}

const sorted = [...data].sort((a, b) => {
const va = a[key], vb = b[key];
if (typeof va === "number" && typeof vb === "number") return currentAsc ? va - vb : vb - va;
return currentAsc ? String(va).localeCompare(String(vb)) : String(vb).localeCompare(String(va));
});
renderRows(sorted);
}

thead.querySelectorAll("th[data-sort]").forEach(th => {
th.addEventListener("click", () => sort(th.dataset.sort));
});

renderRows(data);
}

function renderCashFlowChart(cf) {
  if (cashFlowChart) cashFlowChart.destroy();
  const ctx = document.getElementById("cash-flow-chart").getContext("2d");
  const labels = cf.map(d => d.month);
  cashFlowChart = new Chart(ctx, {
    type: "bar",
    data: {
      labels,
      datasets: [
        { label: "Deposits", data: cf.map(d => d.deposit), backgroundColor: "#7ee787" },
        { label: "Withdrawals", data: cf.map(d => d.withdrawal), backgroundColor: CHART_RED },
        { label: "Dividends", data: cf.map(d => d.dividend), backgroundColor: "#bc8cff" },
      ],
    },
    options: {
      responsive: true,
      plugins: {
        legend: { position: "top", labels: { color: "#8b949e" } },
        tooltip: { backgroundColor: "#21262d", titleColor: "#e6edf3", bodyColor: "#e6edf3" },
      },
      scales: {
        x: { stacked: false, ticks: { color: "#8b949e" }, grid: { color: "#21262d" } },
        y: { beginAtZero: true, ticks: { color: "#8b949e" }, grid: { color: "#21262d" } },
      },
    },
  });
}

function renderTransactions(txs) {
const tbody = document.querySelector("#transactions-table tbody");
const filterInput = document.getElementById("tx-filter");
const table = document.getElementById("transactions-table");
const config = TABLE_CONFIGS['transactions-table'];

let groupBy = null;
let groupDropdown = insertGroupDropdown(table, config, (val) => {
groupBy = val;
render(filterInput.value.trim().toLowerCase());
});

function render(filter = "") {
tbody.innerHTML = "";
const filtered = filter
? txs.filter(t => t.symbol?.toLowerCase().includes(filter) || t.name?.toLowerCase().includes(filter))
: txs;

if (groupBy) {
const cols = table.querySelectorAll("thead th");
const result = groupData(filtered, groupBy, config.numericFields);

let groupRows = result.rows;

const groupColIndex = Array.from(cols).findIndex(th => th.dataset.sort === groupBy);
const useFirstCol = groupColIndex === -1;

groupRows.forEach(grp => {
const tr = document.createElement("tr");
tr.className = "group-row";
cols.forEach((th, i) => {
const key = th.dataset.sort;
if (!key) return;
const td = document.createElement("td");
if (useFirstCol && i === 0) {
td.textContent = grp._groupKey;
td.style.fontWeight = "600";
} else if (key === groupBy) {
td.textContent = grp._groupKey;
td.style.fontWeight = "600";
} else if (config.numericFields.includes(key)) {
td.textContent = formatVal(key, grp[key]);
td.className = "num";
} else {
td.textContent = '—';
}
tr.appendChild(td);
});
tbody.appendChild(tr);
});

const tr = document.createElement("tr");
tr.className = "total-row";
cols.forEach((th, i) => {
const key = th.dataset.sort;
if (!key) return;
const td = document.createElement("td");
if (useFirstCol && i === 0) {
td.textContent = 'Total';
td.style.fontWeight = "700";
} else if (key === groupBy) {
td.textContent = 'Total';
td.style.fontWeight = "700";
} else if (config.numericFields.includes(key)) {
td.textContent = formatVal(key, result.totals[key]);
td.className = "num";
} else {
td.textContent = '';
}
tr.appendChild(td);
});
tbody.appendChild(tr);
return;
}

filtered.forEach(t => {
const tr = document.createElement("tr");
tr.innerHTML = `
<td>${new Date(t.datetime).toLocaleDateString()}</td>
<td>${t.type}</td>
<td>${t.name || ""}</td>
<td>${t.symbol || ""}</td>
<td class="num">${t.shares?.toLocaleString(undefined, {minimumFractionDigits: 4}) || ""}</td>
<td class="num">${t.price != null ? `\u20AC${t.price.toLocaleString(undefined, {minimumFractionDigits: 2})}` : ""}</td>
<td class="num">${t.amount != null ? `\u20AC${t.amount.toLocaleString(undefined, {minimumFractionDigits: 2})}` : ""}</td>
`;
tbody.appendChild(tr);
});
}

render();
filterInput.addEventListener("input", () => render(filterInput.value.trim().toLowerCase()));
}

function renderMonthlyPLChart(data) {
  if (monthlyPLChart) monthlyPLChart.destroy();
  const ctx = document.getElementById("monthly-pl-chart").getContext("2d");
  monthlyPLChart = new Chart(ctx, {
    type: "bar",
    data: {
      labels: data.map(d => d.month),
      datasets: [{
        label: "Realized P&L",
        data: data.map(d => d.realized_pl),
        backgroundColor: data.map(d => d.realized_pl >= 0 ? CHART_GREEN : CHART_RED),
      }],
    },
    options: {
      responsive: true,
      plugins: {
        legend: { display: false },
        tooltip: { backgroundColor: "#21262d", titleColor: "#e6edf3", bodyColor: "#e6edf3" },
      },
      scales: {
        x: { ticks: { color: "#8b949e" }, grid: { color: "#21262d" } },
        y: { beginAtZero: true, ticks: { color: "#8b949e" }, grid: { color: "#21262d" } },
      },
    },
  });
}

function renderAllocationChart(openPositions) {
  if (allocationChart) allocationChart.destroy();
  const ctx = document.getElementById("allocation-chart").getContext("2d");
  const open = openPositions.filter(p => p.total_cost > 0);
  allocationChart = new Chart(ctx, {
    type: "doughnut",
    data: {
      labels: open.map(p => p.name),
      datasets: [{
        data: open.map(p => p.total_cost),
        backgroundColor: open.map((_, i) => CHART_COLORS[i % CHART_COLORS.length]),
      }],
    },
    options: {
      responsive: true,
      plugins: {
        legend: { position: "right", labels: { color: "#8b949e" } },
        tooltip: { backgroundColor: "#21262d", titleColor: "#e6edf3", bodyColor: "#e6edf3" },
      },
    },
  });
}



function renderDividendChart(products) {
  if (dividendChart) dividendChart.destroy();
  const ctx = document.getElementById("dividend-chart").getContext("2d");
  const withDividends = products.filter(p => p.total_dividends > 0).sort((a, b) => b.total_dividends - a.total_dividends);
  const barColors = withDividends.map((_, i) => CHART_COLORS[i % CHART_COLORS.length]);
  dividendChart = new Chart(ctx, {
    type: "bar",
    data: {
      labels: withDividends.map(p => p.name),
      datasets: [{
        label: "Dividends",
        data: withDividends.map(p => p.total_dividends),
        backgroundColor: barColors,
      }],
    },
    options: {
      indexAxis: "y",
      responsive: true,
      plugins: {
        legend: { display: false },
        tooltip: { backgroundColor: "#21262d", titleColor: "#e6edf3", bodyColor: "#e6edf3" },
      },
      scales: {
        x: { beginAtZero: true, ticks: { color: "#8b949e" }, grid: { color: "#21262d" } },
        y: { ticks: { color: "#8b949e" }, grid: { color: "#21262d" } },
      },
    },
  });
}

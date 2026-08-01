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
let incomeChart = null;
let spendingCatChart = null;
let spendingMonthChart = null;

const TABLE_CONFIGS = {
  'open-positions-table': {
    groupColumns: ['asset_class'],
    groupLabels: { asset_class: 'Asset Class' },
    numericFields: ['shares', 'total_cost', 'market_value', 'unrealized_pl', 'weight'],
    averageFields: ['average_cost', 'market_price'],
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
    averageFields: ['yield_on_cost'],
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
  'lot-matches-table': {
    groupColumns: ['name', 'isin'],
    groupLabels: { name: 'Name', isin: 'ISIN' },
    numericFields: ['shares', 'proceeds', 'cost_basis', 'pl'],
  },
};

async function loadAllData() {
const [summary, valuedPositions, closedPositions, cashFlow, transactions, products, monthlyPl, derivativeExecutions, cardTransactions, lotMatches, perfData, income, spending] = await Promise.all([
loadJSON(`${BASE}/api/summary`),
loadJSON(`${BASE}/api/valued_positions`),
loadJSON(`${BASE}/api/closed_positions`),
loadJSON(`${BASE}/api/cash_flow`),
loadJSON(`${BASE}/api/transactions`),
loadJSON(`${BASE}/api/products`),
loadJSON(`${BASE}/api/monthly_pl`),
loadJSON(`${BASE}/api/derivative_executions`),
loadJSON(`${BASE}/api/card_transactions`),
loadJSON(`${BASE}/api/lot_matches`),
loadJSON(`${BASE}/api/performance`),
loadJSON(`${BASE}/api/income`),
loadJSON(`${BASE}/api/spending`),
]);

const empty = !summary || Object.keys(summary).length === 0;
document.getElementById("empty-state").style.display = empty ? "block" : "none";
document.getElementById("summary-cards").innerHTML = "";
document.getElementById("summary-by-asset-class").innerHTML = "";
if (empty) return;
renderSummary(summary);
renderPerformance(perfData);
renderSummaryByAssetClass(summary);
renderRecon(summary);
const openPositions = valuedPositions.positions || [];
renderTable("open-positions-table", openPositions, TABLE_CONFIGS['open-positions-table']);
renderPriceInputs(openPositions);
renderValuedCards(valuedPositions.totals || {}, openPositions);
renderTable("closed-positions-table", closedPositions, TABLE_CONFIGS['closed-positions-table']);
renderCashFlowChart(cashFlow);
renderTransactions(transactions);
renderMonthlyPLChart(monthlyPl);
renderTable("product-results-table", products, TABLE_CONFIGS['product-results-table']);
renderAllocationChart(openPositions);
renderDividendChart(products);
renderIncomeChart(income.monthly);
renderTable("dividend-history-table", income.dividends, null);
renderTable("derivative-executions-table", derivativeExecutions, TABLE_CONFIGS['derivative-executions-table']);
renderTable("lot-matches-table", lotMatches, TABLE_CONFIGS['lot-matches-table']);
renderTable("card-expenses-table", cardTransactions, TABLE_CONFIGS['card-expenses-table']);
renderSpendingCharts(spending);
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

const supportConfig = {};
window.SUPPORT_URLS = supportConfig;

function openSupportUrl(url) {
  if (window.pywebview && window.pywebview.api && window.pywebview.api.open_url) {
    window.pywebview.api.open_url(url);
  } else {
    window.open(url, "_blank");
  }
}

window.openSupport = function () {
  if (supportConfig.DONATION_URL) openSupportUrl(supportConfig.DONATION_URL);
};

window.openFeatureRequest = function () {
  if (supportConfig.GITHUB_URL) openSupportUrl(supportConfig.GITHUB_URL);
};

function bindSupportLinks() {
  bindSupportButton("support-btn", "DONATION_URL");
  bindSupportButton("feature-btn", "GITHUB_URL");
  const footerLink = document.getElementById("footer-support-link");
  if (footerLink) {
    if (!supportConfig.DONATION_URL) {
      footerLink.style.display = "none";
    } else {
      footerLink.addEventListener("click", (e) => {
        e.preventDefault();
        openSupportUrl(supportConfig.DONATION_URL);
      });
    }
  }
}

function bindSupportButton(id, key) {
  const el = document.getElementById(id);
  if (!el) return;
  if (!supportConfig[key]) {
    el.style.display = "none";
    return;
  }
  el.addEventListener("click", () => openSupportUrl(supportConfig[key]));
}

(async () => {
  try {
    const r = await fetch(`${BASE}/api/support`);
    const data = await r.json();
    supportConfig.DONATION_URL = data.donation_url || "";
    supportConfig.GITHUB_URL = data.github_url || "";
    bindSupportLinks();
  } catch (e) {
    bindSupportLinks();
  }
  await loadAllData();
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
        } else if (f === 'market_price') {
          const priced = items.filter(r => r.market_price != null);
          const val = priced.reduce((acc, r) => acc + ((r.shares || 0) * r.market_price), 0);
          const sh = priced.reduce((acc, r) => acc + (r.shares || 0), 0);
          grp[f] = sh > 0 ? val / sh : null;
        } else if (f === 'yield_on_cost') {
          const net = items.reduce((acc, r) => acc + (r.total_dividends_net || 0), 0);
          const cost = items.reduce((acc, r) => acc + (r.total_cost || 0), 0);
          grp[f] = cost > 0 ? Math.round(100 * net / cost * 100) / 100 : null;
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
  if (key === 'weight') return `${(val * 100).toFixed(1)}%`;
  if (key === 'yield_on_cost') return val == null ? '' : `${val.toFixed(2)}%`;
  if (key === 'average_cost' || key.endsWith('_cost') || key === 'total_realized_pl' || key === 'total_invested' || key === 'total_dividends' || key === 'total_dividend_tax' || key === 'total_dividends_net' || key === 'total_fees' || key === 'amount' || key === 'price' || key === 'ko_total' || key === 'warrant_return' || key === 'net_result' || key === 'proceeds' || key === 'cost_basis' || key === 'pl' || key === 'market_value' || key === 'unrealized_pl' || key === 'market_price' || key === 'gross' || key === 'wht' || key === 'net') {
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

function renderPerformance(p) {
if (!p || Object.keys(p).length === 0) return;
const container = document.getElementById("summary-cards");
const eur = v => v == null ? "N/A" : `\u20AC${v.toLocaleString(undefined, {minimumFractionDigits: 2, maximumFractionDigits: 2})}`;
const cards = [
  { label: "XIRR (annualized)", value: p.xirr == null ? "N/A" : `${(p.xirr * 100).toFixed(2)}%` },
  { label: "Win Rate (closed)", value: p.win_rate == null ? "N/A" : `${p.win_rate}% (${p.winners}W/${p.losers}L)` },
  { label: "Avg Win", value: eur(p.avg_win), cls: "positive" },
  { label: "Avg Loss", value: eur(p.avg_loss), cls: "negative" },
];
cards.forEach(c => {
  const div = document.createElement("div");
  div.className = "card";
  div.innerHTML = `<div class="label">${c.label}</div><div class="value ${c.cls || ""}">${c.value}</div>`;
  container.appendChild(div);
});
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

function renderRecon(s) {
const tbody = document.querySelector("#recon-table tbody");
tbody.innerHTML = "";
if (!s.reconciliation) return;
const r = s.reconciliation;
const eur = v => `\u20AC${(v || 0).toLocaleString(undefined, {minimumFractionDigits: 2, maximumFractionDigits: 2})}`;
const rows = [
  ["Net deposits", r.net_deposits],
  ["Income (dividends net, interest, saveback)", r.income],
  ["Realized P&L", r.realized_pl],
  ["Cash balance", r.cash_balance],
  ["Open positions at cost", r.open_positions_cost],
  ["Card spending", r.card_spending],
  ["Standalone fees", r.fees],
  ["Unreconciled difference", r.difference],
];
rows.forEach(([label, val], i) => {
  const tr = document.createElement("tr");
  if (i === rows.length - 1) tr.className = "total-row";
  tr.innerHTML = `<td>${label}</td><td class="num">${eur(val)}</td>`;
  tbody.appendChild(tr);
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
} else if (key.endsWith('datetime') && val) {
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

function renderIncomeChart(monthly) {
  if (incomeChart) incomeChart.destroy();
  const ctx = document.getElementById("income-chart").getContext("2d");
  incomeChart = new Chart(ctx, {
    type: "bar",
    data: {
      labels: monthly.map(d => d.month),
      datasets: [
        { label: "Dividends (net)", data: monthly.map(d => d.dividends), backgroundColor: "#bc8cff" },
        { label: "Interest", data: monthly.map(d => d.interest), backgroundColor: "#7ee787" },
        { label: "Saveback", data: monthly.map(d => d.saveback), backgroundColor: "#58a6ff" },
      ],
    },
    options: {
      responsive: true,
      plugins: {
        legend: { position: "top", labels: { color: "#8b949e" } },
        tooltip: { backgroundColor: "#21262d", titleColor: "#e6edf3", bodyColor: "#e6edf3" },
      },
      scales: {
        x: { stacked: true, ticks: { color: "#8b949e" }, grid: { color: "#21262d" } },
        y: { stacked: true, beginAtZero: true, ticks: { color: "#8b949e" }, grid: { color: "#21262d" } },
      },
    },
  });
}

function renderSpendingCharts(spending) {
  if (spendingCatChart) spendingCatChart.destroy();
  const catCtx = document.getElementById("spending-category-chart").getContext("2d");
  const cats = spending.by_category || [];
  spendingCatChart = new Chart(catCtx, {
    type: "doughnut",
    data: {
      labels: cats.map(c => c.category),
      datasets: [{
        data: cats.map(c => c.total),
        backgroundColor: cats.map((_, i) => CHART_COLORS[i % CHART_COLORS.length]),
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
  if (spendingMonthChart) spendingMonthChart.destroy();
  const monCtx = document.getElementById("spending-monthly-chart").getContext("2d");
  const months = spending.monthly || [];
  spendingMonthChart = new Chart(monCtx, {
    type: "bar",
    data: {
      labels: months.map(m => m.month),
      datasets: [{ label: "Card Spending", data: months.map(m => m.total), backgroundColor: CHART_BLUE }],
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

let lastTaxReport = null;

window.loadTaxReport = async function () {
const yearInput = document.getElementById("tax-year");
if (!yearInput.value) yearInput.value = new Date().getFullYear();
const report = await loadJSON(`${BASE}/api/tax_report?year=${yearInput.value}`);
lastTaxReport = report;
renderTable("tax-disposals-table", report.disposals, null);
const tbody = document.querySelector("#tax-income-table tbody");
tbody.innerHTML = "";
const eur = v => `\u20AC${(v || 0).toLocaleString(undefined, {minimumFractionDigits: 2, maximumFractionDigits: 2})}`;
const t = report.dividend_totals;
[
  ["Dividends", t.gross, t.wht, t.net],
  ["Interest", report.interest, 0, report.interest],
  ["Saveback", report.saveback, 0, report.saveback],
].forEach(([label, g, w, n]) => {
  const tr = document.createElement("tr");
  tr.innerHTML = `<td>${label}</td><td class="num">${eur(g)}</td><td class="num">${eur(w)}</td><td class="num">${eur(n)}</td>`;
  tbody.appendChild(tr);
});
};

window.downloadTaxCsv = function () {
if (!lastTaxReport) return;
const lines = ["date;name;isin;shares;proceeds;cost_basis;fees;gain;acquired"];
lastTaxReport.disposals.forEach(d => {
  lines.push([d.date, d.name, d.isin, d.shares, d.proceeds, d.cost_basis, d.fees, d.gain, d.acquired].join(";"));
});
lines.push("");
lines.push("type;gross;wht;net");
lines.push(`dividends;${lastTaxReport.dividend_totals.gross};${lastTaxReport.dividend_totals.wht};${lastTaxReport.dividend_totals.net}`);
lines.push(`interest;${lastTaxReport.interest};;${lastTaxReport.interest}`);
lines.push(`saveback;${lastTaxReport.saveback};;${lastTaxReport.saveback}`);
const blob = new Blob([lines.join("\n")], { type: "text/csv" });
const a = document.createElement("a");
a.href = URL.createObjectURL(blob);
a.download = `tax_report_${lastTaxReport.year}.csv`;
a.click();
};

function renderValuedCards(totals, positions) {
const container = document.getElementById("summary-cards");
const eur = v => `\u20AC${(v || 0).toLocaleString(undefined, {minimumFractionDigits: 2, maximumFractionDigits: 2})}`;
const top5 = (positions || [])
  .map(p => p.weight || 0)
  .sort((a, b) => b - a)
  .slice(0, 5)
  .reduce((a, b) => a + b, 0);
[
  { label: "Est. Market Value", value: eur(totals.market_value) },
  { label: "Unrealized P&L", value: eur(totals.unrealized_pl), cls: (totals.unrealized_pl || 0) >= 0 ? "positive" : "negative" },
  { label: "Top 5 Concentration", value: `${(top5 * 100).toFixed(1)}%` },
].forEach(c => {
  const div = document.createElement("div");
  div.className = "card";
  div.innerHTML = `<div class="label">${c.label}</div><div class="value ${c.cls || ""}">${c.value}</div>`;
  container.appendChild(div);
});
}

function renderPriceInputs(positions) {
const container = document.getElementById("price-inputs");
container.innerHTML = "";
positions.forEach(p => {
  const row = document.createElement("div");
  row.style.marginBottom = "6px";
  row.innerHTML = `<span style="display:inline-block; width:320px;">${p.name} (${p.isin})</span>`;
  const input = document.createElement("input");
  input.type = "number";
  input.step = "0.0001";
  input.min = "0";
  input.placeholder = "price";
  if (p.market_price != null) input.value = p.market_price;
  input.addEventListener("change", async () => {
    const price = input.value === "" ? null : parseFloat(input.value);
    await fetch(`${BASE}/api/prices`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ isin: p.isin, price }),
    });
    await loadAllData();
  });
  row.appendChild(input);
  container.appendChild(row);
});
}

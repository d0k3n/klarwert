const BASE = "";

async function loadJSON(url) {
const r = await fetch(url);
if (!r.ok) throw new Error(`HTTP ${r.status} ${url}`);
return r.json();
}

let knockedIds = new Set();
let cashFlowChart = null;
let monthlyPLChart = null;
let allocationChart = null;
let dividendChart = null;

async function loadAllData() {
const [summary, openPositions, closedPositions, cashFlow, transactions, knockedDown, products, monthlyPl] = await Promise.all([
loadJSON(`${BASE}/api/summary`),
loadJSON(`${BASE}/api/open_positions`),
loadJSON(`${BASE}/api/closed_positions`),
loadJSON(`${BASE}/api/cash_flow`),
loadJSON(`${BASE}/api/transactions`),
loadJSON(`${BASE}/api/knocked_down`),
loadJSON(`${BASE}/api/products`),
loadJSON(`${BASE}/api/monthly_pl`),
]);

knockedIds = new Set(knockedDown.ids);

document.getElementById("summary-cards").innerHTML = "";
renderSummary(summary);
renderTable("open-positions-table", openPositions);
renderTable("closed-positions-table", closedPositions);
renderCashFlowChart(cashFlow);
renderTransactions(transactions, knockedIds);
renderMonthlyPLChart(monthlyPl);
renderTable("product-results-table", products);
renderAllocationChart(products);
renderDividendChart(products);
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

(async () => { await loadAllData(); })();

function renderSummary(s) {
const cards = [
{ label: "Total Invested", value: s.total_invested, fmt: v => `\u20AC${v.toLocaleString()}` },
{ label: "Realized P&L", value: s.total_realized_pl || 0, fmt: v => `\u20AC${v.toLocaleString()}`, cls: (v) => v >= 0 ? "positive" : "negative" },
{ label: "Dividends", value: s.total_dividends, fmt: v => `\u20AC${v.toLocaleString()}` },
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

const realizedCard = container.querySelector(".card:nth-child(2) .value");
if (realizedCard) realizedCard.textContent = `\u20AC${(s.total_realized_pl || 0).toLocaleString()}`;
}

function renderTable(tableId, data) {
const table = document.getElementById(tableId);
const tbody = table.querySelector("tbody");
const thead = table.querySelector("thead");

let currentSort = null;
let currentAsc = true;

function renderRows(sorted) {
tbody.innerHTML = "";
sorted.forEach(row => {
const tr = document.createElement("tr");
const cols = thead.querySelectorAll("th");
cols.forEach(th => {
const key = th.dataset.sort;
if (!key) return;
const td = document.createElement("td");
td.className = th.className;
let val = row[key];
if (typeof val === "number") {
if (key === "average_cost" || key === "total_cost" || key === "total_realized_pl" || key === "total_invested" || key === "total_dividends" || key === "total_fees") {
td.textContent = `\u20AC${val.toLocaleString(undefined, {minimumFractionDigits: 2, maximumFractionDigits: 2})}`;
} else if (key === "shares" || key === "total_shares_sold") {
td.textContent = val.toLocaleString(undefined, {minimumFractionDigits: 4, maximumFractionDigits: 4});
} else {
td.textContent = val.toLocaleString();
}
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
{ label: "Deposits", data: cf.map(d => d.deposit), backgroundColor: "#16a34a" },
{ label: "Withdrawals", data: cf.map(d => d.withdrawal), backgroundColor: "#dc2626" },
{ label: "Dividends", data: cf.map(d => d.dividend), backgroundColor: "#2563eb" },
],
},
options: {
responsive: true,
plugins: { legend: { position: "top" } },
scales: { x: { stacked: false }, y: { beginAtZero: true } },
},
});
}

async function toggleKnocked(txnId, cb) {
try {
const r = await fetch(`${BASE}/api/knocked_down/toggle`, {
method: "POST",
headers: {"Content-Type": "application/json"},
body: JSON.stringify({id: txnId}),
});
const data = await r.json();
cb(data.flagged);
} catch {
cb(null);
}
}

function renderTransactions(txs, knockedIds) {
const tbody = document.querySelector("#transactions-table tbody");
const filterInput = document.getElementById("tx-filter");

function updateRow(tr, t) {
const cb = tr.querySelector(".knocked-cb");
if (!cb || !t.id) return;
cb.checked = knockedIds.has(t.id);
tr.classList.toggle("knocked", cb.checked);
}

function render(filter = "") {
tbody.innerHTML = "";
const filtered = filter
? txs.filter(t => t.symbol?.toLowerCase().includes(filter) || t.name?.toLowerCase().includes(filter))
: txs;
filtered.forEach(t => {
const tr = document.createElement("tr");
const isBuy = t.type === "BUY";
const checked = t.id && knockedIds.has(t.id);
if (checked) tr.className = "knocked";
tr.innerHTML = `
<td>${new Date(t.datetime).toLocaleDateString()}</td>
<td>${t.type}</td>
<td>${t.name || ""}</td>
<td>${t.symbol || ""}</td>
<td class="num">${t.shares?.toLocaleString(undefined, {minimumFractionDigits: 4}) || ""}</td>
<td class="num">${t.price != null ? `\u20AC${t.price.toLocaleString(undefined, {minimumFractionDigits: 2})}` : ""}</td>
<td class="num">${t.amount != null ? `\u20AC${t.amount.toLocaleString(undefined, {minimumFractionDigits: 2})}` : ""}</td>
<td class="knocked-col">${isBuy && t.id ? `<input type="checkbox" class="knocked-cb" ${checked ? "checked" : ""}>` : "\u2014"}</td>
`;
tbody.appendChild(tr);

const cb = tr.querySelector(".knocked-cb");
if (cb) {
cb.addEventListener("change", () => {
const txnId = t.id;
toggleKnocked(txnId, (flagged) => {
if (flagged === null) {
cb.checked = !cb.checked;
return;
}
if (flagged) knockedIds.add(txnId);
else knockedIds.delete(txnId);
updateRow(tr, t);
});
});
}
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
backgroundColor: data.map(d => d.realized_pl >= 0 ? "#16a34a" : "#dc2626"),
}],
},
options: {
responsive: true,
plugins: { legend: { display: false } },
scales: { y: { beginAtZero: true } },
},
});
}

function renderAllocationChart(products) {
if (allocationChart) allocationChart.destroy();
const ctx = document.getElementById("allocation-chart").getContext("2d");
const openProducts = products.filter(p => p.status === "open" && p.total_invested > 0);
const colors = ["#2563eb", "#16a34a", "#f59e0b", "#ef4444", "#8b5cf6", "#ec4899", "#14b8a6", "#f97316", "#6366f1", "#84cc16"];
allocationChart = new Chart(ctx, {
type: "doughnut",
data: {
labels: openProducts.map(p => p.name),
datasets: [{
data: openProducts.map(p => p.total_invested),
backgroundColor: openProducts.map((_, i) => colors[i % colors.length]),
}],
},
options: {
responsive: true,
plugins: {
legend: { position: "right" },
tooltip: {
callbacks: {
label: ctx => ` ${ctx.label}: €${ctx.parsed.toLocaleString()}`,
},
},
},
},
});
}

function renderDividendChart(products) {
if (dividendChart) dividendChart.destroy();
const ctx = document.getElementById("dividend-chart").getContext("2d");
const withDividends = products.filter(p => p.total_dividends > 0).sort((a, b) => b.total_dividends - a.total_dividends);
dividendChart = new Chart(ctx, {
type: "bar",
data: {
labels: withDividends.map(p => p.name),
datasets: [{
label: "Dividends",
data: withDividends.map(p => p.total_dividends),
backgroundColor: "#2563eb",
}],
},
options: {
indexAxis: "y",
responsive: true,
plugins: { legend: { display: false } },
scales: { x: { beginAtZero: true } },
},
});
}

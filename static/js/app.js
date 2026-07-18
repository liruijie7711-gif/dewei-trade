// ============================================================
// RJ Trade Assistant — Frontend Logic
// ============================================================

let countries = [];
let quoteData = null;

// ---- Init ----
document.addEventListener('DOMContentLoaded', () => {
    loadCountries();
    onModelChange();
    calcVolWeight();
});

async function loadCountries() {
    try {
        const res = await fetch('/api/countries');
        countries = await res.json();
        const sel = document.getElementById('country');
        countries.forEach(c => {
            sel.innerHTML += `<option value="${c.code}">${c.name} (${c.region} · VAT ${(c.vat*100).toFixed(0)}%)</option>`;
        });
        // Pre-select Netherlands
        sel.value = 'NL';
    } catch(e) { console.error('Failed to load countries', e); }
}

// ---- Model change: auto-fill dimensions ----
async function onModelChange() {
    try {
        const model = document.getElementById('model').value;
        const res = await fetch('/api/products');
        const products = await res.json();
        const p = products[model];
        if (p) {
            const dims = p.dims.split('x');
            document.getElementById('dimL').value = dims[0];
            document.getElementById('dimW').value = dims[1];
            document.getElementById('dimH').value = dims[2];
            document.getElementById('weight').value = p.weight;
        }
        calcVolWeight();
    } catch(e) {}
}

// ---- Volume weight calculation ----
function calcVolWeight() {
    const l = parseFloat(document.getElementById('dimL').value) || 0;
    const w = parseFloat(document.getElementById('dimW').value) || 0;
    const h = parseFloat(document.getElementById('dimH').value) || 0;
    const divisor = parseInt(document.getElementById('volDivisor').value) || 5000;
    const actual = parseFloat(document.getElementById('weight').value) || 0;

    if (l && w && h) {
        const vol = (l * w * h) / divisor;
        const chargeable = Math.max(actual, vol).toFixed(1);
        document.getElementById('volWeightInfo').innerHTML =
            `Volume weight: ${vol.toFixed(1)} kg &nbsp;|&nbsp; Chargeable: <strong>${chargeable} kg</strong>`;
    }
}

// ---- Mode change ----
function onModeChange() {
    // Just refresh UI cues
}

// ---- Calculate ----
async function calculate() {
    const country = document.getElementById('country').value;
    const model = document.getElementById('model').value;
    const price = parseFloat(document.getElementById('priceUsd').value) || 0;
    const costCny = parseFloat(document.getElementById('costCny').value) || 0;
    const mode = document.querySelector('input[name="mode"]:checked').value;

    if (!country) { showToast('Please select a country'); return; }
    if (!price) { showToast('Please enter product price'); return; }

    const btn = document.getElementById('calcBtn');
    btn.textContent = 'Calculating...';
    btn.disabled = true;

    try {
        const res = await fetch('/api/calculate', {
            method: 'POST',
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify({ country, model, price, cost_cny: costCny, mode })
        });
        quoteData = await res.json();

        if (quoteData.error) {
            showToast(quoteData.error);
            return;
        }

        renderResults(quoteData);
        document.getElementById('resultsPanel').style.display = '';
        document.getElementById('saveBtn').disabled = false;
        showToast('Calculated!');
    } catch(e) {
        showToast('Calculation failed: ' + e.message);
    } finally {
        btn.textContent = 'Calculate';
        btn.disabled = false;
    }
}

function renderResults(d) {
    const grid = document.getElementById('resultsGrid');
    const items = [
        { label: 'Chargeable Weight', value: `${d.chargeable_weight} kg`, badge: 'badge-blue' },
        { label: 'Shipping (' + d.mode + ')', value: `$${d.shipping_cost}`, badge: 'badge-blue' },
        { label: 'Est. VAT/Tax', value: `$${d.tax_amount}`, badge: 'badge-amber' },
        { label: 'Transit Time', value: `${d.transit} days`, badge: 'badge-green' },
        { label: 'Total Price', value: `$${d.total_price}`, badge: '' },
    ];
    if (d.profit !== null) {
        items.push({ label: 'Est. Profit', value: `$${d.profit} (${d.profit_pct}%)`, badge: d.profit > 0 ? 'badge-green' : 'badge-amber' });
    }

    grid.innerHTML = items.map(i => `
        <div class="p-3 rounded-lg bg-gray-50">
            <div class="text-xs text-gray-500 mb-1">${i.label}</div>
            <div class="text-lg font-semibold ${i.badge ? '' : 'text-gray-900'}">
                ${i.badge ? `<span class="result-badge ${i.badge}">${i.value}</span>` : i.value}
            </div>
        </div>
    `).join('');

    document.getElementById('quoteBox').textContent = d.quote_text;
}

// ---- Copy quote ----
function copyQuote() {
    if (!quoteData) return;
    navigator.clipboard.writeText(quoteData.quote_text).then(() => {
        showToast('Quote copied!');
    }).catch(() => {
        showToast('Failed to copy');
    });
}

// ---- Save quote ----
async function saveQuote() {
    if (!quoteData) return;
    const name = document.getElementById('customerName').value || '';

    try {
        const res = await fetch('/api/quotes', {
            method: 'POST',
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify({
                customer_name: name,
                country_code: quoteData.country.code,
                product_model: document.getElementById('model').value,
                dims_cm: `${document.getElementById('dimL').value}x${document.getElementById('dimW').value}x${document.getElementById('dimH').value}`,
                actual_weight: parseFloat(document.getElementById('weight').value),
                chargeable_weight: quoteData.chargeable_weight,
                product_price: quoteData.product_price,
                shipping_mode: quoteData.mode,
                shipping_cost: quoteData.shipping_cost,
                tax_amount: quoteData.tax_amount,
                total_price: quoteData.total_price,
                profit: quoteData.profit,
                cost_price_cny: parseFloat(document.getElementById('costCny').value) || null,
            })
        });
        const result = await res.json();
        if (result.success) {
            showToast('Quote saved! #' + result.id);
        }
    } catch(e) {
        showToast('Save failed: ' + e.message);
    }
}

// ---- Load quotes history ----
async function loadQuotes() {
    try {
        const res = await fetch('/api/quotes');
        const quotes = await res.json();
        const list = document.getElementById('historyList');
        if (quotes.length === 0) {
            list.innerHTML = '<p class="text-gray-400 text-sm">No saved quotes yet.</p>';
        } else {
            list.innerHTML = quotes.map(q => `
                <div class="flex items-center justify-between py-3 border-b border-gray-100 last:border-0">
                    <div>
                        <div class="text-sm font-medium">${q.customer_name || 'Unnamed'} — ${q.country_code} · ${q.product_model}</div>
                        <div class="text-xs text-gray-400">$${q.total_price} · ${new Date(q.created_at).toLocaleDateString()}</div>
                    </div>
                    <button onclick="viewQuote(${q.id})" class="text-xs text-brand-600 font-medium">View</button>
                </div>
            `).join('');
        }
        document.getElementById('historyModal').style.display = '';
    } catch(e) {
        showToast('Failed to load history');
    }
}

async function viewQuote(id) {
    try {
        const res = await fetch('/api/quote/' + id);
        quoteData = await res.json();
        renderResults(quoteData);
        document.getElementById('resultsPanel').style.display = '';
        document.getElementById('historyModal').style.display = 'none';
        showToast('Loaded quote #' + id);
    } catch(e) {}
}

function closeHistory(e) {
    if (e.target === document.getElementById('historyModal')) {
        document.getElementById('historyModal').style.display = 'none';
    }
}

// ---- Toast ----
function showToast(msg) {
    const t = document.getElementById('toast');
    t.textContent = msg;
    t.classList.add('show');
    setTimeout(() => t.classList.remove('show'), 2000);
}

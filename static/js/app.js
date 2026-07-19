let allCountries = [], quoteData = null;

document.addEventListener('DOMContentLoaded', () => {
    loadCountries();
    calcVolWeight();
    document.addEventListener('click', (e) => {
        if (!e.target.closest('#countryList') && !e.target.closest('#countrySearch')) {
            document.getElementById('countryList').classList.add('hidden');
        }
    });
});

async function loadCountries() {
    try {
        const res = await fetch('/api/countries');
        allCountries = await res.json();
        renderCountryList(allCountries);
    } catch(e) { console.error(e); }
}

function renderCountryList(list) {
    const div = document.getElementById('countryList');
    if (list.length === 0) { div.innerHTML = '<div class="px-3 py-2 text-xs text-gray-400">无匹配结果</div>'; div.classList.remove('hidden'); return; }
    div.innerHTML = list.map(c => `<div class="px-3 py-2 text-sm hover:bg-blue-50 cursor-pointer border-b border-gray-50 last:border-0" onclick="selectCountry('${c.cc}','${c.cn}')">${c.cn} <span class="text-gray-400 text-xs">${c.en} · ${c.region} · VAT ${(c.vat*100).toFixed(0)}%</span></div>`).join('');
    div.classList.remove('hidden');
}

function filterCountries() {
    const q = document.getElementById('countrySearch').value.toLowerCase();
    const filtered = allCountries.filter(c => c.cn.includes(q) || c.en.toLowerCase().includes(q) || c.cc.toLowerCase().includes(q));
    renderCountryList(filtered);
}

function showCountryList() { if (allCountries.length) renderCountryList(allCountries); }

function selectCountry(cc, cn) {
    document.getElementById('country').value = cc;
    document.getElementById('countrySearch').value = cn;
    document.getElementById('countryList').classList.add('hidden');
}


function calcVolWeight() {
    const l = parseFloat(document.getElementById('dimL').value) || 0;
    const w = parseFloat(document.getElementById('dimW').value) || 0;
    const h = parseFloat(document.getElementById('dimH').value) || 0;
    const d = parseInt(document.getElementById('volDivisor').value) || 5000;
    const a = parseFloat(document.getElementById('weight').value) || 0;
    if (l && w && h) {
        const v = (l*w*h)/d, c = Math.max(a,v).toFixed(1);
        document.getElementById('volWeightInfo').innerHTML = `体积重：${v.toFixed(1)} kg | 计费重：<strong>${c} kg</strong>`;
    }
}

async function calculate() {
    const cc = document.getElementById('country').value;
    if (!cc) { showToast('请搜索并选择国家'); return; }
    const price = parseFloat(document.getElementById('priceUsd').value) || 0;
    if (!price) { showToast('请输入产品售价'); return; }
    const mode = document.querySelector('input[name="mode"]:checked').value;
    const method = document.querySelector('input[name="method"]:checked').value;
    const productName = document.getElementById('productName').value || '3D Fan Display';
    const costCny = parseFloat(document.getElementById('costCny').value) || 0;
    const postalCode = document.getElementById('postalCode').value;

    const btn = document.getElementById('calcBtn'); btn.textContent = '计算中...'; btn.disabled = true;
    try {
        const res = await fetch('/api/calculate', {
            method: 'POST', headers: {'Content-Type':'application/json'},
            body: JSON.stringify({
                country: cc, price, mode, method, cost_cny: costCny,
                product_name: productName, postal_code: postalCode,
                dim_l: parseFloat(document.getElementById('dimL').value)||0,
                dim_w: parseFloat(document.getElementById('dimW').value)||0,
                dim_h: parseFloat(document.getElementById('dimH').value)||0,
                weight: parseFloat(document.getElementById('weight').value)||0,
                vol_divisor: parseInt(document.getElementById('volDivisor').value)||5000,
            })
        });
        quoteData = await res.json();
        if (quoteData.error) { showToast(quoteData.error); return; }
        renderResults(quoteData);
        document.getElementById('resultsPanel').style.display = '';
        document.getElementById('saveBtn').disabled = false;
    } catch(e) { showToast('失败: '+e.message); }
    finally { btn.textContent = '开始计算'; btn.disabled = false; }
}

function renderResults(d) {
    const grid = document.getElementById('resultsGrid');
    const items = [
        { label: '运输方式', value: d.method_cn, badge: 'badge-green' },
        { label: '计费重量', value: `${d.chargeable_weight} kg`, badge: 'badge-blue' },
        { label: `运费（${d.mode}）`, value: `$${d.shipping_cost}` + (d.remote_surcharge ? `（偏远 +$${d.remote_surcharge}）` : '') + (d.mode === 'DDP' && d.tax_amount > 0 ? `（已含税 ~$${d.tax_amount}）` : '') + (d.mode === 'DDU' && d.tax_amount > 0 ? `（客户自付税 ~$${d.tax_amount}）` : ''), badge: d.remote_surcharge ? 'badge-amber' : 'badge-blue' },
        { label: '运输时效', value: `${d.transit} 天`, badge: 'badge-green' },
        { label: '客户总价', value: `$${d.total_price}`, badge: '' },
    ...(d.mode === 'DDU' ? [{ label: '客户到港需付税（估计）', value: `~$${d.tax_amount}`, badge: 'badge-amber' }] : []),
    ];
    if (d.profit !== null) items.push({ label: '预估利润', value: `$${d.profit}（${d.profit_pct}%）`, badge: d.profit > 0 ? 'badge-green' : 'badge-amber' });
    grid.innerHTML = items.map(i => `<div class="p-3 rounded-lg bg-gray-50"><div class="text-xs text-gray-500 mb-1">${i.label}</div><div class="text-lg font-semibold">${i.badge ? `<span class="result-badge ${i.badge}">${i.value}</span>` : i.value}</div></div>`).join('');
    document.getElementById('quoteBox').textContent = d.quote_text;
}

function copyQuote() { if(quoteData) navigator.clipboard.writeText(quoteData.quote_text).then(()=>showToast('已复制！')).catch(()=>showToast('复制失败')); }

async function saveQuote() {
    if(!quoteData) return;
    try {
        const res = await fetch('/api/quotes', {method:'POST', headers:{'Content-Type':'application/json'}, body:JSON.stringify({
            customer_name: document.getElementById('customerName').value || '',
            product_name: document.getElementById('productName').value,
            country_code: quoteData.country.code,
            shipping_method: quoteData.method,
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
        })});
        const r = await res.json();
        if(r.success) showToast('已保存！#'+r.id);
    } catch(e) { showToast('保存失败'); }
}

async function loadQuotes() {
    try {
        const res = await fetch('/api/quotes'), qs = await res.json();
        const list = document.getElementById('historyList');
        list.innerHTML = qs.length ? qs.map(q => `<div class="flex items-center justify-between py-3 border-b border-gray-100 last:border-0"><div><div class="text-sm font-medium">${q.customer_name||'未命名'} — ${q.country_code} · ${q.product_name||''}</div><div class="text-xs text-gray-400">$${q.total_price} · ${new Date(q.created_at).toLocaleDateString('zh-CN')}</div></div><button onclick="viewQuote(${q.id})" class="text-xs text-brand-600 font-medium">查看</button></div>`).join('') : '<p class="text-gray-400 text-sm">暂无记录</p>';
        document.getElementById('historyModal').style.display = '';
    } catch(e) { showToast('加载失败'); }
}

async function viewQuote(id) {
    try {
        const res = await fetch('/api/quote/'+id);
        quoteData = await res.json();
        renderResults(quoteData);
        document.getElementById('resultsPanel').style.display = '';
        document.getElementById('historyModal').style.display = 'none';
    } catch(e) {}
}

function closeHistory(e) { if(e.target===document.getElementById('historyModal')) document.getElementById('historyModal').style.display='none'; }
function showToast(m) { const t=document.getElementById('toast'); t.textContent=m; t.classList.add('show'); setTimeout(()=>t.classList.remove('show'),2000); }

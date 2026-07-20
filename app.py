"""
RJ Trade Assistant v2.0 — 物流报价工具
"""

from flask import Flask, render_template, request, jsonify
from flask_sqlalchemy import SQLAlchemy
from datetime import datetime, timezone
import json, os, functools

app = Flask(__name__)
app.secret_key = os.environ.get('SECRET_KEY', 'rj-trade-assistant-dev-key')
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///trade_assistant.db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
db = SQLAlchemy(app)

class QuoteRecord(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    customer_name = db.Column(db.String(100), default='')
    product_name = db.Column(db.String(100), default='')
    country_code = db.Column(db.String(10), nullable=False)
    shipping_method = db.Column(db.String(10), default='air')
    dims_cm = db.Column(db.String(30), nullable=False)
    actual_weight = db.Column(db.Float, nullable=False)
    chargeable_weight = db.Column(db.Float, nullable=False)
    product_price = db.Column(db.Float, nullable=False)
    shipping_mode = db.Column(db.String(10), nullable=False)
    shipping_cost = db.Column(db.Float, nullable=False)
    tax_amount = db.Column(db.Float, nullable=False)
    total_price = db.Column(db.Float, nullable=False)
    profit = db.Column(db.Float, nullable=True)
    cost_price_cny = db.Column(db.Float, nullable=True)
    notes = db.Column(db.Text, default='')
    created_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))

# Load country data
with open('data/countries.json', 'r', encoding='utf-8') as f:
    COUNTRIES = json.load(f)

try:
    with open('data/providers.json', 'r', encoding='utf-8') as f:
        PROVIDERS = json.load(f)
except Exception:
    PROVIDERS = {}

# Country lookup
COUNTRY_MAP = {c["cc"]: c for c in COUNTRIES}

# Remote area surcharge
REMOTE_SURCHARGE = {
    "NO": {"patterns": ["79","8","9"], "surcharge": 25, "label": "Remote Norway"},
    "CA": {"patterns": ["X","Y","A0"], "surcharge": 20, "label": "Remote Canada"},
    "FI": {"patterns": ["9"], "surcharge": 20, "label": "Lapland, Finland"},
    "SE": {"patterns": ["9"], "surcharge": 18, "label": "Northern Sweden"},
    "AU": {"patterns": ["08","6","7"], "surcharge": 15, "label": "Remote Australia"},
    "US": {"patterns": ["995","996","997","998","999","967","968"], "surcharge": 15, "label": "Alaska/Hawaii"},
    "DE": {"patterns": ["264","265","267","274","258","259"], "surcharge": 12, "label": "German Islands"},
    "ES": {"patterns": ["35","38"], "surcharge": 18, "label": "Canary Islands"},
    "GR": {"patterns": ["8","67","68"], "surcharge": 15, "label": "Greek Islands"},
    "GB": {"patterns": ["KW","IV","HS","ZE","PH","PA","BT","KA27","KA28"], "surcharge": 15, "label": "Highlands & Islands"},
    "NZ": {"patterns": ["7","9"], "surcharge": 12, "label": "Remote NZ"},
    "TH": {"patterns": ["8","9"], "surcharge": 10, "label": "Southern Thailand"},
}

METHOD_LABELS = {"air": "Air Freight", "rail": "Rail Freight", "sea": "Sea Freight"}
METHOD_CN = {"air": "空运", "rail": "铁路", "sea": "海运"}

def check_remote_surcharge(country_code, postal_code):
    if not postal_code: return None
    config = REMOTE_SURCHARGE.get(country_code.upper())
    if not config: return None
    pc = postal_code.replace(" ", "").upper()
    for prefix in config["patterns"]:
        if pc.startswith(prefix): return config
    return None

def calc_volumetric(l, w, h, div=5000):
    return (l * w * h) / div

def calc_shipping(country, chargeable_kg, method, mode):
    """Calculate shipping cost based on per-kg rate + minimum."""
    dps = "ddp" if mode == "DDP" else "ddu"
    
    if method == "air":
        rate = country[f"air_{dps}"]
        base = 15  # base handling fee
    elif method == "rail":
        rate = country.get(f"rail_{dps}", 0)
        base = 10
        if rate == 0: return None  # rail not available
    else:  # sea
        rate = country["sea_cbm"] / 166.7  # convert per-CBM to per-kg (1 CBM ≈ 166.7 kg at ÷6000)
        base = 20
    
    # Minimum chargeable weight
    min_wt = 5 if method in ("air","rail") else 10
    cw = max(chargeable_kg, min_wt)
    
    shipping = round(cw * rate + base)
    # Floor
    floors = {"air": 50, "rail": 40, "sea": 35}
    shipping = max(shipping, floors.get(method, 40))
    
    return shipping

def calc_tax(product_price, shipping_cost, country, mode):
    vat_rate = country["vat"]
    if mode == "DDP":
        cif = product_price + shipping_cost * 0.6
    else:
        cif = product_price + shipping_cost
    tax = round(cif * vat_rate)
    return {"vat_rate": vat_rate, "tax_amount": tax}

def gen_quote(product_name, product_price, shipping_cost, tax_amount, total, country, mode, method, transit):
    cn = country["en"]
    method_en = METHOD_LABELS.get(method, method)
    if mode == "DDP":
        return f"""Product: {product_name}
Product Price: ${product_price}
Shipping ({mode} {method_en}): ${shipping_cost}
Delivery Time: {transit} business days
Delivery to: {cn}
────────────────────────
Total: ${total}

All import duties, VAT, and customs clearance fees are included. Door-to-door delivery."""
    else:
        return f"""Product: {product_name}
Product Price: ${product_price}
Shipping ({mode} {method_en}): ${shipping_cost}
Delivery Time: {transit} business days
Delivery to: {cn}
────────────────────────
Subtotal: ${product_price + shipping_cost}

Import VAT and customs clearance fees to be paid by consignee.
Estimated VAT: ~${tax_amount}"""



@app.route('/')
def index():
    return render_template('index.html')

@app.route('/api/countries')
def api_countries():
    return jsonify(COUNTRIES)

@app.route('/api/calculate', methods=['POST'])
def api_calculate():
    data = request.get_json()
    country_code = data.get('country','').upper()
    product_price = float(data.get('price', 0))
    mode = data.get('mode','DDP').upper()
    method = data.get('method','air').lower()
    cost_cny = float(data.get('cost_cny', 0))
    postal_code = data.get('postal_code','')
    product_name = data.get('product_name','3D Fan Display')
    
    # Dimensions
    dims = {}
    for k in ['l','w','h']:
        dims[k] = float(data.get(f'dim_{k}', 0) or 0)
    actual_kg = float(data.get('weight', 0) or 0)
    divisor = int(data.get('vol_divisor', 5000) or 5000)
    
    if country_code not in COUNTRY_MAP:
        return jsonify({"error": "不支持该国家"}), 400
    
    country = COUNTRY_MAP[country_code]
    
    # Volumetric weight
    vol_kg = calc_volumetric(dims['l'], dims['w'], dims['h'], divisor) if all(dims.values()) else 0
    chargeable = round(max(actual_kg, vol_kg), 1)
    
    # Shipping
    shipping = calc_shipping(country, chargeable, method, mode)
    if shipping is None:
        return jsonify({"error": f"该国家不支持{METHOD_CN.get(method, method)}运输"}), 400
    
    # Remote surcharge
    remote = check_remote_surcharge(country_code, postal_code)
    remote_fee = 0
    remote_label = None
    if remote:
        remote_fee = remote["surcharge"]
        remote_label = remote["label"]
        shipping += remote_fee
    
    # Tax
    tax_info = calc_tax(product_price, shipping, country, mode)
    
    # Transit
    transit_key = f"{method}_d"
    transit = country.get(transit_key, "7-12")
    
    # Total: product + shipping (DDU tax paid by customer at customs)
    total = product_price + shipping
    
    # Profit
    profit = None
    profit_pct = None
    if cost_cny > 0:
        cost_usd = round(cost_cny / 7.25, 2)
        profit = round(total - cost_usd - shipping, 2)
        profit_pct = round((profit / total) * 100, 1) if total > 0 else 0
    
    # Quote
    quote_text = gen_quote(product_name, product_price, shipping, tax_info["tax_amount"], total, country, mode, method, transit)
    
    return jsonify({
        "country": {"code": country_code, "name": country["en"], "name_cn": country["cn"]},
        "product_name": product_name,
        "product_price": product_price,
        "mode": mode,
        "method": method,
        "method_cn": METHOD_CN.get(method, method),
        "actual_weight": actual_kg,
        "vol_weight": round(vol_kg, 1),
        "chargeable_weight": chargeable,
        "shipping_cost": shipping,
        "tax_amount": tax_info["tax_amount"],
        "vat_rate": country["vat"],
        "transit": transit,
        "total_price": total,
        "profit": profit,
        "profit_pct": profit_pct,
        "quote_text": quote_text,
        "providers": get_provider_comparison(country["region"], chargeable, method, mode),
        "remote_surcharge": remote_fee,
        "remote_label": remote_label,
        "summary": {
            "method": method,
            "method_cn": METHOD_CN.get(method, method),
            "chargeable": f"{chargeable} kg",
            "shipping": f"${shipping}",
            "tax": f"${tax_info['tax_amount']}",
            "transit": f"{transit} Days",
            "total": f"${total}",
        }
    })

@app.route('/api/quotes', methods=['GET','POST'])
def api_quotes():
    if request.method == 'POST':
        d = request.get_json()
        r = QuoteRecord(
            customer_name=d.get('customer_name',''), product_name=d.get('product_name',''),
            country_code=d['country_code'], shipping_method=d.get('shipping_method','air'),
            dims_cm=d['dims_cm'], actual_weight=d['actual_weight'],
            chargeable_weight=d['chargeable_weight'], product_price=d['product_price'],
            shipping_mode=d['shipping_mode'], shipping_cost=d['shipping_cost'],
            tax_amount=d['tax_amount'], total_price=d['total_price'],
            profit=d.get('profit'), cost_price_cny=d.get('cost_price_cny'), notes=d.get('notes',''),
        )
        db.session.add(r); db.session.commit()
        return jsonify({"success": True, "id": r.id})
    qs = QuoteRecord.query.order_by(QuoteRecord.created_at.desc()).limit(50).all()
    return jsonify([{"id":q.id,"customer_name":q.customer_name,"country_code":q.country_code,
        "product_name":q.product_name,"total_price":q.total_price,
        "created_at":q.created_at.isoformat() if q.created_at else None} for q in qs])

@app.route('/api/quote/<int:qid>')
def api_get_quote(qid):
    q = QuoteRecord.query.get_or_404(qid)
    return jsonify({"id":q.id,"customer_name":q.customer_name,"country_code":q.country_code,
        "product_name":q.product_name,"shipping_method":q.shipping_method,"dims_cm":q.dims_cm,
        "actual_weight":q.actual_weight,"chargeable_weight":q.chargeable_weight,
        "product_price":q.product_price,"shipping_mode":q.shipping_mode,
        "shipping_cost":q.shipping_cost,"tax_amount":q.tax_amount,"total_price":q.total_price,
        "profit":q.profit,"cost_price_cny":q.cost_price_cny,"notes":q.notes,
        "created_at":q.created_at.isoformat() if q.created_at else None})


# ============================================================
@app.errorhandler(404)
def nf(e): return jsonify({"error":"Not found"}),404

if __name__ == '__main__':
    with app.app_context():
        db.create_all()
    app.run(host='0.0.0.0', port=5020, debug=False)

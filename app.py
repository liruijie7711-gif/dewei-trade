"""
RJ Trade Assistant v1.0 — Shipping & Tax Calculator
Internal tool for international trade quotes.
"""

from flask import Flask, render_template, request, jsonify, session, redirect, url_for
from flask_sqlalchemy import SQLAlchemy
from datetime import datetime, timezone
import json
import os
import functools

app = Flask(__name__)
app.secret_key = os.environ.get('SECRET_KEY', 'rj-trade-assistant-dev-key-change-in-prod')
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///trade_assistant.db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

db = SQLAlchemy(app)

# ============================================================
# Database Models
# ============================================================

class QuoteRecord(db.Model):
    """Saved quote records for customers."""
    id = db.Column(db.Integer, primary_key=True)
    customer_name = db.Column(db.String(100), default='')
    country_code = db.Column(db.String(10), nullable=False)
    product_model = db.Column(db.String(20), nullable=False)
    dims_cm = db.Column(db.String(30), nullable=False)          # "50.5x50.5x11.5"
    actual_weight = db.Column(db.Float, nullable=False)
    chargeable_weight = db.Column(db.Float, nullable=False)
    product_price = db.Column(db.Float, nullable=False)
    shipping_mode = db.Column(db.String(10), nullable=False)     # DDP / DDU
    shipping_cost = db.Column(db.Float, nullable=False)
    tax_amount = db.Column(db.Float, nullable=False)
    total_price = db.Column(db.Float, nullable=False)
    profit = db.Column(db.Float, nullable=True)
    cost_price_cny = db.Column(db.Float, nullable=True)
    notes = db.Column(db.Text, default='')
    created_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))

class ExchangeRate(db.Model):
    """Latest exchange rates (manual or auto-updated)."""
    id = db.Column(db.Integer, primary_key=True)
    currency_pair = db.Column(db.String(10), unique=True, nullable=False)
    rate = db.Column(db.Float, nullable=False)
    updated_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))

# ============================================================
# Data: Shipping Rates, Products, Countries
# ============================================================

PRODUCTS = {
    "42cm": {"name": "42cm 3D Fan", "dims": "50.5x50.5x11.5", "weight": 3.0, "vol_weight": 5.8},
    "52cm": {"name": "52cm 3D Fan", "dims": "62x62x14", "weight": 4.5, "vol_weight": 10.8},
    "65cm": {"name": "65cm 3D Fan", "dims": "78x78x16", "weight": 6.5, "vol_weight": 19.5},
    "100cm": {"name": "100cm 3D Fan", "dims": "118x118x20", "weight": 12.0, "vol_weight": 55.7},
}

SHIPPING_RATES = {
    # Europe
    "NL": {"name": "Netherlands", "region": "Europe", "vat": 0.21, "ddu_min": 55, "ddu_max": 70, "ddp_min": 125, "ddp_max": 140, "transit": "7-12"},
    "DE": {"name": "Germany", "region": "Europe", "vat": 0.19, "ddu_min": 55, "ddu_max": 70, "ddp_min": 120, "ddp_max": 140, "transit": "7-10"},
    "FR": {"name": "France", "region": "Europe", "vat": 0.20, "ddu_min": 58, "ddu_max": 75, "ddp_min": 125, "ddp_max": 145, "transit": "7-12"},
    "BE": {"name": "Belgium", "region": "Europe", "vat": 0.21, "ddu_min": 58, "ddu_max": 75, "ddp_min": 125, "ddp_max": 140, "transit": "7-12"},
    "ES": {"name": "Spain", "region": "Europe", "vat": 0.21, "ddu_min": 62, "ddu_max": 78, "ddp_min": 130, "ddp_max": 150, "transit": "8-13"},
    "IT": {"name": "Italy", "region": "Europe", "vat": 0.22, "ddu_min": 62, "ddu_max": 80, "ddp_min": 135, "ddp_max": 155, "transit": "8-13"},
    "GB": {"name": "United Kingdom", "region": "Europe", "vat": 0.20, "ddu_min": 58, "ddu_max": 72, "ddp_min": 125, "ddp_max": 145, "transit": "7-12"},
    "PL": {"name": "Poland", "region": "Europe", "vat": 0.23, "ddu_min": 60, "ddu_max": 75, "ddp_min": 128, "ddp_max": 145, "transit": "8-12"},
    "SE": {"name": "Sweden", "region": "Europe", "vat": 0.25, "ddu_min": 62, "ddu_max": 78, "ddp_min": 132, "ddp_max": 150, "transit": "8-13"},
    "AT": {"name": "Austria", "region": "Europe", "vat": 0.20, "ddu_min": 60, "ddu_max": 75, "ddp_min": 128, "ddp_max": 145, "transit": "7-11"},
    "CH": {"name": "Switzerland", "region": "Europe", "vat": 0.077, "ddu_min": 62, "ddu_max": 78, "ddp_min": 130, "ddp_max": 148, "transit": "7-12"},
    "CZ": {"name": "Czech Republic", "region": "Europe", "vat": 0.21, "ddu_min": 60, "ddu_max": 75, "ddp_min": 128, "ddp_max": 145, "transit": "8-12"},
    "HU": {"name": "Hungary", "region": "Europe", "vat": 0.27, "ddu_min": 60, "ddu_max": 76, "ddp_min": 130, "ddp_max": 148, "transit": "8-13"},
    "PT": {"name": "Portugal", "region": "Europe", "vat": 0.23, "ddu_min": 64, "ddu_max": 80, "ddp_min": 135, "ddp_max": 155, "transit": "8-14"},
    "GR": {"name": "Greece", "region": "Europe", "vat": 0.24, "ddu_min": 65, "ddu_max": 82, "ddp_min": 138, "ddp_max": 158, "transit": "9-15"},
    # North America
    "US": {"name": "United States", "region": "North America", "vat": 0.0, "ddu_min": 42, "ddu_max": 62, "ddp_min": 80, "ddp_max": 110, "transit": "6-10"},
    "CA": {"name": "Canada", "region": "North America", "vat": 0.05, "ddu_min": 52, "ddu_max": 72, "ddp_min": 95, "ddp_max": 120, "transit": "7-12"},
    "MX": {"name": "Mexico", "region": "North America", "vat": 0.16, "ddu_min": 55, "ddu_max": 75, "ddp_min": 100, "ddp_max": 130, "transit": "8-14"},
    # Oceania
    "AU": {"name": "Australia", "region": "Oceania", "vat": 0.10, "ddu_min": 42, "ddu_max": 62, "ddp_min": 82, "ddp_max": 105, "transit": "6-10"},
    "NZ": {"name": "New Zealand", "region": "Oceania", "vat": 0.15, "ddu_min": 48, "ddu_max": 68, "ddp_min": 92, "ddp_max": 112, "transit": "7-10"},
    # Middle East
    "AE": {"name": "UAE", "region": "Middle East", "vat": 0.05, "ddu_min": 45, "ddu_max": 65, "ddp_min": 85, "ddp_max": 110, "transit": "6-10"},
    "SA": {"name": "Saudi Arabia", "region": "Middle East", "vat": 0.15, "ddu_min": 48, "ddu_max": 68, "ddp_min": 90, "ddp_max": 120, "transit": "7-12"},
    "QA": {"name": "Qatar", "region": "Middle East", "vat": 0.05, "ddu_min": 48, "ddu_max": 68, "ddp_min": 92, "ddp_max": 118, "transit": "7-12"},
    "KW": {"name": "Kuwait", "region": "Middle East", "vat": 0.05, "ddu_min": 48, "ddu_max": 68, "ddp_min": 92, "ddp_max": 118, "transit": "7-12"},
    # Asia
    "JP": {"name": "Japan", "region": "Asia", "vat": 0.10, "ddu_min": 38, "ddu_max": 58, "ddp_min": 78, "ddp_max": 105, "transit": "5-8"},
    "KR": {"name": "South Korea", "region": "Asia", "vat": 0.10, "ddu_min": 38, "ddu_max": 55, "ddp_min": 75, "ddp_max": 100, "transit": "5-8"},
    "SG": {"name": "Singapore", "region": "Asia", "vat": 0.09, "ddu_min": 35, "ddu_max": 52, "ddp_min": 72, "ddp_max": 95, "transit": "5-8"},
    "MY": {"name": "Malaysia", "region": "Asia", "vat": 0.10, "ddu_min": 35, "ddu_max": 52, "ddp_min": 72, "ddp_max": 95, "transit": "5-8"},
    "TH": {"name": "Thailand", "region": "Asia", "vat": 0.07, "ddu_min": 35, "ddu_max": 52, "ddp_min": 72, "ddp_max": 95, "transit": "5-9"},
    "PH": {"name": "Philippines", "region": "Asia", "vat": 0.12, "ddu_min": 38, "ddu_max": 55, "ddp_min": 75, "ddp_max": 100, "transit": "6-10"},
    "ID": {"name": "Indonesia", "region": "Asia", "vat": 0.11, "ddu_min": 38, "ddu_max": 55, "ddp_min": 78, "ddp_max": 105, "transit": "6-10"},
}

def calculate_volumetric_weight(l, w, h, divisor=5000):
    """Calculate volumetric weight from cm dimensions."""
    return (l * w * h) / divisor

def get_shipping_estimate(country_code, product_model, mode="DDP"):
    """Get estimated shipping cost for a country and product."""
    country = SHIPPING_RATES.get(country_code, {})
    product = PRODUCTS.get(product_model, {})

    if not country or not product:
        return None

    chargeable = max(product["weight"], product["vol_weight"])

    # Base rate per kg varies by region and mode
    region_rates = {
        "Europe": {"DDP": 7.3, "DDU": 4.5},
        "North America": {"DDP": 6.5, "DDU": 3.8},
        "Oceania": {"DDP": 6.0, "DDU": 3.5},
        "Middle East": {"DDP": 6.8, "DDU": 4.0},
        "Asia": {"DDP": 5.5, "DDU": 3.2},
    }

    region = country.get("region", "Europe")
    rate_per_kg = region_rates.get(region, {}).get(mode, 7.3)

    shipping = round(chargeable * rate_per_kg + 15)  # $15 safety buffer

    # Ensure it falls within the country's range
    if mode == "DDP":
        shipping = max(country["ddp_min"], min(country["ddp_max"], shipping))
    else:
        shipping = max(country["ddu_min"], min(country["ddu_max"], shipping))

    return {
        "shipping_cost": shipping,
        "chargeable_weight": round(chargeable, 1),
        "vol_weight": round(product["vol_weight"], 1),
        "actual_weight": product["weight"],
        "dims": product["dims"],
    }

def calculate_tax(product_price, shipping_cost, country_code, mode):
    """Calculate import tax/VAT."""
    country = SHIPPING_RATES.get(country_code, {})
    vat_rate = country.get("vat", 0.21)

    if mode == "DDP":
        # In DDP, VAT is already included in the shipping - but estimate it for breakdown
        cif_value = product_price + shipping_cost * 0.7  # approximate freight portion
        tax = round(cif_value * vat_rate)
    else:
        # DDU: customer pays VAT on CIF
        cif_value = product_price + shipping_cost
        tax = round(cif_value * vat_rate)

    return {"vat_rate": vat_rate, "tax_amount": tax}

def generate_english_quote(product_price, shipping_cost, tax_amount, total, country_code, mode, transit, product_name):
    """Generate English quote text for customer."""
    country = SHIPPING_RATES.get(country_code, {})
    country_name = country.get("name", country_code)

    if mode == "DDP":
        return f"""Product: {product_name}
Product Price: ${product_price}
Shipping (DDP): ${shipping_cost}
Delivery Time: {transit} business days
Delivery to: {country_name}
────────────────────────
Total: ${total}

All import duties, VAT, and customs clearance fees are included in the shipping cost. Door-to-door delivery."""
    else:
        return f"""Product: {product_name}
Product Price: ${product_price}
Shipping (DDU): ${shipping_cost}
Delivery Time: {transit} business days
Delivery to: {country_name}
────────────────────────
Subtotal: ${product_price + shipping_cost}

Import VAT and customs clearance fees are to be paid by the consignee upon arrival.
Estimated VAT: ~${tax_amount}"""

# ============================================================
# Routes
# ============================================================

def login_required(f):
    @functools.wraps(f)
    def decorated(*args, **kwargs):
        if not session.get('logged_in'):
            return redirect(url_for('login'))
        return f(*args, **kwargs)
    return decorated

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        password = request.form.get('password', '')
        if password == os.environ.get('APP_PASSWORD', 'rj2026'):
            session['logged_in'] = True
            return redirect(url_for('index'))
        return render_template('login.html', error='Invalid password')
    return render_template('login.html', error='')

@app.route('/logout')
def logout():
    session.pop('logged_in', None)
    return redirect(url_for('login'))

@app.route('/')
@login_required
def index():
    return render_template('index.html')

@app.route('/api/countries')
@login_required
def api_countries():
    """Return all supported countries."""
    result = []
    for code, c in SHIPPING_RATES.items():
        result.append({
            "code": code,
            "name": c["name"],
            "region": c["region"],
            "vat": c["vat"],
            "transit": c["transit"],
        })
    return jsonify(result)

@app.route('/api/products')
@login_required
def api_products():
    """Return all products."""
    return jsonify(PRODUCTS)

@app.route('/api/calculate', methods=['POST'])
@login_required
def api_calculate():
    """Calculate shipping, tax, and total."""
    data = request.get_json()
    country_code = data.get('country', '').upper()
    product_model = data.get('model', '42cm')
    product_price = float(data.get('price', 0))
    mode = data.get('mode', 'DDP').upper()
    cost_price_cny = float(data.get('cost_cny', 0))

    if country_code not in SHIPPING_RATES:
        return jsonify({"error": "Country not supported"}), 400

    if product_model not in PRODUCTS:
        return jsonify({"error": "Product model not found"}), 400

    country = SHIPPING_RATES[country_code]
    product = PRODUCTS[product_model]

    # Shipping estimate
    estimate = get_shipping_estimate(country_code, product_model, mode)
    if not estimate:
        return jsonify({"error": "Could not calculate shipping"}), 500

    # Tax
    tax_info = calculate_tax(product_price, estimate["shipping_cost"], country_code, mode)

    # Totals
    if mode == "DDP":
        total = product_price + estimate["shipping_cost"]
        tax_display = tax_info["tax_amount"]
    else:
        total = product_price + estimate["shipping_cost"]
        tax_display = tax_info["tax_amount"]

    # Profit calculation
    profit = None
    profit_pct = None
    if cost_price_cny > 0:
        # Assume USD/CNY ~7.25
        usd_cny = 7.25
        cost_usd = round(cost_price_cny / usd_cny, 2)
        total_cost = cost_usd + estimate["shipping_cost"]
        if mode == "DDU":
            total_cost += tax_info["tax_amount"]  # DDU: you may prepay tax
        profit = round(total - total_cost, 2)
        profit_pct = round((profit / total) * 100, 1) if total > 0 else 0

    # English quote
    quote_text = generate_english_quote(
        product_price, estimate["shipping_cost"],
        tax_display, total, country_code, mode,
        country["transit"], product["name"]
    )

    return jsonify({
        "country": {"code": country_code, "name": country["name"]},
        "product": product,
        "product_price": product_price,
        "mode": mode,
        "chargeable_weight": estimate["chargeable_weight"],
        "vol_weight": estimate["vol_weight"],
        "actual_weight": estimate["actual_weight"],
        "shipping_cost": estimate["shipping_cost"],
        "tax_amount": tax_display,
        "vat_rate": country["vat"],
        "total_price": total,
        "transit": country["transit"],
        "profit": profit,
        "profit_pct": profit_pct,
        "quote_text": quote_text,
    })

@app.route('/api/quotes', methods=['GET', 'POST'])
@login_required
def api_quotes():
    """List or save quote records."""
    if request.method == 'POST':
        data = request.get_json()
        record = QuoteRecord(
            customer_name=data.get('customer_name', ''),
            country_code=data['country_code'],
            product_model=data['product_model'],
            dims_cm=data['dims_cm'],
            actual_weight=data['actual_weight'],
            chargeable_weight=data['chargeable_weight'],
            product_price=data['product_price'],
            shipping_mode=data['shipping_mode'],
            shipping_cost=data['shipping_cost'],
            tax_amount=data['tax_amount'],
            total_price=data['total_price'],
            profit=data.get('profit'),
            cost_price_cny=data.get('cost_price_cny'),
            notes=data.get('notes', ''),
        )
        db.session.add(record)
        db.session.commit()
        return jsonify({"success": True, "id": record.id})

    # GET: list recent quotes
    quotes = QuoteRecord.query.order_by(QuoteRecord.created_at.desc()).limit(50).all()
    return jsonify([{
        "id": q.id,
        "customer_name": q.customer_name,
        "country_code": q.country_code,
        "product_model": q.product_model,
        "total_price": q.total_price,
        "created_at": q.created_at.isoformat() if q.created_at else None,
    } for q in quotes])

@app.route('/api/quote/<int:quote_id>')
@login_required
def api_get_quote(quote_id):
    """Get a single quote record."""
    q = QuoteRecord.query.get_or_404(quote_id)
    return jsonify({
        "id": q.id,
        "customer_name": q.customer_name,
        "country_code": q.country_code,
        "product_model": q.product_model,
        "dims_cm": q.dims_cm,
        "actual_weight": q.actual_weight,
        "chargeable_weight": q.chargeable_weight,
        "product_price": q.product_price,
        "shipping_mode": q.shipping_mode,
        "shipping_cost": q.shipping_cost,
        "tax_amount": q.tax_amount,
        "total_price": q.total_price,
        "profit": q.profit,
        "cost_price_cny": q.cost_price_cny,
        "notes": q.notes,
        "created_at": q.created_at.isoformat() if q.created_at else None,
    })

@app.route('/api/exchange-rates')
@login_required
def api_exchange_rates():
    """Get current exchange rates."""
    rates = ExchangeRate.query.all()
    return jsonify([{"pair": r.currency_pair, "rate": r.rate} for r in rates])

# ============================================================
# Error handlers
# ============================================================

@app.errorhandler(404)
def not_found(e):
    return jsonify({"error": "Not found"}), 404

# ============================================================
# Main
# ============================================================

if __name__ == '__main__':
    with app.app_context():
        db.create_all()
        # Seed exchange rates if empty
        if not ExchangeRate.query.first():
            default_rates = [
                ("USD/CNY", 7.25), ("EUR/USD", 1.09), ("EUR/CNY", 7.90),
                ("GBP/USD", 1.28), ("AUD/USD", 0.65), ("JPY/USD", 0.0067),
            ]
            for pair, rate in default_rates:
                db.session.add(ExchangeRate(currency_pair=pair, rate=rate))
            db.session.commit()
    app.run(host='0.0.0.0', port=5020, debug=True)

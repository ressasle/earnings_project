import os
import time
import sys
import requests
from datetime import datetime, timedelta, timezone
from utils.supabase_client import get_supabase_client

def normalize_for_eodhd_api(ticker_eod: str) -> str:
    """Maps portfolio trading suffixes to EODHD's unified fundamentals exchanges."""
    if not ticker_eod: return ""
    symbol = str(ticker_eod).upper().strip()
    if symbol.endswith(".LSE"): return symbol.replace(".LSE", ".UK")
    if symbol.endswith(".XETRA"): return symbol.replace(".XETRA", ".F")
    return symbol

def fetch_eod_pricing_history(ticker: str, api_token: str, limit: int = 30):
    """Fetches a historical price array from EODHD to calculate performance shifts."""
    api_ticker = normalize_for_eodhd_api(ticker)
    url = f"https://eodhd.com/api/eod/{api_ticker}?api_token={api_token}&fmt=json&limit={limit}"
    try:
        res = requests.get(url, timeout=15)
        return res.json() if res.status_code == 200 else []
    except Exception:
        return []

def extract_earnings_metadata(earnings_data):
    """Parses historical listings to isolate past, future and surprise parameters."""
    if not isinstance(earnings_data, dict): return None, None, 0, 0, 0
    history = earnings_data.get("History", {})
    if not history or not isinstance(history, dict): return None, None, 0, 0, 0
        
    today_str = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    last_date, next_date = None, None
    eps_act, eps_est, eps_pct = 0, 0, 0
    
    for _, entry in sorted(history.items(), key=lambda x: x[1].get('reportDate', ''), reverse=True):
        r_date = entry.get("reportDate")
        if not r_date: continue
        if r_date > today_str:
            if next_date is None or r_date < next_date: next_date = r_date
        else:
            if last_date is None or r_date > last_date:
                last_date = r_date
                eps_act = entry.get("epsActual")
                eps_est = entry.get("epsEstimate")
                eps_pct = entry.get("epsSurprisePercent")
                
    return last_date, next_date, eps_act, eps_est, eps_pct

def enrich_all(portfolio_id=None, verbose=True, days_lookback=14):
    """Step 0 Core: Fills kasona_portfolio_assets columns and queues matching tickers."""
    sb = get_supabase_client()
    api_token = os.environ.get("EODHD_API_KEY") or os.environ.get("EOD_API_TOKEN")
    
    print("\n" + "="*70)
    print("📋 [STEP 0] RUNNING PACED SCHEMA-ALIGNED PORTFOLIO ENRICHMENT")
    print("="*70)

    # 1. Pull active asset baseline mappings
    query = sb.table("kasona_portfolio_assets").select("*")
    if portfolio_id: query = query.eq("portfolio_id", portfolio_id)
    assets = query.execute().data
    print(f"ℹ️ Loaded {len(assets)} raw asset rows from database framework.")

    ticker_map = {a["ticker_eod"]: a for a in assets if a.get("ticker_eod")}
    lookback_start = (datetime.now(timezone.utc) - timedelta(days=days_lookback)).date()
    updated_tickers = []

    for ticker, asset_row in ticker_map.items():
        api_ticker = normalize_for_eodhd_api(ticker)
        print(f"📡 Processing tracking node parameters for: {ticker} -> Routed via: {api_ticker}")
        
        # Explicit Pacing to guard against API rate limits
        time.sleep(0.5)
        
        # 2. Query structural fundamentals payload
        fund_url = f"https://eodhd.com/api/fundamentals/{api_ticker}?api_token={api_token}&fmt=json"
        try:
            fund_res = requests.get(fund_url, timeout=15)
            if fund_res.status_code != 200: continue
            raw_payload = fund_res.json()
        except Exception:
            continue

        general = raw_payload.get("General", {})
        earnings = raw_payload.get("Earnings", {})
        highlights = raw_payload.get("Highlights", {})
        
        last_date_str, next_date_str, eps_act, eps_est, eps_surprise = extract_earnings_metadata(earnings)
        
        # 3. Fetch Pricing arrays to populate math matrices
        price_history = fetch_eod_pricing_history(ticker, api_token, limit=30)
        current_price, prev_quarter_price, yoy_price, qoq_price = None, None, None, None
        
        if price_history and len(price_history) > 0:
            current_price = float(price_history[0].get("close", 0))
            if len(price_history) > 5: prev_quarter_price = float(price_history[5].get("close", 0))
            if current_price and prev_quarter_price:
                qoq_price = round(((current_price - prev_quarter_price) / prev_quarter_price) * 100, 2)

        # Determine benchmark classification (QQQ for tech, else SPY)
        is_tech = "TECH" in str(general.get("Sector", "")).upper() or "SOFTWARE" in str(general.get("Industry", "")).upper()
        benchmark_ticker = "QQQ.US" if is_tech else "SPY.US"

        # 4. Fill every column present inside your DDL layout
        portfolio_update_payload = {
            "stock_name": general.get("Name"),
            "exchange": general.get("Exchange"),
            "exchange_code": general.get("Exchange"),
            "country_name": general.get("CountryName"),
            "country": general.get("CountryISO"),
            "sector": general.get("Sector"),
            "industry": general.get("Industry"),
            "description": general.get("Description"),
            "currency": general.get("CurrencyCode"),
            "isin": general.get("ISIN"),
            "website_url": general.get("WebUrl"),
            "logo_url": general.get("LogoURL"),
            "fiscal_year_end": str(general.get("FiscalYearEnd")),
            "officers": general.get("Officers"), 
            "last_earnings_date": last_date_str if last_date_str else None,
            "next_earnings_date": next_date_str if next_date_str else None,
            "last_earnings_period": "Q1 2026",
            "current_price": current_price,
            "prev_quarter_price": prev_quarter_price,
            "qoq_price": qoq_price,
            "yoy_price": yoy_price if yoy_price else 0.0,
            "price_updated_at": datetime.now(timezone.utc).isoformat(),
            "category": "Equities Asset Group",
            "asset_class": "Stocks",
            "enriched": True,
            "earnings_active": True if last_date_str else False,
            "updated_at": datetime.now(timezone.utc).isoformat()
        }

        # Commit updates directly back to your public.kasona_portfolio_assets layout row
        try:
            sb.table("kasona_portfolio_assets").update(portfolio_update_payload).eq("id", asset_row["id"]).execute()
        except Exception as db_err:
            print(f"   ❌ Database columns initialization failure for row {asset_row['id']}: {db_err}")

        # 5. Route to execution queue based on lookback windows
        if last_date_str:
            try:
                ld = datetime.strptime(last_date_str, "%Y-%m-%d").date()
                if ld >= lookback_start:
                    if ticker not in updated_tickers:
                        updated_tickers.append(ticker)
                        print(f"   🚜 [QUEUED] {ticker} accepted for production pipeline run.")
            except Exception:
                pass
                
    print(f"\n🏁 [STEP 0 FINISHED] Active worker queue successfully constructed: {updated_tickers}\n")
    return {"updated_tickers": updated_tickers}

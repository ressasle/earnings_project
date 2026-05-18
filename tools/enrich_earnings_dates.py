import os
import asyncio
import aiohttp
from datetime import datetime, timedelta, timezone
from utils.supabase_client import get_supabase_client

def normalize_for_eodhd_api(ticker_eod: str) -> str:
    """ Maps portfolio tracking suffixes to EODHD's unified corporate fundamentals exchange codes. """
    if not ticker_eod:
        return ""
    symbol = str(ticker_eod).upper().strip()
    
    # 1. Map London Stock Exchange to EODHD UK root
    if symbol.endswith(".LSE"):
        return symbol.replace(".LSE", ".UK")
        
    # 2. Map German Xetra listings to unified Frankfurt fundamentals stream
    if symbol.endswith(".XETRA"):
        return symbol.replace(".XETRA", ".F")
        
    return symbol

def extract_earnings_dates(earnings_data):
    """Parses historical statements to identify past and forward release dates."""
    if not isinstance(earnings_data, dict):
        return None, None
    history = earnings_data.get("History", {})
    if not history or not isinstance(history, dict):
        return None, None
        
    today_str = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    last_date, next_date = None, None
    
    for _, entry in history.items():
        r_date = entry.get("reportDate")
        if not r_date:
            continue
        if r_date > today_str:
            if next_date is None or r_date < next_date:
                next_date = r_date
        else:
            if last_date is None or r_date > last_date:
                last_date = r_date
                
    return last_date, next_date

async def enrich_all(portfolio_id=None, verbose=True, days_lookback=14):
    """
    Step 0 Engine: Populates empty portfolio_assets table columns and builds the worker queue.
    Automatically translates international suffixes to bypass 404 endpoint errors.
    """
    sb = get_supabase_client()
    api_token = os.environ.get("EODHD_API_KEY") or os.environ.get("EOD_API_TOKEN")
    
    print("\n" + "="*70)
    print("📋 [STEP 0] RUNNING ROUTED PORTFOLIO ENRICHMENT LAYER")
    print(f"   Deduplication Filter: DISABLED | Lookback Scan Window: {days_lookback} Days")
    print("="*70)

    # Extract asset array list from public.kasona_portfolio_assets
    query = sb.table("kasona_portfolio_assets").select("*")
    if portfolio_id:
        query = query.eq("portfolio_id", portfolio_id)
    assets = query.execute().data

    print(f"ℹ️ Extracted {len(assets)} total asset rows from database tracking matrix.")

    ticker_map = {}
    for a in assets:
        if a.get("ticker_eod"):
            ticker_map.setdefault(a["ticker_eod"], []).append(a)

    lookback_start = (datetime.now(timezone.utc) - timedelta(days=days_lookback)).date()
    updated_tickers = []

    async with aiohttp.ClientSession() as session:
        for ticker in list(ticker_map.keys()):
            # Run the automated routing normalization to transform .XETRA -> .F and .LSE -> .UK
            api_target_ticker = normalize_for_eodhd_api(ticker)
            url = f"https://eodhd.com/api/fundamentals/{api_target_ticker}?api_token={api_token}&fmt=json"
            
            try:
                async with session.get(url, timeout=15) as resp:
                    if resp.status != 200:
                        print(f"❌ [API ERROR] Routed target {api_target_ticker} ({ticker}) returned: {resp.status}")
                        continue
                    raw_payload = await resp.json(content_type=None)
            except Exception as e:
                print(f"❌ [NETWORK ERROR] Connection timeout for {ticker}: {e}")
                continue

            if not raw_payload or not isinstance(raw_payload, dict):
                print(f"⚠️ [FORMAT ERROR] Empty or invalid payload maps for {ticker}")
                continue

            general = raw_payload.get("General", {})
            earnings = raw_payload.get("Earnings", {})
            
            last_date_str, next_date_str = extract_earnings_dates(earnings)

            # Map corporate metadata to fill your asset table columns
            portfolio_update_payload = {
                "stock_name": general.get("Name"),
                "exchange": general.get("Exchange"),
                "exchange_code": general.get("Exchange"),
                "country_name": general.get("CountryName"),
                "sector": general.get("Sector"),
                "industry": general.get("Industry"),
                "description": general.get("Description"),
                "currency": general.get("CurrencyCode"),
                "isin": general.get("ISIN"),
                "website_url": general.get("WebUrl"),
                "logo_url": general.get("LogoURL"),
                "last_earnings_date": last_date_str if last_date_str else None,
                "next_earnings_date": next_date_str if next_date_str else None,
                "enriched": True,
                "updated_at": datetime.now(timezone.utc).isoformat()
            }

            # Sync data properties to your database row configurations
            for asset in ticker_map[ticker]:
                try:
                    sb.table("kasona_portfolio_assets").update(portfolio_update_payload).eq("id", asset["id"]).execute()
                except Exception as db_err:
                    print(f"   [WARN] Database column sync failure for ID {asset['id']}: {db_err}")

            if not last_date_str:
                print(f"⚠️ [SKIPPED] {ticker}: EODHD records show zero historical release stamps.")
                continue

            try:
                ld = datetime.strptime(last_date_str, "%Y-%m-%d").date()
                is_recent = ld >= lookback_start

                if not is_recent:
                    print(f"   [SKIPPED] {ticker}: Last report date ({last_date_str}) falls outside current execution window.")
                    continue

                if ticker not in updated_tickers:
                    updated_tickers.append(ticker)
                    print(f"   扭 [QUEUED] {ticker} routed via {api_target_ticker} -> Added to pipeline. Reported: {last_date_str}")

            except Exception as eval_err:
                print(f"   [WARN] Internal filtering calculation exception for {ticker}: {eval_err}")

            await asyncio.sleep(0.2)
            
    print("="*70)
    print(f"🏁 [STEP 0 COMPLETE] Columns updated across portfolios. Active Queue Size: {len(updated_tickers)}")
    print("="*70 + "\n")
    return {"updated_tickers": updated_tickers}

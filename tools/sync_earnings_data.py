#!/usr/bin/env python3
import os
import sys
import requests
from datetime import datetime, timezone
from utils.supabase_client import get_supabase_client

def sync_ticker(ticker: str, period: str = "Q1 2026"):
    """
    Ingests financial statement metrics from EODHD, generates an explicit 
    source lineage tracking manifest, and populates the database row.
    """
    sb = get_supabase_client()
    api_token = os.environ.get("EODHD_API_KEY") or os.environ.get("EOD_API_TOKEN")
    
    # Standardize our exchange routing targets to prevent validation gaps
    api_ticker = str(ticker).upper().strip().replace(".XETRA", ".DE").replace(".LSE", ".UK")
    
    print(f"📡 Ingesting metrics trace for tracking key: {ticker}...")
    
    # Define exact tracking URIs
    fundamentals_endpoint = f"https://eodhd.com/api/fundamentals/{api_ticker}"
    pricing_endpoint = f"https://eodhd.com/api/eod/{api_ticker}"
    
    # 1. FETCH FUNDAMENTALS PACK
    fund_url = f"{fundamentals_endpoint}?api_token={api_token}&fmt=json"
    try:
        fund_res = requests.get(fund_url, timeout=15)
        if fund_res.status_code != 200:
            raise Exception(f"EODHD server returned response status indicator: {fund_res.status_code}")
        payload = fund_res.json()
    except Exception as e:
        print(f"❌ [DATA INGESTION CRASH] Fundamentals extraction failed: {e}")
        raise e

    # Extract specific nesting buckets
    general = payload.get("General", {})
    highlights = payload.get("Highlights", {})
    earnings = payload.get("Earnings", {})
    financials = payload.get("Financials", {})
    
    company_name = general.get("Name", ticker)
    
    # Extract Statements
    income_stmt = financials.get("Income_Statement", {}).get("quarterly", {})
    latest_income = list(income_stmt.values())[0] if income_stmt else {}
    revenue = float(latest_income.get("totalRevenue") or 0.0)
    
    # Extract Earnings History parameters
    earnings_hist = earnings.get("History", {})
    latest_key = list(earnings_hist.keys())[0] if earnings_hist else None
    latest_earning_node = earnings_hist[latest_key] if latest_key else {}
    eps_actual = float(latest_earning_node.get("epsActual") or 0.0)
    eps_estimate = float(latest_earning_node.get("epsEstimate") or 0.0)
    eps_surprise = float(latest_earning_node.get("epsSurprisePercent") or 0.0)

    # 2. CONSTRUCT DYNAMIC HIGH-FIDELITY SOURCE AUDIT MANIFEST LOG
    qa_source_log = {
        "metadata": {
            "synchronized_at": datetime.now(timezone.utc).isoformat(),
            "target_api_ticker": api_ticker,
            "data_provider": "EODHD API Platform"
        },
        "lineage": {
            "company_name": {"source_endpoint": fundamentals_endpoint, "field_path": "General -> Name"},
            "revenue_actual": {"source_endpoint": fundamentals_endpoint, "field_path": "Financials -> Income_Statement -> quarterly -> totalRevenue"},
            "eps_actual": {"source_endpoint": fundamentals_endpoint, "field_path": "Earnings -> History -> epsActual"},
            "eps_estimate": {"source_endpoint": fundamentals_endpoint, "field_path": "Earnings -> History -> epsEstimate"},
            "eps_surprise_percent": {"source_endpoint": fundamentals_endpoint, "field_path": "Earnings -> History -> epsSurprisePercent"},
            "financial_highlights": {"source_endpoint": fundamentals_endpoint, "field_path": "Highlights -> PERatio/ProfitMargin"}
        }
    }

    print(f"📝 Lineage verification manifest mapped for {ticker}. Committing database ledger rows...")

    # 3. UPSERT RECORDS INTO QUARTERLY_EARNINGS TABLE WITH THE SOURCE LOG INCLUDED
    update_payload = {
        "ticker_eod": ticker,
        "fiscal_period": period,
        "quarter": "Q1",
        "fiscal_year": 2026,
        "company_name": company_name,
        "revenue_actual": revenue,
        "eps_actual": eps_actual,
        "eps_estimate": eps_estimate,
        "eps_surprise_percent": eps_surprise,
        "qa_source_log": qa_source_log,  # Writes source manifest dictionary straight to JSONB column
        "status": "pending",
        "review_status": "pending",
        "updated_at": datetime.now(timezone.utc).isoformat()
    }

    try:
        sb.table("quarterly_earnings").upsert(
            update_payload, 
            on_conflict="ticker_eod,fiscal_period"
        ).execute()
        print(f"✅ [SYNC SUCCESS] Ingestion ledger updated cleanly with QA source logs for {ticker}.")
    except Exception as db_err:
        print(f"❌ [DATABASE FAIL] Critical error saving payload values for row {ticker}: {db_err}")
        raise db_err

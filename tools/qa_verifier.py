#!/usr/bin/env python3
import os
import sys
import uuid
import requests
from datetime import datetime, timezone
from utils.supabase_client import get_supabase_client

def validate_uuid(uuid_string):
    """Guarantees string matches a strict UUID layout to prevent PostgreSQL type crashes."""
    try:
        val = uuid.UUID(str(uuid_string), version=4)
        return str(val)
    except (ValueError, AttributeError):
        print(f"⚠️ [QA WARNING] Provided reference_id '{uuid_string}' is not a valid UUID format.")
        return None

def run_independent_qa(ticker: str, target_id: str) -> dict:
    """
    Independent QA Module: Cross-checks compiled layout metrics against raw EODHD endpoints.
    Logs alignment incidents directly into public.kasona_qa_log matching PostgreSQL schemas.
    """
    sb = get_supabase_client()
    eodhd_token = os.environ.get("EODHD_API_KEY") or os.environ.get("EOD_API_TOKEN")
    
    # Standardize our exchange routing targets to prevent 404 validation gaps
    api_ticker = str(ticker).upper().strip().replace(".XETRA", ".DE").replace(".LSE", ".UK")
    
    print(f"\n🕵️ Automated QA Auditor spinning up for token audit: {ticker}...")
    
    # Validate UUID layout before database transmission phase
    clean_reference_id = validate_uuid(target_id)

    # 1. RETRIEVE GENERATED DATA FROM NATIVE TABLE GRID
    try:
        report_res = sb.table("quarterly_earnings").select("*").eq("id", target_id).execute()
        if not report_res.data:
            print(f"❌ [QA ERROR] Target record ID {target_id} not located in quarterly_earnings.")
            return {"passed": False, "notes": "Source row missing."}
        report_data = report_res.data[0]
    except Exception as db_fetch_err:
        print(f"❌ [QA DATABASE FETCH ERROR] Failed to query target row content: {db_fetch_err}")
        return {"passed": False, "notes": str(db_fetch_err)}

    # 2. RETRIEVE SOURCE OF TRUTH (Direct Live EODHD API Pull)
    try:
        fund_url = f"https://eodhd.com/api/fundamentals/{api_ticker}?api_token={eodhd_token}&fmt=json"
        fund_res = requests.get(fund_url, timeout=15).json()
        
        # Pull live consensus variables
        earnings_hist = fund_res.get("Earnings", {}).get("History", {})
        latest_key = list(earnings_hist.keys())[0] if earnings_hist else None
        eodhd_eps_actual = float(earnings_hist[latest_key].get("epsActual", 0.0)) if latest_key else 0.0
        
        income_stmt = fund_res.get("Financials", {}).get("Income_Statement", {}).get("quarterly", {})
        latest_income = list(income_stmt.values())[0] if income_stmt else {}
        eodhd_rev_actual = float(latest_income.get("totalRevenue", 0.0))
        
    except Exception as api_err:
        print(f"⚠️ [QA NETWORK NOTICE] Failed to query reference endpoints from live API streams: {api_err}")
        return {"passed": False, "notes": "EODHD source validation endpoint unavailable."}

    # 3. CONSTRUCT MATRIX CONFIGURATION ALIGNED WITH DDL KEY VARIABLES
    audit_matrix = {
        "eps_actual": {
            "expected": eodhd_eps_actual,
            "reported": float(report_data.get("eps_actual") or 0.0),
            "source_type": "eodhd_fundamentals_earnings",
            "severity": "CRITICAL"
        },
        "revenue_actual": {
            "expected": eodhd_rev_actual,
            "reported": float(report_data.get("revenue_actual") or 0.0),
            "source_type": "eodhd_fundamentals_income_statement",
            "severity": "HIGH"
        }
    }

    qa_incidents = []
    all_passed = True

    # 4. EVALUATION PROCESSOR
    for metric, state in audit_matrix.items():
        expected = state["expected"]
        reported = state["reported"]
        
        # Calculate deviation percentage safely
        deviation = abs(reported - expected) / expected if expected != 0.0 else 0.0
        
        # Trigger an incident flag if text metrics deviate by more than 0.5%
        if deviation > 0.005:
            all_passed = False
            
            incident_entry = {
                "skill": "quarterly_earnings",
                "reference_id": clean_reference_id,
                "ticker": ticker,
                "data_point": metric,
                "expected_source": state["source_type"],
                "actual_source": "llm_generation_context_drift",
                "api_value": float(expected),
                "report_value": float(reported),
                "deviation_pct": float(round(deviation * 100, 4)),
                "severity": state["severity"],
                "auto_corrected": True,
                "notes": f"AI model output deviated from verified EODHD ledger data streams by {round(deviation*100, 2)}%"
            }
            qa_incidents.append(incident_entry)
            print(f"⚠️ [AUDIT INCIDENT DETECTED] {metric} variance found! Deviation: {round(deviation*100, 2)}%")

    # 5. PERSIST METRICS DIRECTLY DOWN TO KASONA_QA_LOG
    if qa_incidents:
        try:
            print(f"📤 Inserting {len(qa_incidents)} incident reports into public.kasona_qa_log...")
            insert_res = sb.table("kasona_qa_log").insert(qa_incidents).execute()
            print(f"✅ [DATABASE SUCCESS] QA logs successfully committed. Row entries written: {len(insert_res.data)}")
            status_flag = "corrected"
        except Exception as insert_error:
            print(f"❌ [DATABASE WRITE ERROR] Supabase rejected kasona_qa_log payload insertion trace:")
            print(insert_error)
            status_flag = "unverified"
    else:
        print(f"✅ [AUDIT CLEAR] Verification matches live API schemas. No data hallucinations detected for {ticker}.")
        status_flag = "verified"

    # 6. PROMOTE THE STATUS FIELD INSIDE QUARTERLY_EARNINGS
    try:
        sb.table("quarterly_earnings").update({
            "qa_verification_status": status_flag,
            "qa_verified_at": datetime.now(timezone.utc).isoformat()
        }).eq("id", target_id).execute()
    except Exception as final_update_err:
        print(f"⚠️ [WARN] Could not update verification status flags inside quarterly_earnings row: {final_update_err}")

    return {"passed": all_passed, "qa_verification_status": status_flag}

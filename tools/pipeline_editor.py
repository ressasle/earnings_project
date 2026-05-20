#!/usr/bin/env python3
import sys
from utils.supabase_client import get_supabase_client

def execute_pre_generation_verification_gate(ticker: str, period: str = "Q1 2026") -> bool:
    """
    Pre-Generation Gate Check: Reviews the relational ledger record context to verify 
    that data lineage metadata exists before permitting the LLM to run text generation.
    """
    sb = get_supabase_client()
    print(f"🔍 [GATE CHECK] Scanning data source safety markers for {ticker} - {period}...")
    
    try:
        res = sb.table("quarterly_earnings")\
            .select("id, qa_source_log")\
            .eq("ticker_eod", ticker)\
            .eq("fiscal_period", period)\
            .execute()
            
        if not res.data:
            print(f"❌ [GATE REJECTED] Access Denied for {ticker}: No data record initialized in database matching parameters.")
            return False
            
        record = res.data[0]
        source_log = record.get("qa_source_log")
        
        # Enforce strict NULL validation check against the jsonb structure keys
        if not source_log or source_log == {} or source_log is None:
            print(f"❌ [GATE REJECTED] Access Denied for {ticker}: 'qa_source_log' field is NULL or missing lineage traces.")
            print("   ↳ Reason: AI generation blocked to prevent potential metric hallucinations. Re-run Step 1 data ingestion first.")
            return False
            
        print(f"✅ [GATE PASSED] Data lineage trace verified for {ticker}. Proceeding to text narrative expansion loop.")
        return True
        
    except Exception as gate_exc:
        print(f"❌ [GATE FAILURE ERROR] Internal verification handler error occurred: {gate_exc}")
        return False

# Integrated execution example block:
# if not execute_pre_generation_verification_gate(ticker="VOD.LSE"):
#     raise Exception("Content expansion sequence terminated due to verification failure.")

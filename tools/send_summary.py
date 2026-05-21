#!/usr/bin/env python3
import os
import requests
from datetime import datetime, timezone
from utils.supabase_client import get_supabase_client

def compile_and_send_ops_summary():
    """Compiles a high-impact diagnostic markdown report and fires it live to operations alerts."""
    sb = get_supabase_client()
    print("[*] Compiling global operational metrics trace summary...")

    # Pull active relational state matrices
    earnings = sb.table("quarterly_earnings").select("*").execute().data or []
    assets = sb.table("kasona_portfolio_assets").select("*").execute().data or []
    qa_logs = sb.table("kasona_qa_log").select("*").execute().data or []

    total_produced = len(earnings)
    active_in_portfolio = sum(1 for a in assets if a.get("earnings_active"))
    critical_hallucinations = sum(1 for q in qa_logs if q.get("severity") == "CRITICAL")

    # Construct clean markdown text payload block matching summary parameters
    message = f"""
🦅 *KASONA SYSTEM OPERATIONS EXECUTIVE SUMMARY*
📅 Generated: {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')}
─────────────────────────────────────────
📊 *SYSTEM PERFORMANCE COUNTERS:*
- Total Automated Reports Compiled: `{total_produced}`
- Portfolio Asset Active Flags Enabled: `{active_in_portfolio}`
- Isolated Model Hallucinations Logged: `{len(qa_logs)}` (Critical: `{critical_hallucinations}`)

🚨 *RECENT INCIDENT REVIEWS (LAST 3 DETECTED ENTRANCES):*
"""
    for log in qa_logs[:3]:
        message += f"• ⚠️ *{log.get('ticker')}* [{log.get('data_point')}]: Drifted by `{log.get('deviation_pct')}%` (Severity: `{log.get('severity')}`)\n"

    # --- TELEGRAM COURIER ROUTING DISPATCH ---
    tg_token = os.environ.get("TELEGRAM_BOT_TOKEN")
    tg_chat_id = os.environ.get("TELEGRAM_CHAT_ID")
    
    if tg_token and tg_chat_id:
        tg_url = f"https://api.telegram.org/bot{tg_token}/sendMessage"
        try:
            requests.post(tg_url, json={
                "chat_id": tg_chat_id,
                "text": message,
                "parse_mode": "Markdown"
            }, timeout=10)
            print("✅ Operational summary report successfully transmitted to Telegram Alerts.")
        except Exception as tg_err:
            print(f"❌ Failed to deliver message to Telegram endpoint: {tg_err}")

    # --- GMAIL/SMTP ROUTING DISPATCH ---
    # Can hook straight into your current mailer modules or hit a simple trigger address loop
    return message

if __name__ == "__main__":
    compile_and_send_ops_summary()

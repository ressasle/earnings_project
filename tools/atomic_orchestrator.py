import os
import subprocess
import sys
import time
import glob
import shutil
from datetime import datetime
from dotenv import load_dotenv

# Ensure container runtime roots match up perfectly
base_workspace = "/root" if os.path.exists("/root") else os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if base_workspace not in sys.path:
    sys.path.append(base_workspace)

from supabase import Client
from utils.supabase_client import get_supabase_client

load_dotenv()

supabase = get_supabase_client()
SUPABASE_URL = os.environ.get("SUPABASE_URL")

def push_to_master_index(
    ticker_eod: str,
    company_name: str,
    pdf_url: str,
    audio_url: str,
    fiscal_period: str,
    supabase_client: Client,
    pdf_url_de: str = None,
    audio_url_de: str = None
) -> bool:
    """Push quarterly earnings metadata directly to public.kasona_company_reports."""
    print(f"   [INDEX] Pushing master ledger rows for {ticker_eod}...")
    
    quarterly_pdf_en = [{"type": "earnings_pdf", "label": f"Earnings Report {fiscal_period}", "url": pdf_url}]
    quarterly_audio_en = [{"type": "earnings_audio", "label": f"Earnings Audio {fiscal_period}", "url": audio_url}]

    quarterly_pdf_de = []
    if pdf_url_de:
        quarterly_pdf_de.append({"type": "earnings_pdf", "label": f"Earnings Report {fiscal_period} (DE)", "url": pdf_url_de})

    quarterly_audio_de = []
    if audio_url_de:
        quarterly_audio_de.append({"type": "earnings_audio", "label": f"Earnings Audio {fiscal_period} (DE)", "url": audio_url_de})

    payload = {
        "ticker_eod": ticker_eod,
        "company_name": company_name,
        "report_date": datetime.now().isoformat(),
        "skill_id": "quarterly_earnings",
        "report_type": "Quarterly Earnings Analysis",
        "trigger_reason": "Batch Orchestration",
        "presentation_pdf_en": [],
        "presentation_pdf_de": [],
        "presentation_audio_en": [],
        "presentation_audio_de": [],
        "quarterly_analysis_pdf_en": quarterly_pdf_en,
        "quarterly_analysis_pdf_de": quarterly_pdf_de,
        "quarterly_analysis_audio_en": quarterly_audio_en,
        "quarterly_analysis_audio_de": quarterly_audio_de,
        "created_by": "n8n-automation",
        "review_status": "published",
        "updated_at": datetime.now().isoformat()
    }

    try:
        res = supabase_client.table("kasona_company_reports").upsert(
            payload,
            on_conflict="ticker_eod,skill_id"
        ).execute()
        return len(res.data) > 0
    except Exception as exc:
        print(f"   [!] Master Index ledger write error: {exc}")
        return False

def upload_file_natively(local_path: str, bucket: str, storage_path: str, content_type: str) -> bool:
    """Streams binaries directly to Supabase Storage with explicit error handling."""
    if not os.path.exists(local_path):
        print(f"   ❌ [UPLOAD ERROR] Local file target missing: {local_path}")
        return False
    try:
        print(f"   [+] Streaming {os.path.basename(local_path)} to bucket '{bucket}'...")
        with open(local_path, "rb") as f:
            supabase.storage.from_(bucket).upload(
                path=storage_path,
                file=f,
                file_options={"content-type": content_type, "x-upsert": "true"}
            )
        print(f"   ✅ [UPLOAD SUCCESS] Synced path: {storage_path}")
        return True
    except Exception as e:
        print(f"   ❌ [UPLOAD FAILED] Storage exception for {storage_path}: {e}")
        return False

def run_orchestrator(target_ticker=None, target_id=None):
    print(f"[*] Atomic Orchestrator: Starting verification cycle...")
    
    output_dir = "/root/output" if os.path.exists("/root") else os.path.join(os.getcwd(), "output")
    tools_dir = "/root/tools" if os.path.exists("/root") else os.path.join(os.getcwd(), "tools")
    os.makedirs(output_dir, exist_ok=True)

    # Resolve target matching queries
    if target_id:
        query = supabase.table("quarterly_earnings").select("*").eq("id", target_id)
    else:
        query = supabase.table("quarterly_earnings").select("*").eq("review_status", "approved").eq("fiscal_period", "Q1 2026")
        if target_ticker:
            query = query.eq("ticker_eod", target_ticker)
            
    res = query.execute()
    records = res.data
    
    if not records:
        print("[!] No approved records found matching search matrices.")
        return {"pdf_uploaded": False, "mp3_uploaded": False}

    status_tracker = {"pdf_uploaded": False, "mp3_uploaded": False}
    
    for record in records:
        ticker = record["ticker_eod"]
        fp = record.get("fiscal_period") or "Q1 2026"
        company = record.get("company_name") or ticker
        quarter = record.get("quarter") or "Q1"
        year = record.get("fiscal_year") or 2026
        
        print(f"\n[>>>] Processing Asset Array: {ticker} - {fp}")
        
        markdown_text = record.get("markdown_content") or ""
        if not markdown_text:
            print(f"   [!] Skipping {ticker}: Markdown text field is empty.")
            continue

        md_file = os.path.join(output_dir, f"{ticker}_{fp.replace(' ', '_')}.md")
        with open(md_file, "w", encoding="utf-8") as f:
            f.write(markdown_text)
            
        pdf_name = f"{ticker}_{fp.replace(' ', '_')}.pdf"
        html_name = f"{ticker}_{fp.replace(' ', '_')}.html"
        mp3_name = f"{ticker}_{fp.replace(' ', '_')}.mp3"

        # Explicit absolute path definitions for sub-scripts
        script_html = os.path.join(tools_dir, "generate_earnings_html.py")
        script_pdf = os.path.join(tools_dir, "generate_earnings_pdf.py")
        script_audio = os.path.join(tools_dir, "generate_audio.py")

        # 1. Generate HTML & PDF Core Binaries
        print(f"   [+] Compiling HTML template matrices...")
        subprocess.run(["python", script_html, md_file], check=False)
        print(f"   [+] Execiling primary layout PDF engine...")
        subprocess.run(["python", script_pdf, md_file, "--ticker", ticker], check=False)
        
        # 2. Build Structural Branding Public Storage Target Mapping Links
        pdf_target_path = f"{ticker}/{quarter}_{year}_{pdf_name}"
        audio_target_path = f"{ticker}/{quarter}_{year}_{mp3_name}"
        html_target_path = f"{ticker}/{quarter}_{year}_{html_name}"

        pdf_url = f"{SUPABASE_URL}/storage/v1/object/public/earnings-reports-pdf/{pdf_target_path}"
        audio_url = f"{SUPABASE_URL}/storage/v1/object/public/earnings-reports-audio/{audio_target_path}"

        # 3. Generate Neural Audio Stream
        print(f"   [+] Compiling speech metrics...")
        sys.stdout.flush()

        bm_ticker_stored = record.get("benchmark_ticker", "")
        benchmark_label = "Nasdaq-100" if str(bm_ticker_stored).upper() == "QQQ" else "S&P 500"

        cmd_args = [
            "python", script_audio,
            "--script", str(md_file), "--company", str(company), "--ticker-eod", str(ticker),
            "--pdf-url", str(pdf_url), "--audio-url", str(audio_url), "--fiscal-period", str(fp),
            "--impact-score", str(record.get("impact_score", "N/A")),
            "--output", os.path.join(output_dir, mp3_name),
        ]

        move_7d = record.get("price_movement_7d_prior")
        move_post = record.get("price_movement_post_earnings")
        bm_move = record.get("benchmark_move_post")
        rel_perf = record.get("relative_performance")

        if move_7d is not None: cmd_args += ["--move-7d", str(move_7d)]
        if move_post is not None: cmd_args += ["--move-post", str(move_post)]
        if bm_ticker_stored: cmd_args += ["--benchmark-label", benchmark_label]
        if bm_move is not None: cmd_args += ["--benchmark-move", str(bm_move)]
        if rel_perf is not None: cmd_args += ["--relative-perf", str(rel_perf)]

        subprocess.run(cmd_args, check=False)
        
        # 4. NATIVE STORAGE TRANSMISSION PHASE (No shell subprocess dependency)
        pdf_success = upload_file_natively(os.path.join(output_dir, pdf_name), "earnings-reports-pdf", pdf_target_path, "application/pdf")
        mp3_success = upload_file_natively(os.path.join(output_dir, mp3_name), "earnings-reports-audio", audio_target_path, "audio/mpeg")
        html_success = upload_file_natively(os.path.join(output_dir, html_name), "earnings-reports-html", html_target_path, "text/html")

        if pdf_success: status_tracker["pdf_uploaded"] = True
        if mp3_success: status_tracker["mp3_uploaded"] = True

        # 5. Push Metadata Index Updates
        if pdf_success and mp3_success:
            push_to_master_index(ticker, company, pdf_url, audio_url, fp, supabase, pdf_url_de=None, audio_url_de=None)
            
        print(f"[OK] End-to-end rendering pipeline completed for {ticker}")

    return status_tracker

if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--ticker", help="Specific ticker to process")
    args = parser.parse_args()
    run_orchestrator(target_ticker=args.ticker)

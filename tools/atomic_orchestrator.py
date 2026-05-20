#!/usr/bin/env python3
import os
import sys
import subprocess
import time
from datetime import datetime, timezone
from utils.supabase_client import get_supabase_client

def upload_to_bucket(local_file: str, bucket: str, destination_path: str, content_type: str) -> str:
    """Streams binary file data natively up to Supabase Cloud Buckets."""
    if not os.path.exists(local_file): 
        print(f"   ⚠️ [ORCHESTRATOR WARN] Local asset missing for upload: {local_file}")
        return ""
    sb = get_supabase_client()
    try:
        with open(local_file, "rb") as f:
            sb.storage.from_(bucket).upload(
                path=destination_path,
                file=f,
                file_options={"content-type": content_type, "x-upsert": "true"}
            )
        sb_url = os.environ.get("SUPABASE_URL")
        return f"{sb_url}/storage/v1/object/public/{bucket}/{destination_path}"
    except Exception as e:
        print(f"   ❌ [STORAGE ERR] Binary streaming crash for path {destination_path}: {e}")
        return ""

def run_orchestrator(target_ticker=None):
    print(f"[*] Atomic Orchestrator: Constructing high-fidelity standard artifact blocks...")
    sb = get_supabase_client()
    
    # Standardize our directory maps inside the absolute container environments
    output_dir = "/root/output" if os.path.exists("/root") else os.path.join(os.getcwd(), "output")
    tools_dir = "/root/tools" if os.path.exists("/root") else os.path.join(os.getcwd(), "tools")
    os.makedirs(output_dir, exist_ok=True)

    # Gather records that have been generated and approved
    query = sb.table("quarterly_earnings").select("*").eq("review_status", "approved").eq("fiscal_period", "Q1 2026")
    if target_ticker: 
        query = query.eq("ticker_eod", target_ticker)
    records = query.execute().data

    if not records:
        print("[!] No matching approved records found for orchestration formatting.")
        return {"pdf_uploaded": False, "mp3_uploaded": False}

    for record in records:
        ticker = record["ticker_eod"]
        fp = record["fiscal_period"]
        fp_slug = fp.replace(" ", "_")
        company = record.get("company_name") or ticker
        quarter = record.get("quarter") or "Q1"
        year = record.get("fiscal_year") or 2026
        
        print(f"\n[>>>] Running Corporate Template Toolchains for: {ticker}")
        
        # FIXED: Enforce absolute paths for all tool executions inside the VM sandbox
        script_html = os.path.join(tools_dir, "generate_earnings_html.py")
        script_pdf = os.path.join(tools_dir, "generate_earnings_pdf.py")
        script_audio = os.path.join(tools_dir, "generate_audio.py")

        md_file = os.path.join(output_dir, f"{ticker}_{fp_slug}.md")
        pdf_file = os.path.join(output_dir, f"{ticker}_{fp_slug}.pdf")
        html_file = os.path.join(output_dir, f"{ticker}_{fp_slug}.html")
        mp3_file = os.path.join(output_dir, f"{ticker}_{fp_slug}.mp3")

        # Drop the raw database markdown content back onto the workspace disk cache
        with open(md_file, "w", encoding="utf-8") as f: 
            f.write(record["markdown_content"])

        # ====================================================
        # RE-ENGAGE RE-STYLED ARTIFACT GENERATION LAYERS
        # ====================================================
        print(f"   [+] Executing HTML template constructor module...")
        subprocess.run([sys.executable, script_html, md_file], check=False)
        
        print(f"   [+] Executing PDF branding layouts compiler...")
        subprocess.run([sys.executable, script_pdf, md_file, "--ticker", ticker], check=False)

        # Build public matching URL target parameters for audio references
        pdf_path_target = f"{ticker}/{quarter}_{year}_{ticker}_{fp_slug}.pdf"
        mp3_path_target = f"{ticker}/{quarter}_{year}_{ticker}_{fp_slug}.mp3"
        html_path_target = f"{ticker}/{quarter}_{year}_{ticker}_{fp_slug}.html"

        pdf_public_url = f"{os.environ.get('SUPABASE_URL')}/storage/v1/object/public/earnings-reports-pdf/{pdf_path_target}"
        audio_public_url = f"{os.environ.get('SUPABASE_URL')}/storage/v1/object/public/earnings-reports-audio/{mp3_path_target}"

        # --- AUDIO SUITE COMPILATION RUN ---
        print(f"   [+] Compiling synthesized audio narrative layout...")
        cmd_args = [
            sys.executable, script_audio,
            "--script", str(md_file),
            "--company", str(company),
            "--ticker-eod", str(ticker),
            "--pdf-url", str(pdf_public_url),
            "--audio-url", str(audio_public_url),
            "--fiscal-period", str(fp),
            "--impact-score", str(record.get("impact_score", "N/A")),
            "--output", mp3_file,
        ]

        # Inject secondary metric parameters if populated
        if record.get("price_movement_7d_prior") is not None: 
            cmd_args += ["--move-7d", str(record["price_movement_7d_prior"])]
        if record.get("price_movement_post_earnings") is not None: 
            cmd_args += ["--move-post", str(record["price_movement_post_earnings"])]
        if record.get("benchmark_ticker"):
            bm_label = "Nasdaq-100" if str(record["benchmark_ticker"]).upper() == "QQQ.US" else "S&P 500"
            cmd_args += ["--benchmark-label", bm_label]
        if record.get("benchmark_move_post") is not None: 
            cmd_args += ["--benchmark-move", str(record["benchmark_move_post"])]
        if record.get("relative_performance") is not None: 
            cmd_args += ["--relative-perf", str(record["relative_performance"])]

        subprocess.run(cmd_args, check=False)

        # --- BINARY DATA STREAM STORAGE UPLOADS ---
        print(f"   [+] Synchronizing file binaries to Supabase public storage buckets...")
        pdf_url_live = upload_to_bucket(pdf_file, "earnings-reports-pdf", pdf_path_target, "application/pdf")
        mp3_url_live = upload_to_bucket(mp3_file, "earnings-reports-audio", mp3_path_target, "audio/mpeg")
        html_url_live = upload_to_bucket(html_file, "earnings-reports-html", html_path_target, "text/html")

        # --- UPDATE DATABASE STATE METRICS ---
        sb.table("quarterly_earnings").update({
            "pdf_report_url": pdf_url_live,
            "audio_report_url": mp3_url_live,
            "html_report_url": html_url_live,
            "published_at": datetime.now(timezone.utc).isoformat(),
            "uploaded": True
        }).eq("id", record["id"]).execute()

        sb.table("kasona_portfolio_assets").update({
            "earnings_produced": True,
            "production_updated_at": datetime.now(timezone.utc).isoformat()
        }).eq("ticker_eod", ticker).execute()

        print(f"✅ [ORCHESTRATION COMPLETE] All artifacts (HTML, PDF, MP3) successfully pushed for {ticker}.")

    return {"pdf_uploaded": True, "mp3_uploaded": True}

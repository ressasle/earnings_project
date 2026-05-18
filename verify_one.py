import modal
import os
import sys
import shutil
import asyncio
from datetime import datetime

image = (
    modal.Image.debian_slim()
    .pip_install(
        "supabase", "requests", "fpdf2", "edge-tts", 
        "Pillow", "aiohttp", "python-dotenv", "jinja2", 
        "fastapi[standard]", "google-generativeai", "pandas"
    )
    .add_local_dir(".", remote_path="/root/app") 
)

app = modal.App("kasona-universal-sync")

@app.cls(image=image, secrets=[modal.Secret.from_name("kasona-secrets")], timeout=3600)
class VerificationRunner:
    @modal.enter()
    def setup(self):
        if "/root/app" not in sys.path:
            sys.path.append("/root/app")
        
        # Consolas Ghost Drive Setup
        fake_fonts = "/root/app/C:/Windows/Fonts"
        os.makedirs(fake_fonts, exist_ok=True)
        for f in ["consola.ttf", "consolab.ttf", "consolai.ttf", "consolaz.ttf"]:
            src = f"/root/app/tools/{f}"
            if os.path.exists(src): shutil.copy2(src, os.path.join(fake_fonts, f))

        os.chdir("/root/app")
        print("✅ Environment Ready.")

    @modal.method()
    async def run_analysis(self, ticker: str):
        # Configuration matches your orchestrator logic
        period = "Q1 2026"
        quarter = "Q1"
        year = 2026
        
        print(f"🚀 [START] Processing {ticker}...")

        try:
            # --- STAGE 0-1: SYNC ---
            from tools.enrich_earnings_dates import enrich_all
            from tools.sync_earnings_data import sync_ticker
            await enrich_all(ticker_filter=ticker, verbose=True)
            sync_ticker(ticker, period)

            # --- STAGE 2: CAPTURE PRIMARY KEY ---
            from utils.supabase_client import get_supabase_client
            sb = get_supabase_client()
            SUPABASE_URL = os.environ.get("SUPABASE_URL")
            
            res = sb.table("quarterly_earnings").select("*").eq("ticker_eod", ticker).execute()
            if not res.data:
                raise Exception(f"No row found for {ticker} after sync.")
            
            # Identify the specific row we are working on
            row = sorted(res.data, key=lambda x: x.get('created_at', ''), reverse=True)[0]
            row_id = row["id"]
            print(f"✅ Target Row ID: {row_id}")

            # --- STAGE 3: AI NARRATIVE ---
            from tools.Giga_Expansion_1515 import process_ticker
            process_ticker(ticker, period)
            
            # Force approve to allow orchestrator to run
            sb.table("quarterly_earnings").update({"review_status": "approved"}).eq("id", row_id).execute()

            # --- STAGE 4: ARTIFACT GENERATION ---
            from tools.atomic_orchestrator import run_orchestrator
            print("📦 Stage 4: Generating Artifacts...")
            run_orchestrator(target_ticker=ticker)

            # --- STAGE 5: THE UNIVERSAL DB UPDATE (The Fix) ---
            # Construct the exact public URLs based on your orchestrator's naming convention
            fp_safe = period.replace(' ', '_')
            pdf_url = f"{SUPABASE_URL}/storage/v1/object/public/earnings-reports-pdf/{ticker}/{quarter}_{year}_{ticker}_{fp_safe}.pdf"
            audio_url = f"{SUPABASE_URL}/storage/v1/object/public/earnings-reports-audio/{ticker}/{quarter}_{year}_{ticker}_{fp_safe}.mp3"
            html_url = f"{SUPABASE_URL}/storage/v1/object/public/earnings-reports-html/{ticker}/{quarter}_{year}_{ticker}_{fp_safe}.html"

            print(f"🔗 Linking artifacts to Row ID: {row_id}...")
            sb.table("quarterly_earnings").update({
                "pdf_report_url": pdf_url,
                "audio_report_url": audio_url,
                "html_report_url": html_url,
                "updated_at": datetime.now().isoformat()
            }).eq("id", row_id).execute()

            print(f"🏁 [SUCCESS] {ticker} fully processed and table updated.")
            return {"status": "SUCCESS", "ticker": ticker, "row_id": row_id}

        except Exception as e:
            print(f"❌ [CRASH]: {str(e)}")
            return {"status": "FAILED", "error": str(e)}

@app.local_entrypoint()
def main(ticker: str = "UBER.US"):
    runner = VerificationRunner()
    result = runner.run_analysis.remote(ticker)
    print(f"\nFinal Result: {result}")

import modal
import os
import sys
import shutil
import asyncio
import requests
import traceback
from fastapi import FastAPI

web_app = FastAPI()
IMAGE_BUILD_SIGNATURE = "v1.2.6_portfolio_scouter_integration"

image = (
    modal.Image.debian_slim()
    .pip_install(
        "supabase", "requests", "fpdf2", "edge-tts", 
        "Pillow", "aiohttp", "python-dotenv", "jinja2", 
        "google-generativeai", "pandas", "fastapi"
    )
    .run_commands(f"echo 'Building deployment signature: {IMAGE_BUILD_SIGNATURE}'")
    .add_local_dir(".", remote_path="/root") 
)

app = modal.App("kasona-production-engine")

@app.cls(image=image, secrets=[modal.Secret.from_name("kasona-secrets")], timeout=3600)
class EarningsProcessor:
    @modal.enter()
    def setup(self):
        os.chdir("/root")
        if "/root" not in sys.path:
            sys.path.append("/root")
        fake_fonts = "/root/C:/Windows/Fonts"
        os.makedirs(fake_fonts, exist_ok=True)
        for f in ["consola.ttf", "consolab.ttf", "consolai.ttf", "consolaz.ttf"]:
            src = f"/root/tools/{f}"
            if os.path.exists(src):
                shutil.copy2(src, os.path.join(fake_fonts, f))

    @modal.method()
    def process_ticker_batch(self, ticker: str):
        period = "Q1 2026"
        try:
            from tools.sync_earnings_data import sync_ticker
            from tools.Giga_Expansion_1515 import process_ticker
            from tools.atomic_orchestrator import run_orchestrator
            from utils.supabase_client import get_supabase_client
            
            print(f"\n{'='*70}\n🔄 RUNNING BATCH WORKER NODE FOR: {ticker}\n{'='*70}")
            sb = get_supabase_client()
            
            # Step 1: EODHD Synchronization
            print(f"📡 [DEBUG] Executing sync_ticker variables for {ticker}...")
            try:
                sync_ticker(ticker, period)
            except Exception as sync_err:
                print(f"⚠️ Sync Trace Notice: {sync_err}")
                
            # Step 2: Database Handshake Pointers
            res = sb.table("quarterly_earnings").select("id").eq("ticker_eod", ticker).eq("fiscal_period", period).execute()
            if not res.data:
                insert_res = sb.table("quarterly_earnings").insert({
                    "ticker_eod": ticker, "fiscal_period": period, "review_status": "pending"
                }).execute()
                row_id = insert_res.data[0]['id']
            else:
                row_id = sorted(res.data, key=lambda x: x.get('created_at', ''), reverse=True)[0]['id']
            
            # Step 3: Text Content Generation Block
            print(f"🤖 [DEBUG] Triggering Giga Expansion narrative compiler for {ticker}...")
            process_ticker(ticker, period)
            
            # Step 4: Run Original Subprocess Artifact Engine
            print(f"📦 [DEBUG] Invoking atomic script orchestrator pipelines...")
            os.environ["PYTHONPATH"] = "/root"
            upload_status = run_orchestrator(target_ticker=ticker)
            
            # Step 5: Final Promotion Flag
            sb.table("quarterly_earnings").update({"review_status": "approved"}).eq("id", row_id).execute()
            
            sb_url = os.environ.get("SUPABASE_URL")
            pdf_url = f"{sb_url}/storage/v1/object/public/earnings-reports-pdf/{ticker}/Q1_2026_{ticker}_Q1_2026.pdf"
            print(f"✅ [SUCCESS] Run complete for {ticker}. Artifact path: {pdf_url}")
            return {"ticker": ticker, "status": "Success", "url": pdf_url}
                
        except Exception as e:
            print(f"💥 WORKER EXCEPTION ENCOUNTERED ON {ticker} 💥")
            traceback.print_exc()
            return {"ticker": ticker, "status": "Error", "message": str(e).split('\n')[0][:200]}

    @modal.method()
    async def scout_and_process(self, n8n_webhook: str, lookback: int = 14):
        print(f"\n{'='*70}\n🚀 KASONA VERIFIED PORTFOLIO INTEGRATION ENGINE ONLINE\n{'='*70}")
        
        try:
            requests.post(n8n_webhook, json={
                "status": "processing",
                "summary_text": f"🚀 *Kasona Production Engine Engaged*\nExecuting live history scans across active database assets..."
            }, timeout=10)
        except Exception as e:
            print(f"⚠️ Webhook communication check notice: {e}")

        try:
            # ----------------------------------------------------
            # STEP 1: IMPORT AND EXECUTE YOUR ASSET SCOUTER LAYER
            # ----------------------------------------------------
            from tools.enrich_earnings_dates import enrich_all
            
            print(f"🕵️ Scanning kasona_portfolio_assets for revisions in the last {lookback} days...")
            scout_payload = await enrich_all(verbose=True, days_lookback=lookback)
            tickers = scout_payload.get("updated_tickers", [])
            
            if not tickers:
                print("📭 Portfolio tracking registers 0 newly reported tickers inside this window.")
                requests.post(n8n_webhook, json={
                    "status": "complete", "count": 0,
                    "summary_text": f"📋 *Kasona Run Report*\n\n📭 Portfolios scan complete. No new earnings reports detected inside the last {lookback} days."
                })
                return

            print(f"🎯 Discoveries confirmed! Found {len(tickers)} assets matching search filters: {tickers}")
            print(f"🚜 Initializing cluster execution arrays across parallel nodes...\n")
            
            # ----------------------------------------------------
            # STEP 2: MAP PARALLEL WORKERS ONLY FOR DETECTED TICKERS
            # ----------------------------------------------------
            results = [res async for res in self.process_ticker_batch.map.aio(tickers)]
            
            report_lines = []
            success_count = 0
            for r in results:
                if r["status"] == "Success":
                    success_count += 1
                    report_lines.append(f"✅ *{r['ticker']}*: {r['url']}")
                else:
                    report_lines.append(f"❌ *{r['ticker']}*: Processing Interrupted ({r.get('message')})")
                    
            summary_text = f"📋 *Kasona Executive Stable Run Report*\n\nTarget Scouter Output: {success_count} Passed / {len(results) - success_count} Blocked\n\n" + "\n".join(report_lines)
            
            requests.post(n8n_webhook, json={
                "status": "complete",
                "count": success_count,
                "summary_text": summary_text
            }, timeout=15)
            print("🏁 Final summary metrics passed back safely to your webhook panel.")
            
        except Exception as e:
            print(f"💥 CRITICAL PIPELINE LOOP FAILURE 💥")
            traceback.print_exc()
            requests.post(n8n_webhook, json={"status": "error", "summary_text": f"❌ Core System Crash:\n\n{str(e)[:500]}"}, timeout=10)

@app.function(image=image, secrets=[modal.Secret.from_name("kasona-secrets")])
@modal.asgi_app()
def api():
    return web_app

@web_app.post("/harvest")
async def trigger_harvest(n8n_callback: str, lookback: int = 14):
    await EarningsProcessor().scout_and_process.spawn.aio(n8n_webhook=n8n_callback, lookback=lookback)
    return {"status": "accepted"}

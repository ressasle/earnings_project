import modal
import os
import sys
import shutil
import requests
import traceback
from fastapi import FastAPI

web_app = FastAPI()
IMAGE_BUILD_SIGNATURE = "v1.3.3_pacing_and_unrestricted_cluster_engine"

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

@app.cls(image=image, secrets=[modal.Secret.from_name("kasona-secrets")], timeout=7200)
class EarningsProcessor:
    @modal.enter()
    def setup(self):
        os.chdir("/root")
        if "/root" not in sys.path: 
            sys.path.append("/root")
            
        # Guarantee system-wide cluster typography paths for FPDF matching
        print("[*] Mounting cluster typography mappings inside runtime sandbox...")
        fake_fonts = "/root/C:/Windows/Fonts"
        os.makedirs(fake_fonts, exist_ok=True)
        
        for f in ["consola.ttf", "consolab.ttf", "consolai.ttf", "consolaz.ttf"]:
            src = f"/root/tools/{f}"
            if os.path.exists(src):
                shutil.copy2(src, os.path.join(fake_fonts, f))
                print(f"   ↳ [LOADED] Typography asset mapped: {f}")
            else:
                with open(os.path.join(fake_fonts, f), "wb") as empty_f:
                    empty_f.write(b"")

    @modal.method()
    def process_ticker_batch(self, ticker: str):
        period = "Q1 2026"
        try:
            from tools.sync_earnings_data import sync_ticker
            from tools.Giga_Expansion_1515 import process_ticker
            from tools.qa_verifier import run_independent_qa
            from tools.atomic_orchestrator import run_orchestrator
            from utils.supabase_client import get_supabase_client
            
            sb = get_supabase_client()
            print(f"\n{'='*70}\n⚡ RUNNING CORE WORKER CONTAINER TARGET: {ticker}\n{'='*70}")
            
            # STAGE 1: RAW INGESTION & DATA SOURCE MANIFEST LINEAGE LOGGING
            print(f"📡 [STAGE 1/4] Pulling EODHD fundamentals data arrays...")
            sync_ticker(ticker, period)
            
            # Resolve target tracking row references
            res = sb.table("quarterly_earnings").select("id").eq("ticker_eod", ticker).eq("fiscal_period", period).execute()
            if not res.data:
                raise Exception(f"Relational row tracking initialization failure for key: {ticker}")
            row_id = sorted(res.data, key=lambda x: x.get('created_at', ''), reverse=True)[0]['id']

            # STAGE 2: NARRATIVE ARTIFACT GENERATION (GEMINI 3 FLASH)
            print(f"\n🤖 [STAGE 2/4] Triggering content generation loops via Gemini 3...")
            process_ticker(ticker, period)
            
            # STAGE 3: DATA INTEGRITY CHECKS & AUDIT PATH LOGGING
            print(f"\n🕵️ [STAGE 3/4] Running schema-aligned QA validation checks...")
            run_independent_qa(ticker=ticker, target_id=row_id)

            # STAGE 4: ATOMIC ORCHESTRATOR PDF FORMATTING LABELS
            print(f"\n📦 [STAGE 4/4] Executing asset formatting and file uploads...")
            os.environ["PYTHONPATH"] = "/root"
            run_orchestrator(target_ticker=ticker)
            
            # Generate the live public access link tracker
            sb_url = os.environ.get("SUPABASE_URL")
            pdf_url = f"{sb_url}/storage/v1/object/public/earnings-reports-pdf/{ticker}/Q1_2026_{ticker}_Q1_2026.pdf"
            
            print(f"\n🚀 [RUN COMPLETE] All tables filled & assets compiled for {ticker}.\n📄 Public PDF Link: {pdf_url}\n")
            return {"ticker": ticker, "status": "Success", "url": pdf_url}
            
        except Exception as e:
            print(f"💥 PIPELINE BREAK ON NODE {ticker} 💥")
            traceback.print_exc()
            return {"ticker": ticker, "status": "Error", "message": str(e).split('\n')[0][:200]}

    @modal.method()
    async def scout_and_process(self, n8n_webhook: str, lookback: int = 14, target_ticker=None):
        print(f"\n🚀 KASONA SCALED ZERO-EMPTY ENGINE INITIALIZED")
        
        # ----------------------------------------------------
        # HARD CRITERIA GATE: CHECK FOR SINGLE TICKER TARGET
        # ----------------------------------------------------
        if target_ticker and str(target_ticker).strip() != "" and str(target_ticker).upper() != "NONE":
            clean_ticker = str(target_ticker).strip().upper()
            tickers = [clean_ticker]
            print(f"🎯 SINGLE TARGET OVERRIDE ENFORCED. Bypassing Step 0 full portfolio scan. Target queue: {tickers}")
        else:
            print("🕵️ No manual target override detected. Initializing full portfolio database scan...")
            from tools.enrich_earnings_dates import enrich_all
            scout_payload = await enrich_all(verbose=True, days_lookback=lookback)
            tickers = scout_payload.get("updated_tickers", [])
        
        if not tickers:
            print("📭 Queue Empty. No tracking targets allocated for runtime execution.")
            try:
                requests.post(n8n_webhook, json={"status": "complete", "summary_text": "Scan finished. Queue Empty."}, timeout=10)
            except:
                pass
            return

        print(f"🚜 Handing off processing slots to isolated parallel container cluster nodes: {tickers}")
        results = [res async for res in self.process_ticker_batch.map.aio(tickers)]
        
        report_lines = []
        for r in results:
            if r["status"] == "Success":
                report_lines.append(f"✅ *{r['ticker']}*: {r['url']}")
            else:
                report_lines.append(f"❌ *{r['ticker']}*: Processing Interrupted ({r.get('message')})")
                
        summary_text = f"📋 *Kasona Production Run Summary*\n\n" + "\n".join(report_lines)
        try:
            requests.post(n8n_webhook, json={"status": "complete", "summary_text": summary_text}, timeout=15)
        except:
            pass
        print("🏁 High-fidelity scale run successfully processed.")

@app.function(image=image, secrets=[modal.Secret.from_name("kasona-secrets")])
@modal.asgi_app()
def api():
    return web_app
@web_app.post("/harvest")
async def trigger_harvest(n8n_callback: str, lookback: int = 1, ticker: str = None):
    """
    ASGI Webhook Entrypoint: Forces variable normalization to ensure manual triggers 
    bypass multi-ticker portfolio queues instantly.
    """
    try:
        processor = EarningsProcessor()
        clean_ticker_str = str(ticker).strip() if ticker else None
        print(f"📡 [WEBHOOK INCOMING] Processing target_ticker parameter: '{clean_ticker_str}'")
        
        # FIXED: Use await ...spawn.aio() to resolve async contextual warning
        await processor.scout_and_process.spawn.aio(
            n8n_webhook=n8n_callback, 
            lookback=int(lookback), 
            target_ticker=clean_ticker_str
        )
        
        return {
            "status": "accepted", 
            "message": f"Single ticker execution safely backgrounded on cluster nodes.",
            "target_ticker": clean_ticker_str
        }
        
    except Exception as api_err:
        print(f"❌ [WEBHOOK FAILURE] Failed to background task layout thread: {api_err}")
        return {"status": "error", "message": str(api_err)}

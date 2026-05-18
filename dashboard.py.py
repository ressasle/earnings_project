import streamlit as st
import requests
import pandas as pd

# --- ACTUAL MODAL ENDPOINTS ---
URLS = {
    "enrich": "https://ressasle--kasona-modular-pipeline-kasonaprocessor-enrich-dates.modal.run",
    "sync": "https://ressasle--kasona-modular-pipeline-kasonaprocessor-sync-data.modal.run",
    "expand": "https://ressasle--kasona-modular-pipeline-kasonaprocessor-expand-c3a067.modal.run",
    "artifacts": "https://ressasle--kasona-modular-pipeline-kasonaprocessor-genera-1bc458.modal.run"
}

st.set_page_config(page_title="Kasona Intelligence Hub", layout="wide", page_icon="📈")

# Custom CSS for a professional look
st.markdown("""
    <style>
    .main { background-color: #f8f9fa; }
    .stButton>button { width: 100%; border-radius: 5px; height: 3em; background-color: #007bff; color: white; }
    .stStatusWidget { border-radius: 10px; }
    </style>
    """, unsafe_allow_html=True)

st.title("📈 Kasona Wealth Intelligence Hub")
st.caption("Orchestrating Giga-Expansion Pipelines & Artifact Generation")

# --- GLOBAL SETTINGS ---
with st.sidebar:
    st.header("Settings")
    period = st.selectbox("Fiscal Period", ["Q1 2026", "Q4 2025"], index=0)
    st.divider()
    st.info("Bakes SKILL.md rules into every stage.")

# Initialize session state for tickers
if "tickers" not in st.session_state:
    st.session_state.tickers = []

# --- STAGE 0: ENRICHMENT ---
st.subheader("Step 1: Check for Updates")
if st.button("🔍 Scan Portfolios for New Earnings Dates"):
    with st.spinner("Calling Stage 0 (Modal)..."):
        # We send an empty ticker or a portfolio ID to trigger the global scan
        resp = requests.post(URLS["enrich"], json={"period": period})
        if resp.status_code == 200:
            data = resp.json()
            # Assuming your tool returns a list of tickers that were 'updated'
            st.session_state.tickers = data.get("stats", {}).get("updated_tickers", [])
            if not st.session_state.tickers:
                st.warning("No new dates found. Your database is up to date.")
            else:
                st.success(f"Found {len(st.session_state.tickers)} tickers requiring action.")
        else:
            st.error(f"Stage 0 Failed: {resp.text}")

# --- PIPELINE EXECUTION ---
if st.session_state.tickers:
    st.divider()
    st.subheader("Step 2: Execute Ticker Pipeline")
    
    for ticker in st.session_state.tickers:
        with st.expander(f"Pipeline for {ticker}", expanded=False):
            col1, col2, col3, col4 = st.columns(4)
            
            # --- SYNC ---
            if col1.button(f"1. Sync Data", key=f"sync_{ticker}"):
                with st.spinner("Syncing..."):
                    r = requests.post(URLS["sync"], json={"ticker": ticker, "period": period})
                    st.toast(f"{ticker} Synced!") if r.status_code == 200 else st.error("Fail")
            
            # --- EXPAND ---
            if col2.button(f"2. Giga AI", key=f"giga_{ticker}"):
                with st.spinner("Expanding..."):
                    r = requests.post(URLS["expand"], json={"ticker": ticker, "period": period})
                    st.toast(f"{ticker} Analysis Generated!") if r.status_code == 200 else st.error("Fail")

            # --- ARTIFACTS ---
            if col3.button(f"3. Generate Artifacts", key=f"art_{ticker}"):
                with st.spinner("Creating PDF/Audio..."):
                    r = requests.post(URLS["artifacts"], json={"ticker": ticker, "period": period})
                    if r.status_code == 200:
                        st.success("Artifacts Uploaded!")
                        st.json(r.json().get("files", []))
                    else:
                        st.error("Fail")

            # --- FULL AUTO ---
            if col4.button(f"🚀 FULL RUN", key=f"full_{ticker}"):
                progress_text = st.empty()
                bar = st.progress(0)
                
                # Step 1
                progress_text.text("Syncing Fundamentals...")
                requests.post(URLS["sync"], json={"ticker": ticker, "period": period})
                bar.progress(33)
                
                # Step 2
                progress_text.text("Running Giga-Expansion AI...")
                requests.post(URLS["expand"], json={"ticker": ticker, "period": period})
                bar.progress(66)
                
                # Step 3
                progress_text.text("Finalizing Artifacts & Storage...")
                requests.post(URLS["artifacts"], json={"ticker": ticker, "period": period})
                bar.progress(100)
                
                st.balloons()
                st.success(f"{ticker} Pipeline Finished.")

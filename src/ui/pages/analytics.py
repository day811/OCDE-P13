# src/ui/pages/analytics.py
"""
Analytics page - Token tracking and statistics
"""

import streamlit as st
import pandas as pd
import json
import logging
from pathlib import Path
from src.config import Config
from src.utils.token_accounting import get_accounting

logger = logging.getLogger(__name__)


def render():
    st.title("Analytique")
    st.markdown("Suivi de la consommation de tokens et statistiques système")
    st.markdown("---")

    st.markdown("**Session Actuelle**")
    try:
        session_id = st.session_state.get("session_id")
        accounting = get_accounting(session_id=session_id)
        report = accounting.get_session_report()

        col1, col2, col3, col4 = st.columns(4)
        with col1:
            st.metric("Tokens Totaux", report["total_tokens"])
        with col2:
            st.metric("Tokens Query (Embedding)", sum(l.get("query_tokens", 0) for l in accounting.load_session_logs()))
        with col3:
            st.metric("Tokens Context (Prompt)", sum(l.get("context_tokens", 0) for l in accounting.load_session_logs()))
        with col4:
            st.metric("Tokens LLM (Réponse)", sum(l.get("llm_tokens", 0) for l in accounting.load_session_logs()))

        # Détails session
        with st.expander("Détails Session", expanded=False):
            st.json({
                "Session ID": report.get("session_id"),
                "Opérations": len(accounting.load_session_logs()),
                "Fichier": accounting.sessionlogfile.name,
                "Tokens par type": {
                    "Query": sum(l.get("query_tokens", 0) for l in accounting.load_session_logs()),
                    "Context": sum(l.get("context_tokens", 0) for l in accounting.load_session_logs()),
                    "LLM": sum(l.get("llm_tokens", 0) for l in accounting.load_session_logs())
                }
            })

    except Exception as e:
        st.warning(f"Impossible de charger les statistiques: {e}")
        logger.error(f"Analytics error: {e}", exc_info=True)

    st.markdown("---")
    st.markdown("**Informations Système**")
    col1, col2 = st.columns(2)
    with col1:
        st.markdown("**Configuration**")
        st.write(f"- LLM Provider: {Config.LLM_PROVIDER}")
        st.write(f"- Région: {Config.REGION}")
        st.write(f"- Days Back: {Config.DAYS_BACK}")
    with col2:
        st.markdown("**État des données**")
        st.write(f"- Raw Data: {Config.RAW_DATA_DIR}")
        st.write(f"- Processed: {Config.PROCESSED_DATA_DIR}")
        st.write(f"- Indexes: {Config.INDEXES_DIR}")

# src/ui/pages/search.py
"""
Search page - Simple RAG search interface
"""

import streamlit as st
import logging
from src.core.seek_engine import SeekEngine
from src.ui.components import (
    render_question_input,
    render_advanced_filters,
    render_answer,
    render_sources,
    render_stats,
    render_error,
    render_no_index_error
)
from pathlib import Path
from src.config import Config

logger = logging.getLogger(__name__)


def render(snapshot_date: str = "", embedder :str=""):
    """Render search page."""
    
    st.title("🔍 Recherche Simple")
    st.markdown("Recherchez les événements culturels en Occitanie")
    st.markdown("---")
    
    if 'search_engine' not in st.session_state:
        st.session_state.search_engine = None
    if 'search_history' not in st.session_state:
        st.session_state.search_history = []
    
    if 'should_submit_message' not in st.session_state:
        st.session_state.should_submit_message = False

    snapshot_date = snapshot_date or Config.DEV_SNAPSHOT_DATE
    
    # Check if index exists
    index_path = Path(Config.get_index_path(embedder, snapshot_date))
    if not index_path.exists():
        render_no_index_error()
        return
    
    # Initialize SeekEngine
    if st.session_state.search_engine is None:
        try:
            st.session_state.search_engine = SeekEngine(
                embedder= embedder,
                snapshot_date=snapshot_date,
                mode='search'
            )
        except Exception as e:
            render_error(str(e))
            return
    
    # Input section
    st.markdown("### Votre question")
    
    col1, col2 = st.columns([4, 1])
    
    with col1:
        question = render_question_input(
            placeholder="Ex: Concerts ce weekend à Toulouse ?",
            key="search_question"
        )
    
    with col2:
        search_button = st.button(
            "🚀 Rechercher",
            use_container_width=True,
            key="search_button"
        )
    
    filters = render_advanced_filters()
    
    # Search execution
    if search_button :
        st.session_state.should_submit_message = True
    
    # ✅ TRAITER SEULEMENT SI LE BOUTON A ÉTÉ CLIQUÉ
    if st.session_state.should_submit_message:
        st.session_state.should_submit_message = False  # Reset le flag

        if not question.strip():
            st.warning("⚠️ Veuillez entrer une question.")
            return
        
        if question not in st.session_state.search_history:
            st.session_state.search_history.append(question)
        
        try:
            with st.spinner("⏳ Recherche en cours..."):
                result = st.session_state.search_engine.query(
                    question=question,
                    top_k=filters['top_k'],
                    temperature=filters['temperature'],
                    session_id=st.session_state.session_id
                )
            
            render_answer(result.get('answer', ''), is_chat=False)
            
            sources = result.get('sources', [])
            if sources:
                render_sources(sources)
            else:
                st.info("Aucune source trouvée pour cette question.")
            
            st.markdown("---")
            render_stats(result)
        
        except Exception as e:
            logger.error(f"Search error: {e}", exc_info=True)
            render_error(str(e))
    
    # History
    st.sidebar.markdown("### 📜 Historique")
    if st.session_state.search_history:
        for i, past_question in enumerate(reversed(st.session_state.search_history[-5:]), 1):
            if st.sidebar.button(
                f"{i}. {past_question[:40]}...",
                key=f"history_btn_{i}"
            ):
                st.rerun()
    else:
        st.sidebar.info("Aucune recherche récente")

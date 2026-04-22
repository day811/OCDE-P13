0# main.py - Streamlit Entry Point

import streamlit as st
import logging
from datetime import datetime
from pathlib import Path
from src.config import Config

# Configuration logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Configuration Streamlit
st.set_page_config(
    page_title="Puls-Events - Événements Culturels - RAG",
    page_icon="🎭",
    layout="wide",
    initial_sidebar_state="expanded"
)

# ============================================================================
# CUSTOM CSS
# ============================================================================
st.markdown("""
    <style>
    .metric-card {
        background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
        padding: 20px;
        border-radius: 10px;
        color: white;
        text-align: center;
    }
    
    .source-card {
        background-color: #f0f2f6;
        padding: 15px;
        border-left: 4px solid #667eea;
        margin: 10px 0;
        border-radius: 5px;
    }
    
    .answer-box {
        background-color: #e8f4f8;
        padding: 15px;
        border-radius: 8px;
        border-left: 4px solid #00b4d8;
        margin: 10px 0;
    }
    </style>
    """, unsafe_allow_html=True)

# ============================================================================
# SESSION STATE INITIALIZATION
# ============================================================================
if 'session_id' not in st.session_state:
    st.session_state.session_id = datetime.now().strftime("%Y%m%d_%H%M%S")
    st.session_state.search_history = []
    st.session_state.last_result = None
    st.session_state.total_tokens = 0

logger.info(f"Session ID: {st.session_state.session_id}")

# ============================================================================
# SIDEBAR & NAVIGATION
# ============================================================================

st.sidebar.markdown("---")
st.sidebar.markdown("# 🎭 Puls Events")
st.sidebar.title("📋 Menu")
st.sidebar.markdown("---")

page = st.sidebar.radio(
    "Sélectionner une page",
    [
        "🏠 Accueil",
        "🔍 Recherche Simple",
        "💬 Chat Interactif",
        "📊 Analytique"
    ],
    key="page_selection"
)

st.sidebar.markdown("---")

# Configuration snapshot date en sidebar
st.sidebar.markdown("### ⚙️ Configuration")

from src.config import Config
llm_provider = st.sidebar.selectbox(
    "Provider",
    options=Config.ALL_LLM
)

available_dates = Config.get_available_index_dates()
date_options = []
labels = []
embedders=[]
for d in available_dates:
    (date_str, (marker, size, embedder)) = list(d.items())[0]
    label = embedder[:1].upper()
    label += f":{date_str} ({size:.1f} MB)"
    if marker:
        label += f"  -  {marker}"
    date_options.append(date_str)
    labels.append(label)
    embedders.append(embedder)

# valeur par défaut: DEV_SNAPSHOT_DATE si présente, sinon dernière
default_date = Config.DEV_SNAPSHOT_DATE

# On utilise un selectbox avec labels, mais on stocke la vraie date
selected_label = st.sidebar.selectbox(
    "Snapshot disponible",
    options=labels,
    index=labels.index(
        next(l for l, d in zip(labels, date_options) if d == default_date)
    ),
    key="snapshot_date_sidebar"
)

# On récupère la date correspondant au label choisi
snapshot_date = date_options[labels.index(selected_label)]
embedder = embedders[labels.index(selected_label)]

# ✅ CALLBACK: Réinitialiser au changement de date
if llm_provider != st.session_state.get('previous_llm', "") or \
    snapshot_date != st.session_state.get('previous_snapshot_date', ""):
   
    Config.LLM_PROVIDER = llm_provider
    logger.info(f"Changing SeekEngine to {llm_provider} / {snapshot_date})")
    
    # Réinitialiser les engines
    if 'search_engine' in st.session_state:
        st.session_state.search_engine.load_engine(embedder, snapshot_date)
    if 'chat_engine' in st.session_state:
        st.session_state.chat_engine.load_engine(embedder,snapshot_date)
    
    
    st.session_state.previous_snapshot_date = snapshot_date
    st.session_state.previous_llm = llm_provider


st.sidebar.markdown("---")
st.sidebar.markdown(f"**Version**: v1.0 (Streamlit)")
st.sidebar.markdown(f"**Session**: {st.session_state.session_id}")

# ============================================================================
# PAGE ROUTING
# ============================================================================

if page == "🏠 Accueil":
    from src.ui.pages import home
    home.render(snapshot_date=snapshot_date, embedder = embedder)

elif page == "🔍 Recherche Simple":
    from src.ui.pages import search
    search.render(snapshot_date=snapshot_date, embedder = embedder)

elif page == "💬 Chat Interactif":
    from src.ui.pages import chat
    chat.render(snapshot_date=snapshot_date, embedder = embedder)

elif page == "📊 Analytique":
    from src.ui.pages import analytics
    analytics.render()

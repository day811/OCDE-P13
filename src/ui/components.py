# src/ui/components.py
"""
Composants Streamlit réutilisables pour l'interface RAG
"""

import streamlit as st
from typing import Dict, List, Optional
from src.utils.utils import flat_date_constraints
from datetime import datetime
import json 


def render_question_input(
    placeholder: str = "Ex: Concerts ce weekend à Toulouse",
    key: str = "question_input"
) -> str:
    """Render input field for user question."""
    question = st.text_area(
        "❓ Votre question",
        placeholder=placeholder,
        height=100,
        key=key
    )
    return question


def render_advanced_filters() -> Dict:
    """Render advanced filter options."""
    with st.expander("⚙️ Paramètres avancés", expanded=False):
        col1, col2, col3 = st.columns(3)
        
        with col1:
            top_k = st.slider(
                "Nombre de résultats (Top-K)",
                min_value=1,
                max_value=20,
                value=5,
                key="top_k_slider"
            )
        
        with col2:
            temperature = st.slider(
                "Température LLM",
                min_value=0.0,
                max_value=1.0,
                value=0.7,
                step=0.1,
                key="temperature_slider"
            )
        
    return {
        'top_k': top_k,
        'temperature': temperature,
    }


def render_answer(answer: str, is_chat: bool = False):
    """Render formatted answer."""
    if not answer:
        st.warning("Pas de réponse disponible.")
        return
    
    icon = "💬" if is_chat else "✨"
    st.markdown(f"### {icon} Réponse")
    
    st.markdown(f"""
    <div class="answer-box">
    {answer}
    </div>
    """, unsafe_allow_html=True)


def render_sources(sources: List[Dict], compact:bool = False):
    """Render list of source events."""
    if not sources:
        st.info("Aucune source trouvée.")
        return
    
    st.markdown(f"### 📍 Sources ({len(sources)} trouvées)")
    
    nb_cols = 2 if compact else 3
    cols = st.columns(min(len(sources), nb_cols))
    
    for idx, source in enumerate(sources):
        with cols[idx % len(cols)]:
            render_source_card(source, compact=compact)


def render_source_card(source: Dict, compact:bool = False):
    """Render single source card."""
    title = source.get('title', 'Sans titre')
    city = source.get('city', 'N/A')
    dates = source.get('dates', 'Date inconnue')
    url = source.get('url', '#')
    address = source.get('address')
    distance = source.get('distance')

    optional_br = " - " if compact else "<br>"
    
    relevance = ""
    if distance:
        relevance_pct = int((1 - distance) * 100)
        relevance = f"⭐ Pertinence: {relevance_pct}%"
    
    st.markdown(f"""
    <div class="source-card">
    <strong>{title}</strong>{optional_br}📅 : {dates}<br>
    📍 : {city}{optional_br}{address}
    <br>{relevance}{optional_br}
    <a href="{url}" target="_blank">🔗 Voir l'événement</a>
    </div>
    """, unsafe_allow_html=True)


def render_stats(result: Dict):
    """Render statistics about the query."""
    col1, col2, col3 = st.columns(3)
    
    with col1:
        total_tokens = result.get('total_tokens', 0)
        st.metric("📊 Tokens utilisés", total_tokens)
    
    with col2:
        exec_time = result.get('execution_time', 0)
        st.metric("⏱️ Temps d'exécution", f"{exec_time:.2f}s")
    
    with col3:
        sources_count = len(result.get('sources', []))
        st.metric("📍 Résultats", sources_count)
    
    with st.expander("📈 Détails", expanded=False):
        col4,col5 = st.columns(2)
        with col4:
            st.markdown('**Environnement**')
            st.json({
                'Snapshot Index' : result.get('snapshot_index',"").split('/')[-1],
                'LLM Chat Model' : result['llm_chat_model'],
                'LLM Embed Model' : result['llm_embed_model'],
                'Top_k' : result['top_k'],
                'Temperature' : result['temperature'],
            })

            st.markdown('**Contraintes**')
            st.json({
                'Question' : result['question'],
                'Date' : flat_date_constraints(result['constraints']['date']),
                'Département' : result['constraints']['dept'],
                'Ville' : result['constraints']['city'],
            })
        with col5:
#            download_button = st.button("📤 Enregistrer", use_container_width=True)

            st.markdown('**Statistiques**')
            mean_distance = result.get('mean_distance', None)
            avg_relevance = int((1 - float(mean_distance)) * 100) if mean_distance else "---"
            query_tokens = result.get('query_tokens', 0)
            context_tokens = result.get('context_tokens', 0)
            llm_tokens = result.get('llm_tokens', 0)
            timestamp = result.get('timestamp', datetime.now().strftime('%Y%m%d_%H%M%s'))
            faiss_time = result.get('faiss_time', 0)
            st.json({
                'total_tokens': total_tokens,
                'query tokens': query_tokens,
                'context tokens': context_tokens,
                'answer tokens': llm_tokens,
                'execution_time': f"{exec_time:.3f}s",
                'faiss search_time': f"{faiss_time:.3f}ms",
                'average relevance' : f"{avg_relevance}%",
                'sources_count': sources_count,
                'mode': result.get('mode', 'unknown'),
                'timestamp': timestamp
            })
            st.download_button(
                label="💾 JSON complet",
                data=json.dumps(result, default=str, ensure_ascii=False, indent=2),
                file_name=f"puls_result_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json",
                mime="application/json",
                use_container_width=True,
                key=f"dl_{st.session_state.session_id}_{timestamp}"
            )



def render_error(error_message: str):
    """Render error message."""
    st.markdown(f"""
    <div style="background-color: #ffe0e0; padding: 15px; border-radius: 8px; color: #d32f2f; border-left: 4px solid #d32f2f;">
    ❌ <strong>Erreur:</strong> {error_message}
    </div>
    """, unsafe_allow_html=True)


def render_no_index_error():
    """Render error when index is not available."""
    st.error("""
    ❌ **Index non disponible**
    
    L'index Faiss n'a pas été créé pour cette date.
    
    Pour corriger:
    1. Exécutez le script de pipeline: `python scripts/run_pipeline.py`
    2. Ou utilisez une date de snapshot différente
    """)

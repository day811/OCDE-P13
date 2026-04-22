# src/ui/pages/home.py
"""
Home page - Dashboard and introduction
"""

import streamlit as st
from src.config import Config
from pathlib import Path
import pandas as pd
from datetime import datetime


def render(snapshot_date: str = "", embedder: str=""):
    """Render home page."""
    
    st.title("🎭 Événements Culturels - Moteur RAG")
    st.markdown("---")
    
    col1, col2 = st.columns([2, 1])
    
    with col1:
        st.markdown("""
        ### Bienvenue ! 👋
        
        Cet outil vous permet de **rechercher et explorer les événements culturels** 
        de la région **Occitanie** de manière intuitive.
        
        Grâce à la technologie **RAG** (Retrieval-Augmented Generation), 
        l'application comprend vos questions naturelles et vous propose 
        les événements les plus pertinents.
        """)
        st.markdown("---")
        
        st.markdown("""
        ### ⚡ Démarrage rapide
                            
        1. **Rendez-vous** sur la page "🔍 Recherche Simple"
        2. **Posez une question** (ex: "Qu'est-ce qu'il y a à faire samedi ?")
        3. **Explorez les résultats** et les sources trouvées
        4. **Consultez les stats** d'utilisation des tokens
        """)    

    with col2:
        processed_path = Config.get_processed_snapshot_path(snapshot_date)
        if snapshot_date == Config.DEV_SNAPSHOT_DATE:
            str_today = snapshot_date
            today = datetime.strptime(snapshot_date, "%Y-%m-%d")
        else:
            today = datetime.now()
            str_today = today.strftime("%Y-%m-%d")
        df = pd.read_json(processed_path)
        nb_events = df.shape[0]
        mask = df['first_date']> today.isoformat()
        nb_future_events = df[mask].shape[0]
        st.markdown("🤖 Dataset")
        st.markdown( Config.BASE_URL)
        st.metric("📊 Région", Config.REGION)
        st.metric("🎭 Total Événements", nb_events)
        st.metric(f"🎭 Événements après today({str_today}) : ", nb_future_events)
    
    st.markdown("---")
    
    st.markdown("### 🚀 Fonctionnalités")
    
    col1, col2, col3 = st.columns(3)
    
    with col1:
        st.markdown("""
        #### 🔍 Recherche Simple
        
        Posez vos questions naturelles et recevez 
        les événements les plus pertinents.
        """)
    
    with col2:
        st.markdown("""
        #### 💬 Chat Interactif
        
        Conversez avec un assistant intelligent 
        pour explorer les événements en détail.
        """)
    
    with col3:
        st.markdown("""
        #### 📊 Analytique
        
        Suivez la consommation de tokens et 
        les performances du système.
        """)
    
    
    st.markdown("---")
    
    with st.expander("ℹ️ Informations techniques", expanded=False):
        col1, col2 = st.columns(2)
        api_key = Config.get_api_key()
        with col1:
            st.markdown("#### Configuration")
            st.write(f"""
            - **Api Key**     : {api_key[:3]}...{api_key[-3:]}
            - **Chat model**: {Config.LLM_PROVIDER}/{Config.get_chat_model()}
            - **Embedding Model**: {embedder}/{Config.get_embed_model(embedder)}
            - **Vector DB**: Faiss (IndexIVFFlat) with {embedder}
            - **Snapshot Date**: {snapshot_date or Config.DEV_SNAPSHOT_DATE}
            """)
        
        with col2:
            st.markdown("#### État des données")
            snapshot_date_check = snapshot_date or Config.DEV_SNAPSHOT_DATE
            short_index_path = Config.get_index_path(embedder,snapshot_date_check)
            index_path = Path(short_index_path)
            short_metadata_path = Config.get_metadata_path(embedder,snapshot_date_check)
            metadata_path = Path(short_metadata_path)
            
            status_index = f"{short_index_path.split('/')[-1]} : " + ( "✅ Disponible" if index_path.exists() else "❌ Absent")
            status_metadata = f"{short_metadata_path.split('/')[-1]} : " + ( "✅ Disponible" if metadata_path.exists() else "❌ Absent")

            st.write(f"""
                    - **Index Faiss**: {status_index}
                    - **Metadata**    : {status_metadata}  
                    """)

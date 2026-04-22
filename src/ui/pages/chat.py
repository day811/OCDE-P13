# src/ui/pages/chat.py
"""
Chat page - Interactive chat with LangChain
"""

import streamlit as st
import logging
from src.core.seek_engine import SeekEngine
from src.ui.components import render_no_index_error, render_advanced_filters, render_error,render_stats, render_sources
from pathlib import Path
from src.config import Config

logger = logging.getLogger(__name__)


def render(snapshot_date: str = "", embedder : str=""):
    """Render chat page."""
    
    st.title("💬 Chat Interactif")
    st.markdown("Conversez avec l'assistant pour explorer les événements")
    st.markdown("---")
    
    if 'chat_engine' not in st.session_state:
        st.session_state.chat_engine = None
    if 'messages' not in st.session_state:
        st.session_state.messages = []
    
    if 'should_submit_message' not in st.session_state:
        st.session_state.should_submit_message = False

    if 'should_save_conversation' not in st.session_state:
        st.session_state.should_save_conversation = False

    snapshot_date = snapshot_date or Config.DEV_SNAPSHOT_DATE
    
    # Check if index exists
    index_path = Path(Config.get_index_path(embedder, snapshot_date))
    if not index_path.exists():
        render_no_index_error()
        return
    
    # Initialize ChatEngine
    if st.session_state.chat_engine is None:
        try:
            st.session_state.chat_engine = SeekEngine(
                embedder=embedder,
                snapshot_date=snapshot_date,
                mode='chat'
            )
        except Exception as e:
            render_error(str(e))
            return
    
    # Display chat history
    for message in st.session_state.messages:
        if message['role'] == 'user':
            st.markdown(f"**👤 Vous:** {message['content']}")
        elif message['role'] == 'assistant':
            st.markdown(f"**🤖 Assistant:** {message['answer']}")
            if message['sources']:
                render_sources(message['sources'], compact=True )
            if message.get('total_tokens'):
                render_stats(message)
            else:
                st.info("Aucune source trouvée pour cette question.")

        elif message['role'] == 'error':
            st.error(message['content'])
  
    st.markdown("---")
    
    # Input section
    user_input = st.text_area(
        "💬 Votre message",
        height=80,
        placeholder="Posez une question...",
        key="chat_input"
    )
    
    col1, col2 = st.columns([2, 1])
    
    with col1:
        send_button = st.button("📤 Envoyer", use_container_width=True)
    
    with col2:
        if st.button("🔄 Nouvelle conv.", use_container_width=True):
            st.session_state.messages = []
            st.rerun()
    
    filters = render_advanced_filters()

    # ✅ CHECK BUTTON
    if send_button:
        st.session_state.should_submit_message = True
    
    # ✅ TRAITER SEULEMENT SI LE BOUTON A ÉTÉ CLIQUÉ
    if st.session_state.should_submit_message:
        st.session_state.should_submit_message = False  # Reset le flag
        
        if not user_input.strip():
            st.warning("⚠️ Veuillez entrer un message.")
            st.stop()
        
        logger.debug(f"[chat.render] User submitted: {user_input[:50]}...")
        
        # Ajouter le message utilisateur
        st.session_state.messages.append({
            'role': 'user',
            'content': user_input
        })
        
        # ✅ TRY/EXCEPT AVEC st.stop()
        try:
            logger.debug(f"[chat.render] Processing user input: {user_input[:50]}...")
            
            with st.spinner("🤖 L'assistant réfléchit..."):
                logger.debug(f"[chat.render] Calling search_engine.query...")
                
                result = st.session_state.chat_engine.query(
                    question=user_input,
                    top_k=filters['top_k'],
                    temperature=filters['temperature'],
                    session_id=st.session_state.session_id
                )
                
                logger.debug(f"[chat.render] Query successful, answer length: {len(result.get('answer', ''))}")
                
                message = result
                message['role'] = 'assistant'
                # Ajouter la réponse
                st.session_state.messages.append(message)
                user_input=""
                logger.info(f"[chat.render] Message processed successfully")
            
            # ✅ Si succès, rafraîchir l'interface
            st.rerun()
        
        except Exception as e:
            logger.error(f"[chat.render] Error occurred: {str(e)}", exc_info=True)
            
            # Ajouter le message d'erreur
            st.session_state.messages.append({
                'role': 'error',
                'content': f"❌ Erreur: {str(e)}",
            })
            
            # ✅ AFFICHER L'ERREUR ET S'ARRÊTER PROPREMENT
            st.error(f"""
            **❌ Erreur lors du traitement de votre message**
            
            ```
            {str(e)}
            ```
            
            Consultez les logs pour plus de détails.
            
            **Essayez**:
            - Recharger la page (F5)
            - Cliquer sur "🔄 Nouvelle conversation"
            - Vérifier que l'index Faiss existe
            """)
            
            logger.info(f"[chat.render] Error displayed, calling st.stop()")
            st.stop()  # ← Arrête sans boucle infinie!
    
    # Info si vide
    if len(st.session_state.messages) == 0:
        st.info("""
        ### 💡 Comment utiliser le chat ?
        
        1. **Posez une question naturelle** sur les événements culturels
        2. **L'assistant recherche les événements pertinents** en utilisant le RAG
        3. **Continuez la conversation** pour affiner votre recherche
        """)
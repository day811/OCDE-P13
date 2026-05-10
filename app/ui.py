import chainlit as cl
from chainlit.input_widget import Select, Slider
import os
from app.services.seek_engine import SeekEngine
from app.services.storage.settings_storage import SettingsStorageService
from app.services.storage.user_storage import UserStorageService
from app.services.storage.conversation_storage import ConversationStorageService
from app.config import get_unique_locations


@cl.password_auth_callback
async def auth_callback(username: str, password: str):
    """
    Validates user credentials. 
    In production, this will query a real DB or Azure AD.
    """
    user_service = UserStorageService()
    user_data = user_service.authenticate(username, password)
    
    if user_data:
        # On retourne l'objet User avec les métadonnées de la base
        return cl.User(identifier=username, metadata=user_data.get("metadata", {}))
    return None

@cl.on_chat_start
async def start():

    image_path = "./public/favicon.png"
    
    if os.path.exists(image_path):
        # On crée l'élément d'abord
        avatar = cl.Image(
            path=image_path, 
            name="Puls-Events Assistant", 
            display="side"
        )
        # On l'envoie explicitement (await est crucial ici)
        await avatar.send(for_id="")
    else:
        print(f"Erreur : Logo introuvable au chemin {image_path}")
        
    user = cl.user_session.get("user")
    settings_service = SettingsStorageService()
    
    # --- MÉMOIRE PERSISTANTE : INITIALISATION ---
    conv_service = ConversationStorageService()
    session_id = cl.user_session.get("id") # ID unique de la session Chainlit
    
    # Chargement de l'historique depuis Cosmos DB
    history = conv_service.get_history_by_user(user.identifier)
    # --------------------------------------------
    if history:
        for msg in history:
            await cl.Message(
                content=msg["content"],
                author="Utilisateur" if msg["role"] == "user" else "Assistant"
            ).send()

    # Load settings to customize the experience from the start
    user_settings = settings_service.get_settings(user.identifier) # type: ignore
    all_cities, all_depts = get_unique_locations()     

    city_options = ["Aucun"] + all_cities
    dept_options = ["Aucun"] + all_depts

    settings = await cl.ChatSettings([
        Select(
            id="favorite_city",
            label="Ville par défaut",
            values=city_options,
            initial_value=user_settings.get("favorite_city") or "Aucun"
        ),
        Select(
            id="favorite_dept",
            label="Département par défaut",
            values=dept_options,
            initial_value=user_settings.get("favorite_dept") or "Aucun"
        ),
        Slider(
            id="radius_km",
            label="Rayon (km)",
            initial=user_settings.get("radius_km", 20),
            min=5,
            max=100
        )
    ]).send()

    # Stockage en session
    cl.user_session.set("settings", user_settings)
    cl.user_session.set("chat_history", history) # On utilise l'historique chargé
    cl.user_session.set("engine", SeekEngine())
    cl.user_session.set("settings_service", settings_service)
    cl.user_session.set("conv_service", conv_service) # Stockage du service de mémoire

    await cl.Message(
        content=f"Bonjour {user.identifier} ! Ravi de te revoir. " # type: ignore
                f"Mémoire conversationnelle et réglages chargés."
    ).send()

@cl.on_settings_update
async def setup_agent(settings):
    user = cl.user_session.get("user")
    storage = cl.user_session.get("settings_service")
    
    # Transform de "Aucun" en None avant la sauvegarde
    processed_settings = settings.copy()
    if processed_settings.get("favorite_city") == "Aucun":
        processed_settings["favorite_city"] = None
    if processed_settings.get("favorite_dept") == "Aucun":
        processed_settings["favorite_dept"] = None
        
    storage.save_settings(user.identifier, processed_settings) # type: ignore
    cl.user_session.set("settings", processed_settings)
    
    await cl.Message(content="✅ Préférences mises à jour.").send()

@cl.on_message
# app/ui.py

@cl.on_message
async def main(message: cl.Message):
    engine = cl.user_session.get("engine")
    history: list = cl.user_session.get("chat_history") # type: ignore
    user = cl.user_session.get("user")
    user_settings: dict = cl.user_session.get("settings") # type: ignore
    storage = cl.user_session.get("settings_service")
    conv_service = cl.user_session.get("conv_service")
    session_id = cl.user_session.get("id")
    
    # 1. Sauvegarde immédiate de la question
    conv_service.save_message(session_id, user.identifier, "user", message.content)

    # 2. Initialisation du message de réponse vide pour le streaming
    res_msg = cl.Message(content="")
    
    full_answer = ""
    metadata = {}

    # 3. Consommation du stream
    # search est maintenant une fonction asynchrone génératrice
    async for chunk in engine.search(
        user_query=message.content,
        user_id=user.identifier,
        chat_history=history,
        fav_city=user_settings.get("favorite_city"),
        fav_dept=user_settings.get("favorite_dept")
    ):
        if isinstance(chunk, str):
            # C'est un morceau de texte (token)
            full_answer += chunk
            await res_msg.stream_token(chunk)
        elif isinstance(chunk, dict):
            # C'est le dictionnaire de métadonnées final
            metadata = chunk

    # 4. Finalisation de l'affichage (Usage & Footer)
    usage = metadata.get("usage", {"prompt": 0, "completion": 0, "total": 0})
    cumulative = storage.update_usage(
        user.identifier, 
        usage.get("prompt", 0), 
        usage.get("completion", 0)
    )
    
    footer = f"\n\n*(Consommation : {usage['total']} tokens | Cumul : {cumulative['total_tokens']})*"
    res_msg.content = full_answer + footer
    await res_msg.send()

    # 5. Sauvegardes finales
    conv_service.save_message(session_id, user.identifier, "assistant", full_answer)
    
    history.append({"role": "user", "content": message.content})
    history.append({"role": "assistant", "content": full_answer})
    cl.user_session.set("chat_history", history[-10:])
import chainlit as cl
import os
from app.services.seek_engine import SeekEngine
from app.services.settings_storage import SettingsStorageService
from chainlit.input_widget import Select, Slider
from app.config import get_unique_locations

# Mock user database for local dev
USERS = {
    "admin": "p@ssword123",
    "yves": "occitanie2026"
}

@cl.password_auth_callback
async def auth_callback(username: str, password: str):
    """
    Validates user credentials. 
    In production, this will query a real DB or Azure AD.
    """
    if USERS.get(username) == password:
        return cl.User(identifier=username)
    return None

@cl.on_chat_start
async def start():
    user = cl.user_session.get("user")
    settings_service = SettingsStorageService()
    
    # Load settings to customize the experience from the start
    user_settings = settings_service.get_settings(user.identifier)# type: ignore
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

    cl.user_session.set("settings", user_settings)
    cl.user_session.set("chat_history", [])
    cl.user_session.set("engine", SeekEngine())
    cl.user_session.set("settings_service", settings_service)

    await cl.Message(
        content=f"Bonjour {user.identifier} ! Ravi de te revoir. " # type: ignore
                f"Tes réglages pour {user_settings.get('favorite_city') or 'l\'Occitanie'} sont chargés."
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
async def main(message: cl.Message):
    engine = cl.user_session.get("engine")
    history:list = cl.user_session.get("chat_history") # type: ignore
    user = cl.user_session.get("user")
    user_settings:dict = cl.user_session.get("settings") # type: ignore
    storage = cl.user_session.get("settings_service")
    
    # 1. Search with history
    res = engine.search( # type: ignore
        user_query=message.content,
        user_id=user.identifier, # type: ignore
        chat_history=history,
        fav_city=user_settings.get("favorite_city"),
        fav_dept=user_settings.get("favorite_dept")
    )    
    # 2. Update local history (Sliding window of last 10 messages)
    history.append({"role": "user", "content": message.content})
    history.append({"role": "assistant", "content": res["answer"]})
    cl.user_session.set("chat_history", history[-10:])
    
    # 2. Accounting : Mise à jour persistante
    usage = res.get("usage", {"prompt": 0,"completion": 0,"total": 0})
    cumulative = storage.update_usage( # type: ignore
        user.identifier,  # type: ignore
        usage.get("prompt", 0), 
        usage.get("completion", 0)
    )

    # 3. Affichage (Optionnel : petit texte discret en bas de réponse)
    footer = f"\n\n*(Consommation : {usage['total']} tokens | Cumul : {cumulative['total_tokens']})*"
    await cl.Message(content=res["answer"] + footer).send()
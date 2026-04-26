import chainlit as cl
import os
from app.services.seek_engine import SeekEngine
from app.services.settings_storage import SettingsStorageService

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
    user_settings = settings_service.get_settings(user.identifier)
    cl.user_session.set("settings", user_settings)
    
    cl.user_session.set("engine", SeekEngine())
    cl.user_session.set("settings_service", settings_service)

    await cl.Message(
        content=f"Bonjour {user.identifier} ! Ravi de te revoir. "
                f"Tes réglages pour {user_settings.get('favorite_city') or 'l\'Occitanie'} sont chargés."
    ).send()

@cl.on_message
async def main(message: cl.Message):
    engine = cl.user_session.get("engine")
    
    # Execute RAG
    res = engine.search(message.content)
    
    # Send answer
    await cl.Message(content=res["answer"]).send()
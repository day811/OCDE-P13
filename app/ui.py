# app/ui.py
"""
Chainlit UI for Puls-Events AI chatbot.

Conversation persistence (left pane history, new chat button) is handled
natively by the SQLAlchemy data layer declared below.
UserSettings and token usage are still managed via SettingsStorageService.
"""

import os
import chainlit as cl
from chainlit.input_widget import Select, Slider

from app.services.seek_engine import SeekEngine
from app.services.storage.user_storage import UserStorageService
from app.services.storage.settings_storage import SettingsStorageService
from app.services.storage.chainlit_storage import get_data_layer
from app.config import get_unique_locations

# ── Data layer registration ────────────────────────────────────────────────────
# This single decorator activates the left-pane conversation history,
# the New Chat button, and message persistence — no extra code needed.

cl.data_layer(get_data_layer)

# ── Authentication ─────────────────────────────────────────────────────────────

@cl.password_auth_callback
async def auth_callback(username: str, password: str):
    """
    Validates user credentials against Cosmos DB.
    Returns a cl.User object on success, None on failure.
    """
    user_service = UserStorageService()
    user_data = user_service.authenticate(username, password)
    if user_data:
        return cl.User(identifier=username, metadata=user_data.get("metadata", {}))
    return None


# ── Chat start ─────────────────────────────────────────────────────────────────

@cl.on_chat_start
async def start():
    """
    Initialises a new chat session:
      1. Displays the assistant avatar.
      2. Loads and applies user settings.
      3. Registers session variables.
      4. Sends the welcome message.
    """
    # 1. Avatar
    image_path = "./public/favicon.png"
    if os.path.exists(image_path):
        avatar = cl.Image(path=image_path, name="Puls-Events Assistant", display="side")
        await avatar.send(for_id="")

    user             = cl.user_session.get("user")
    settings_service = SettingsStorageService()
    user_settings    = settings_service.get_settings(user.identifier)

    # 2. Settings widgets
    all_cities, all_depts = get_unique_locations()

    await cl.ChatSettings([
        Select(
            id="favorite_city",
            label="Ville par défaut",
            values=["Aucun"] + all_cities,
            initial_value=user_settings.get("favorite_city") or "Aucun"
        ),
        Select(
            id="favorite_dept",
            label="Département par défaut",
            values=["Aucun"] + all_depts,
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

    # 3. Session variables
    cl.user_session.set("settings",         user_settings)
    cl.user_session.set("chat_history",     [])
    cl.user_session.set("engine",           SeekEngine())
    cl.user_session.set("settings_service", settings_service)

    # 4. Welcome message
    await cl.Message(
        content=f"Bonjour **{user.identifier}** ! Que puis-je faire pour vous ?"
    ).send()


# ── Settings update ────────────────────────────────────────────────────────────

@cl.on_settings_update
async def on_settings_update(settings: dict):
    """Persists updated user settings to storage."""
    user    = cl.user_session.get("user")
    storage = cl.user_session.get("settings_service")

    processed = {
        "favorite_city": None if settings.get("favorite_city") == "Aucun" else settings.get("favorite_city"),
        "favorite_dept": None if settings.get("favorite_dept") == "Aucun" else settings.get("favorite_dept"),
        "radius_km":     settings.get("radius_km", 20),
    }
    storage.save_settings(user.identifier, processed)
    cl.user_session.set("settings", processed)
    await cl.Message(content="✅ Préférences mises à jour.").send()


# ── Main message handler ───────────────────────────────────────────────────────

@cl.on_message
async def main(message: cl.Message):
    """
    Handles incoming user messages:
      1. Streams the RAG engine response token by token.
      2. Appends token usage to the response footer.
      3. Updates the in-memory history (last 20 messages = 10 turns).

    Note: Message persistence to the data layer is handled automatically
    by Chainlit — no explicit save_message() call needed here.
    """
    engine        = cl.user_session.get("engine")
    history: list = cl.user_session.get("chat_history")
    user          = cl.user_session.get("user")
    user_settings = cl.user_session.get("settings")
    storage       = cl.user_session.get("settings_service")

    # Stream response
    res_msg     = cl.Message(content="")
    full_answer = ""
    metadata    = {}

    async for chunk in engine.search(
        user_query=message.content,
        user_id=user.identifier,
        chat_history=history,
        fav_city=user_settings.get("favorite_city"),
        fav_dept=user_settings.get("favorite_dept")
    ):
        if isinstance(chunk, str):
            full_answer += chunk
            await res_msg.stream_token(chunk)
        elif isinstance(chunk, dict):
            metadata = chunk

    # Token usage footer
    usage      = metadata.get("usage", {"prompt": 0, "completion": 0, "total": 0})
    cumulative = storage.update_usage(
        user.identifier,
        usage.get("prompt", 0),
        usage.get("completion", 0)
    )
    res_msg.content = (
        full_answer
        + f"\n\n*(Consommation : {usage['total']} tokens"
        + f" | Cumul : {cumulative['total_tokens']})*"
    )
    await res_msg.send()

    # Update in-memory history (kept for RAG context condensation)
    history.append({"role": "user",      "content": message.content})
    history.append({"role": "assistant", "content": full_answer})
    cl.user_session.set("chat_history", history[-20:])
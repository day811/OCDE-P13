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
cl.data_layer(get_data_layer)


# ── Shared session initialisation ──────────────────────────────────────────────

async def _init_session(user: cl.User) -> None:
    """
    Initialises all session variables required by on_message.
    Called both from on_chat_start (new conversation) and
    on_chat_resume (loading an existing conversation from history).

    Args:
        user (cl.User): The authenticated Chainlit user object.
    """
    settings_service = SettingsStorageService()
    user_settings    = settings_service.get_settings(user.identifier)
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

    cl.user_session.set("settings",         user_settings)
    cl.user_session.set("chat_history",     [])
    cl.user_session.set("engine",           SeekEngine())
    cl.user_session.set("settings_service", settings_service)


# ── Authentication ─────────────────────────────────────────────────────────────

@cl.password_auth_callback
async def auth_callback(username: str, password: str):
    """
    Validates user credentials against Cosmos DB.
    Returns a cl.User object on success, None on failure.
    """
    user_service = UserStorageService()
    user_data    = user_service.authenticate(username, password)
    if user_data:
        return cl.User(identifier=username, metadata=user_data.get("metadata", {}))
    return None


# ── Chat start (new conversation) ─────────────────────────────────────────────

@cl.on_chat_start
async def start():
    """
    Initialises a brand-new chat session.
    Displays avatar, initialises session variables, sends welcome message.
    """
    # Avatar
    image_path = "./public/favicon.png"
    if os.path.exists(image_path):
        avatar = cl.Image(path=image_path, name="Puls-Events Assistant", display="side")
        await avatar.send(for_id="")

    user = cl.user_session.get("user")
    await _init_session(user)

    await cl.Message(
        content=f"Bonjour **{user.identifier}** ! Que puis-je faire pour vous ?"
    ).send()


# ── Chat resume (loading existing conversation from left pane) ────────────────

@cl.on_chat_resume
async def resume(thread: dict):
    """
    Restores session variables when an existing conversation is loaded
    from the left-pane history. Without this callback, on_message would
    find empty session variables and the input area would be disabled.

    Args:
        thread (dict): The thread metadata provided by Chainlit's data layer.
    """
    user = cl.user_session.get("user")
    await _init_session(user)

    # Rebuild in-memory history from persisted thread messages
    # so the RAG engine has context for follow-up questions
    history = []
    for message in thread.get("steps", []):
        role    = "user" if message.get("type") == "user_message" else "assistant"
        content = message.get("output", "")
        if content:
            history.append({"role": role, "content": content})

    # Keep only the last 10 turns (20 messages)
    cl.user_session.set("chat_history", history[-20:])


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
      1. Checks guest daily quota.
      2. Streams the RAG engine response token by token.
      3. Persists token usage to PostgreSQL.
      4. Appends token usage to the response footer.
      5. Updates the in-memory history (last 10 turns = 20 messages).

    Note: Message persistence to the data layer is handled automatically
    by Chainlit — no explicit save_message() call needed here.
    """
    engine        = cl.user_session.get("engine")
    history: list = cl.user_session.get("chat_history")
    user          = cl.user_session.get("user")
    user_settings = cl.user_session.get("settings")
    storage       = cl.user_session.get("settings_service")

    # 1. Guest quota check
    quota = storage.check_daily_quota(user.identifier, user.metadata)
    if not quota["allowed"]:
        await cl.Message(content=quota["reason"]).send()
        return

    # 2. Stream response
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

    # 3. Persist token usage to PostgreSQL (async)
    usage      = metadata.get("usage", {"prompt": 0, "completion": 0, "total": 0})
    cumulative = await storage.update_usage(
        user.identifier,
        cl.context.session.thread_id,
        usage.get("prompt", 0),
        usage.get("completion", 0)
    )

    # 4. Increment guest daily counter
    if user.metadata.get("role") == "guest":
        storage.increment_daily_usage(user.identifier, usage.get("total", 0))

    # 5. Token usage footer
    res_msg.content = (
        full_answer
        + f"\n\n*(Consommation : {usage['total']} tokens"
        + f" | Cumul : {cumulative['total_tokens']})*"
    )
    await res_msg.send()

    # 6. Update in-memory history
    history.append({"role": "user",      "content": message.content})
    history.append({"role": "assistant", "content": full_answer})
    cl.user_session.set("chat_history", history[-20:])
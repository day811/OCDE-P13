# app/ui.py
"""
Chainlit UI for Puls-Events AI chatbot.

Conversation persistence (left pane history, new chat button) is handled
natively by the SQLAlchemy data layer declared below.
UserSettings and token usage are still managed via SettingsStorageService.
"""

import os
import chainlit as cl
from chainlit.input_widget import Select, Slider, TextInput
from chainlit.types import ThreadDict
import logging 
from app.services.seek_engine import SeekEngine
from app.services.storage.user_storage import UserStorageService
from app.services.storage.settings_storage import SettingsStorageService
from app.services.storage.chainlit_storage import get_data_layer
from app.config import get_cached_locations , warm_location_cache

logger = logging.getLogger(__name__)

# ── Data layer registration ────────────────────────────────────────────────────
cl.data_layer(get_data_layer)

# ── Geographic reference cache ─────────────────────────────────
# Loaded once at app startup, shared across all modules

_engine: SeekEngine 

@cl.on_app_startup
async def startup():
    global _engine
    warm_location_cache()   # charge villes/depts une fois
    _engine = SeekEngine()  # SeekEngine appelle aussi get_unique_locations()
    logger.info("App startup complete")

    
# ── Shared session initialisation ──────────────────────────────────────────────

async def _init_session(user: cl.User) -> None:
    """
    Initialises all session variables required by on_message.
    Called both from on_chat_start (new conversation) and
    on_chat_resume (loading an existing conversation from history).

    Args:
        user (cl.User): The authenticated Chainlit user object.
    """
    logger.info("_init_session: start")
    settings_service = SettingsStorageService()
    user_settings    = settings_service.get_settings(user.identifier)
    logger.info("_init_session: settings loaded")

    _ , all_depts = get_cached_locations()
    logger.info(f"_init_session: locations loaded ({len(all_depts)} departments)")

    await cl.ChatSettings([
        TextInput(
            id="favorite_city",
            label="Ville par défaut",
            initial=user_settings.get("favorite_city") or "",
            placeholder="ex: Toulouse"
        ),
        Select(
            id="favorite_dept",
            label="Département par défaut",
            values=["Aucun"] + all_depts,
            initial_value=user_settings.get("favorite_dept") or "Aucun"
        ),
        Slider(
            id="top_k",
            label="Nombre de résultats souhaités",
            initial=user_settings.get("top_k", 5),
            min=1,
            max=10,
            step=1
        )
    ]).send()
    logger.info("_init_session: ChatSettings sent")

    cl.user_session.set("settings",         user_settings)
    cl.user_session.set("chat_history",     [])
    cl.user_session.set("engine",           _engine)
    logger.info("_init_session: SeekEngine loaded")
    cl.user_session.set("settings_service", settings_service)
    logger.info("_init_session: complete")


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
async def resume(thread: ThreadDict):
    """
    Restores session variables when an existing conversation is loaded
    from the left-pane history. Without this callback, on_message would
    find empty session variables and the input area would be disabled.

    Args:
        thread (dict): The thread metadata provided by Chainlit's data layer.
    """
    logger.info(f"on_chat_resume triggered for thread: {thread.get('id', 'unknown')}")
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

# ── PATCH: replace the full on_message handler in app/ui.py ──────────────────

@cl.on_message
async def main(message: cl.Message):
    """
    Handles incoming user messages with a grouped step display:
      - All RAG pipeline steps are nested inside a single collapsible parent step.
      - The parent step collapses automatically once the answer starts streaming.
      - Web search fallback shows a dedicated waiting indicator.
      - Token usage footer is appended after streaming completes.
    """
    engine        = cl.user_session.get("engine")
    history       = cl.user_session.get("chat_history")
    user          = cl.user_session.get("user")
    user_settings = cl.user_session.get("settings")
    storage       = cl.user_session.get("settings_service")

    # Guest daily quota check
    quota = storage.check_daily_quota(user.identifier, user.metadata)
    if not quota["allowed"]:
        await cl.Message(content=quota["reason"]).send()
        return

    # Accumulators
    full_answer  = ""
    metadata     = {}
    step_buffer  = {}   # Accumulates step content by name before display
    web_step     = None # Reference to the web search step for live updates

    # ── Single collapsible parent step ─────────────────────────────────────────
    # All pipeline steps are nested inside this parent.
    # It collapses once the LLM answer begins streaming.
    async with cl.Step(name="⚙️ Analyse en cours...", type="run", default_open=True) as parent_step:

        res_msg = cl.Message(content="")

        async for chunk in engine.search(
            user_query=message.content,
            user_id=user.identifier,
            thread_id=cl.context.session.thread_id or "",
            chat_history=history,
            fav_city=user_settings.get("favorite_city"),
            fav_dept=user_settings.get("favorite_dept"),
            top_k=int(user_settings.get("top_k", 5))
        ):
            # ── Step chunk: pipeline progress indicator ─────────────────────
            if isinstance(chunk, dict) and chunk.get("type") == "step":
                name    = chunk["name"]
                content = chunk["content"]

                if name == "🌐 Recherche web":
                    # Web search: show a dedicated child step with waiting message
                    # This step stays open during the long smolagents call
                    web_step = cl.Step(
                        name=name,
                        type="run",
                        parent_id=parent_step.id
                    )
                    await web_step.__aenter__()
                    web_step.output = (
                        "⏳ Recherche sur les sites événementiels...\n"
                        "*(billetweb, eventbrite, openagenda, fnacspectacles...)*"
                    )
                    await web_step.update()
                else:
                    # Regular pipeline steps: accumulate and display as compact child steps
                    async with cl.Step(
                        name=name,
                        type="run",
                        parent_id=parent_step.id,
                        default_open= True,
                        auto_collapse=False
                    ) as child_step:
                        child_step.output = content
                        await child_step.update()

            # ── String chunk: LLM token streaming ──────────────────────────
            elif isinstance(chunk, str):
                # Close the web search step cleanly before streaming starts
                if web_step is not None:
                    web_step.output = "✅ Résultats web récupérés"
                    await web_step.__aexit__(None, None, None)
                    web_step = None

                # Update parent step name to signal completion
                if not full_answer:
                    parent_step.name = "⚙️ Analyse terminée"

                full_answer += chunk
                await res_msg.stream_token(chunk)

            # ── Final metadata dict ─────────────────────────────────────────
            elif isinstance(chunk, dict) and "usage" in chunk:
                metadata = chunk

        # Update parent step summary before it collapses
        parent_step.output = (
            f"Analyse terminée · "
            f"{metadata.get('usage', {}).get('total', 0)} tokens"
        )

    # ── Token usage footer ──────────────────────────────────────────────────────
    usage      = metadata.get("usage", {"prompt": 0, "completion": 0, "total": 0})
    cumulative = await storage.update_usage(
        user.identifier,
        cl.context.session.thread_id,
        usage.get("prompt", 0),
        usage.get("completion", 0)
    )

    if user.metadata.get("role") == "guest":
        storage.increment_daily_usage(user.identifier, usage.get("total", 0))

    res_msg.content = (
        full_answer
        + f"\n\n*(Consommation : {usage['total']} tokens"
        + f" | Cumul : {cumulative['total_tokens']})*"
    )
    await res_msg.send()

    # ── Update in-memory history ────────────────────────────────────────────────
    history.append({"role": "user",      "content": message.content})
    history.append({"role": "assistant", "content": full_answer})
    cl.user_session.set("chat_history", history[-20:])
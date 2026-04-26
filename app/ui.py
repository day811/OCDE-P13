import chainlit as cl
from app.services.seek_engine import SeekEngine

@cl.on_chat_start
async def start():
    # Initialize engine in user session
    cl.user_session.set("engine", SeekEngine())
    await cl.Message(content="Welcome to Puls-Events! How can I help you find an event in Occitanie?").send()

@cl.on_message
async def main(message: cl.Message):
    engine = cl.user_session.get("engine")
    
    # Execute RAG
    res = engine.search(message.content)
    
    # Send answer
    await cl.Message(content=res["answer"]).send()
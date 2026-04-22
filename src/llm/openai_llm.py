from typing import List
from src.llm.base import BaseLLM
from openai import OpenAI
import logging
from src.config import Config

logger = logging.getLogger(__name__)

class OpenAILLM(BaseLLM):

    NAME = "Open AI"
    PROVIDER = "openai"
    CHAT_MODEL = Config.get_chat_model(PROVIDER)
    EMBED_MODEL = Config.get_embed_model(PROVIDER)
    API_KEY = Config.get_api_key(PROVIDER)

    def __init__(self, temperature: float = 0.7):

        super().__init__(temperature)

        self.client = OpenAI(api_key=self.API_KEY)
        logger.info(f"OpenAILLM initialized - Chat: {self.CHAT_MODEL}, Embed: {self.EMBED_MODEL}, Temp: {self.temperature}")
    
    def generate(self, prompt: str, temperature: float = 0.7) -> str:
        """Generate text using OpenAI chat API"""
        temp = temperature if temperature is not None else self.temperature
        response = self.client.chat.completions.create(
            model=self.CHAT_MODEL,
            messages=[{"role": "user", "content": prompt}],
            temperature=temp
        )
        return response.choices.message.content # type: ignore
    
    def embed(self, text: str) :
        """Generate embeddings using OpenAI embed API"""
        response = self.client.embeddings.create(
            model=self.EMBED_MODEL,
            input=text
        )
        if isinstance(text, list):
            # Multiple texts → return list of embeddings
            response = self.client.embeddings.create(
                model=self.EMBED_MODEL,
                input=text
            )
            return [embed.embedding for embed in response.data]
        else:
            # Single text → return single embedding
            response = self.client.embeddings.create(
                model=self.embed_model,
                input=[text]
            )
            return response.data[0].embedding

    @classmethod
    def get_langchain(cls,temperature: float = 0.7):
        from langchain_openai import ChatOpenAI


        return ChatOpenAI(
            model=cls.CHAT_MODEL, # type: ignore
            api_key=cls.API_KEY,
            temperature=temperature
        )

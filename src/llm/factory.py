from src.llm.mistral_llm import MistralLLM
from src.llm.openai_llm import OpenAILLM
from src.llm.gemini_llm import GeminiLLM


import logging
from src.config import Config

logger = logging.getLogger(__name__)

class LLMFactory:
    """Factory for creating LLM instances"""
    
    PROVIDERS = {
        'mistral': MistralLLM,
        'openai': OpenAILLM,
        'gemini': GeminiLLM
    }
    
    @staticmethod
    def create_llm(temperature: float = 0.7, provider:str=""):
        """Create LLM instance based on provider"""
        if not provider:
            provider = Config.LLM_PROVIDER
        
        if provider not in LLMFactory.PROVIDERS:
            raise ValueError(f"Unknown provider: {provider}. Available: {list(LLMFactory.PROVIDERS.keys())}")
        
        logger.info(f"Creating LLM instance - Provider: {provider}")
        return LLMFactory.PROVIDERS[provider](temperature=temperature )

    @staticmethod
    def create_langchain(temperature: float = 0.7, provider:str=Config.LLM_PROVIDER):
        """Create LLM instance based on provider"""
        
        if provider not in LLMFactory.PROVIDERS:
            raise ValueError(f"Unknown provider: {provider}. Available: {list(LLMFactory.PROVIDERS.keys())}")
        
        logger.info(f"Creating Langchain instance - Provider: {provider}")
        return LLMFactory.PROVIDERS[provider].get_langchain(temperature=temperature )


def get_llm(temperature: float = 0.7, provider:str=Config.LLM_PROVIDER):
    """Convenience function to get LLM instance"""

    return LLMFactory.create_llm( temperature, provider)


def get_langchain_llm( temperature: float = 0.7, provider:str  = Config.LLM_PROVIDER):
    """
    Factory pour LangChain LLM multi-provider.
    
    Args:
        provider: 'mistral', 'openai', 'gemini', 'perplexity'
        api_key: Clé API correspondante
        model: Modèle spécifique (optionnel)
        temperature: 0.0-1.0
    """
    provider  = Config.LLM_PROVIDER

    return LLMFactory.create_langchain( temperature, provider)



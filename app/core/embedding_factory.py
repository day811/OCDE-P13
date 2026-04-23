import os
from langchain_mistralai import MistralAIEmbeddings
from langchain_openai import AzureOpenAIEmbeddings

class EmbeddingFactory:
    @staticmethod
    def get_embedding_model():
        env = os.getenv("ENV", "LOCAL").upper()
        
        if env == "AZURE":
            return AzureOpenAIEmbeddings(
                azure_deployment=os.getenv("AZURE_EMBEDDING_DEPLOYMENT"),
                api_key=os.getenv("AZURE_OPENAI_API_KEY")
            )
        else:
            return MistralAIEmbeddings(
                model="mistral-embed",
                api_key=os.getenv("MISTRAL_API_KEY")
            )
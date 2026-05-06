import os, dotenv
from langchain_mistralai import MistralAIEmbeddings
from langchain_openai import AzureOpenAIEmbeddings

dotenv.load_dotenv()

class EmbeddingFactory:
    @staticmethod
    def get_embedding_model():
        env = os.getenv("ENV", "LOCAL").upper()
        
        if env == "AZURE":
            # On récupère proprement les variables
            endpoint = os.getenv("AZURE_OPENAI_ENDPOINT")
            api_key = os.getenv("AZURE_OPENAI_API_KEY","")
            deployment = os.getenv("AZURE_EMBEDDING_DEPLOYMENT")
            # On force une version récente si la variable est vide
            api_version = os.getenv("AZURE_OPENAI_API_VERSION", "2024-02-15-preview")

            return AzureOpenAIEmbeddings(
                azure_endpoint=endpoint,
                azure_deployment=deployment,
                api_key=api_key,
                api_version=api_version
        )
        else:
            return MistralAIEmbeddings(
                model="mistral-embed",
                api_key=os.getenv("MISTRAL_API_KEY")
            )
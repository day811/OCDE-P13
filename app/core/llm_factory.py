import os
from dotenv import load_dotenv
from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_openai import AzureChatOpenAI

load_dotenv()

class LLMFactory:
    @staticmethod
    def get_chat_model():
        env = os.getenv("ENV", "LOCAL").upper()
        
        if env == "AZURE":
            return AzureChatOpenAI(
                azure_deployment=os.getenv("AZURE_OPENAI_DEPLOYMENT"),
                api_key=os.getenv("AZURE_OPENAI_API_KEY"), # type: ignore
                azure_endpoint=os.getenv("AZURE_OPENAI_ENDPOINT"),
                api_version=os.getenv("AZURE_OPENAI_API_VERSION"),
                temperature=0
            )
        else:
            return ChatGoogleGenerativeAI(
                model="gemini-2.5-flash-lite",
                google_api_key=os.getenv("GOOGLE_API_KEY"),
                temperature=0.3
            )
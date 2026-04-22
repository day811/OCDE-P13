"""
RAG System Configuration
Manages environment, snapshot versions, and paths
"""

from enum import Enum
from pathlib import Path
import os
from dotenv import load_dotenv
from typing import cast, Any
from datetime import datetime


load_dotenv()


class Environment(Enum):
    """Execution environment"""
    DEVELOPMENT = "development"  # Phase 2-5: Fixed snapshot for testing
    DEMO = "demo"                # Soutenance: Latest snapshot
    PRODUCTION = "production"    # After delivery


class Config:

    # Open Agenda API endpoint (free, no auth required)
    BASE_URL = "https://public.opendatasoft.com/api/explore/v2.1/catalog/datasets/evenements-publics-openagenda/records/"

    """Manage snapshot versions and index selection"""
    
    # ============= PATHS =============
    BASE_DIR = Path(__file__).parent.parent
    DATA_DIR = BASE_DIR / "data"
    RAW_DATA_DIR = DATA_DIR / "raw"
    PROCESSED_DATA_DIR = DATA_DIR / "processed"
    INDEXES_DIR = DATA_DIR / "indexes"
    
    # Create directories if they don't exist
    RAW_DATA_DIR.mkdir(parents=True, exist_ok=True)
    PROCESSED_DATA_DIR.mkdir(parents=True, exist_ok=True)
    INDEXES_DIR.mkdir(parents=True, exist_ok=True)
    
    # ============= SNAPSHOT CONFIGURATION =============
    # FROZEN snapshot for reproducible testing (Phase 2-5)
    DEV_SNAPSHOT_DATE = os.getenv("DEV_SNAPSHOT_DATE","2026-01-29")
    
    # Current execution environment
    ENVIRONMENT = Environment[os.getenv("RAG_ENVIRONMENT", "development").upper()]
    
# ==================== LLM CONFIGURATION ====================
    
    LLM_MISTRAL = "mistral"
    LLM_OPENAI = "openai"
    LLM_GEMINI = "gemini"
    
    
    # Provider: 'mistral', 'openai', 'gemini'
    LLM_PROVIDER = os.getenv('LLM_PROVIDER', 'mistral')
    
    # API Keys
    API_KEYS = { 
        LLM_MISTRAL : os.getenv('MISTRAL_API_KEY','') ,
        LLM_OPENAI :  os.getenv('OPENAI_API_KEY',''), 
        LLM_GEMINI :  os.getenv('GEMINI_API_KEY','') }
    
    ALL_LLM = [LLM_MISTRAL, LLM_GEMINI, LLM_OPENAI]
    
    # Default models fallback (if not specified in .env)
    LLM_MODELS = {
        'mistral': {
            'chat': os.getenv('MISTRAL_CHAT_MODEL', 'mistral-small'),
            'embed': os.getenv('MISTRAL_EMBED_MODEL', 'mistral-embed')
        },
        'openai': {
            'chat': os.getenv('OPENAI_CHAT_MODEL', 'gpt-4o-mini'),
            'embed': os.getenv('OPENAI_EMBED_MODEL', 'text-embedding-3-small')
        },
        'gemini': {
            'chat': os.getenv('GEMINI_CHAT_MODEL', 'gemini-2.5-flash'),
            'embed': os.getenv('GEMINI_EMBED_MODEL', 'gemini-embedding-001')
        }
    }
    
    # Models per provider
    LLM_CHAT_MODEL = os.getenv('LLM_CHAT_MODEL') or LLM_MODELS[LLM_PROVIDER]['chat']
    LLM_EMBED_MODEL = os.getenv('LLM_EMBED_MODEL') or LLM_MODELS[LLM_PROVIDER]['embed']
    
    # Temperature for generation (0.0 = deterministic, 1.0 = random)
    LLM_TEMPERATURE = float(os.getenv('LLM_TEMPERATURE', '0.7'))

    # ============= DATA PARAMETERS =============
    # Geographic region for filtering
    REGION = os.getenv("RAG_REGION", "Occitanie")
    
    # Historical period (days) for data collection
    DAYS_BACK = int(os.getenv("RAG_DAYS_BACK", "365"))

    # Max pages limit to fetch
    MAX_PAGES = os.getenv("MAX_PAGES", None)
    if MAX_PAGES : MAX_PAGES=int(MAX_PAGES)

    # ============= FIELDS =============
    UID = "uid"
    TITLE = "title_fr"
    DESC = "description_fr"
    LONG_DESC = "longdescription_fr"
    LOC_NAME = "location_name"
    LOC_DEPT = "location_department"
    LOC_CITY = "location_city"
    LOC_ADDRESS = "location_address"
    CONDITIONS = "conditions_fr"
    URL = "canonicalurl"
    LOC_COORD = "location_coordinates"
    LOC_LAT = "location_lat"
    LOC_LON = "location_lon"
    TIMINGS = "timings"
    FIRST_DATE = "first_date"
    
    
    SELECTED_FIELDS = [UID, TITLE, DESC, LONG_DESC, LOC_NAME, LOC_DEPT, LOC_CITY, LOC_ADDRESS, CONDITIONS, URL, TIMINGS, LOC_COORD ]
    REQUIRED_FIELDS = [UID, DESC, LOC_ADDRESS, TIMINGS]
    CHUNK_FIELDS = [TITLE, DESC, LONG_DESC, CONDITIONS, LOC_CITY, LOC_ADDRESS, LOC_DEPT]
    
    
    # ============= METHODS =============
    
    @classmethod
    def get_api_key(cls, provider:str=""):
        def get_api_key(cls, provider: str = "") -> str:
            """
            Retrieve the API key for the specified provider.
            Args:
                provider (str, optional): The name of the API provider. If not provided,
                    defaults to the configured LLM_PROVIDER. Defaults to "".
            Returns:
                str: The API key associated with the specified provider.
            Raises:
                KeyError: If the provider is not found in the API_KEYS dictionary.
            """

        if not provider: provider= cls.LLM_PROVIDER
        return cls.API_KEYS[provider] 
        # Get models from config

    @classmethod
    def get_chat_model(cls, provider:str=""):
        """
        Get the chat model for the specified LLM provider.
        Args:
            provider (str, optional): The name of the LLM provider. If not provided,
                defaults to the class's LLM_PROVIDER attribute.
        Returns:
            The chat model instance/configuration for the specified provider.
        Raises:
            KeyError: If the provider is not found in cls.LLM_MODELS.
        """

        if not provider: provider= cls.LLM_PROVIDER
        return cls.LLM_MODELS[provider]['chat']
    
    @classmethod
    def get_embed_model(cls, provider:str=""):
        def get_embed_model(cls, provider: str = "") -> Any:
            """
            Retrieve the embedding model for the specified provider.
            Args:
                provider (str, optional): The name of the LLM provider. 
                    If not provided, defaults to the configured LLM_PROVIDER. 
                    Defaults to "".
            Returns:
                Any: The embedding model associated with the specified provider.
            Raises:
                KeyError: If the provider is not found in LLM_MODELS.
            Example:
                >>> embed = get_embed_model("openai")
                >>> embed = get_embed_model()  # Uses default provider
            """

        if not provider: provider= cls.LLM_PROVIDER
        return cls.LLM_MODELS[provider]['embed']
    
    
    @classmethod
    def set_environment(cls, env: Environment) -> None:
        """
        Set the execution environment for the application.
        This class method updates the current environment configuration to the specified
        target environment and outputs a confirmation message.
            env (Environment): The target environment to set. Must be one of the
                Environment enum values: DEVELOPMENT, DEMO, or PRODUCTION.
        Returns:
            None
        Raises:
            TypeError: If env is not a valid Environment enum member.
        Example:
            >>> Config.set_environment(Environment.PRODUCTION)
            📌 Environment set to: PRODUCTION
        """
        cls.ENVIRONMENT = env
        print(f"📌 Environment set to: {env.value.upper()}")
    
    
    @classmethod
    def print_available_indexes(cls) -> None:
        """
        Display a formatted list of available FAISS index snapshots.
        Prints a table of all available index files in the indexes directory,
        including their snapshot dates, file sizes, and status markers.
        For each index, displays:
        - Sequential index number
        - Snapshot date (extracted from filename)
        - File size in megabytes
        - Status marker indicating if it's a development snapshot or the latest one
        If no indexes are found, prints a message indicating the pipeline needs to be run.
        Status markers:
        - "🔒 DEVELOPMENT (FROZEN)": Indicates the development snapshot
        - "⭐ LATEST": Indicates the most recent snapshot
        Args:
            cls: The class instance (used to access class attributes like INDEXES_DIR,
                 LLM_PROVIDER, ALL_LLM, and DEV_SNAPSHOT_DATE)
        Returns:
            None
        """
        
        print("\n" + "="*70)
        print("📚 AVAILABLE SNAPSHOTS")
        print("="*70)
        
        index_files = sorted(cls.INDEXES_DIR.glob("faiss_index_*.bin"))
        
        if not index_files:
            print("  ❌ No indexes found. Run pipeline first.")
            print("="*70 + "\n")
            return
        
        for idx, fpath in enumerate(index_files, 1):
            short_filename = fpath.stem
            embedder = cls.LLM_PROVIDER
            for llm in cls.ALL_LLM:
                new_stem = short_filename.replace(f"{llm}_","")
                if new_stem != short_filename:
                   short_filename = new_stem
                   embedder = llm
                   break 
            snapshot_date = fpath.stem.replace("faiss_index_", "")
            file_size_mb = fpath.stat().st_size / (1024 * 1024)
            
            # Check if this is development or latest
            markers = "[]"
            if snapshot_date == cls.DEV_SNAPSHOT_DATE:
                markers = "🔒 DEVELOPMENT (FROZEN)"
            if idx == len(index_files):
                markers="⭐ LATEST"
            
            print(f"  {idx}. {snapshot_date}  ({file_size_mb:.1f} MB)  {markers}")
        
        print("="*70 + "\n")
    
    @classmethod
    def get_available_index_dates(cls):
        """
        Retrieve metadata for all available FAISS index files in the indexes directory.
        This method scans the indexes directory for FAISS index binary files, extracts
        their metadata (snapshot date, file size, and embedder), and marks special indexes
        (latest and development).
        Returns:
            list: A list of dictionaries, each containing a snapshot date as key and a tuple
                  of (markers, file_size_mb, embedder) as value. The markers string indicates
                  special indexes:
                  - "⭐ LATEST": The most recently added index file
                  - "🔒 DEV": The development snapshot index
                  - "": No special marker for regular indexes
                  Returns an empty list if no index files are found.
        Example:
            >>> indexes = get_available_index_dates()
            >>> # Returns: [{'2024-01-15': ('⭐ LATEST', 125.5, 'openai')}, 
            >>>             {'2024-01-10': ('', 120.3, 'openai')}]
        """
        
        
        index_files = sorted(cls.INDEXES_DIR.glob("*_faiss_index_*.bin"))
        
        if not index_files:
            print("  ❌ No indexes found. Run pipeline first.")
            print("="*70 + "\n")
            return []
        
        result = []
        for idx, fpath in enumerate(index_files, 1):
            short_filename = fpath.stem
            embedder = cls.LLM_PROVIDER
            for llm in cls.ALL_LLM:
                new_stem = short_filename.replace(f"{llm}_","")
                if new_stem != short_filename:
                   short_filename = new_stem
                   embedder = llm
                   break 
            snapshot_date = short_filename.replace("faiss_index_", "")
            file_size_mb = fpath.stat().st_size / (1024 * 1024)
            
            # Check if this is development or latest
            markers = ""
            if idx == len(index_files):
                markers= "⭐ LATEST"
            if snapshot_date == cls.DEV_SNAPSHOT_DATE:
                markers= "🔒 DEV"
            
            result.append({snapshot_date: (markers,file_size_mb,embedder)})
        return result    
    
    @classmethod
    def get_raw_snapshot_path(cls, snapshot_date: str = "") -> str:
        """
        Generate the file path for a raw data snapshot JSON file.
        Args:
            snapshot_date (str, optional): The date of the snapshot in "YYYY-MM-DD" format.
                If not provided or empty string, defaults to the current date.
                Defaults to "".
        Returns:
            str: The full file path to the raw snapshot JSON file, formatted as
                "{RAW_DATA_DIR}/raw_snapshot_{snapshot_date}.json".
        Example:
            >>> path = get_raw_snapshot_path("2024-01-15")
            >>> # Returns: ".../raw_snapshot_2024-01-15.json"
        """
        
        if snapshot_date == "":
            snapshot_date = datetime.now().strftime("%Y-%m-%d")
        
        return str(cls.RAW_DATA_DIR / f"raw_snapshot_{snapshot_date}.json")
    
    @classmethod
    def get_processed_snapshot_path(cls, snapshot_date: str = "") -> str:
        """
        Generate the file path for the processed snapshot data.
        Args:
            snapshot_date (str, optional): The snapshot date in 'YYYY-MM-DD' format. 
                If empty string, defaults to today's date. Defaults to "".
        Returns:
            str: The full file path to the processed events JSON file.
        Example:
            >>> path = get_processed_snapshot_path("2023-12-25")
            >>> # Returns: '/path/to/processed_data/processed_events_2023-12-25.json'
        """
        
        if snapshot_date == "":
            snapshot_date = datetime.now().strftime("%Y-%m-%d")
        
        return str(cls.PROCESSED_DATA_DIR / f"processed_events_{snapshot_date}.json")
    
    @classmethod
    def get_index_path(cls, provider:str, snapshot_date: str = "") -> str:
        """
            Get the file path for a FAISS index file.
            Args:
                provider (str): The name of the data provider.
                snapshot_date (str, optional): The snapshot date in 'YYYY-MM-DD' format. 
                                              Defaults to the current date if not provided.
            Returns:
                str: The full file path to the FAISS index file with the format:
                     '{INDEXES_DIR}/{provider}_faiss_index_{snapshot_date}.bin'
            """
        
        if snapshot_date == "":
            snapshot_date = datetime.now().strftime("%Y-%m-%d")
        
        return str(cls.INDEXES_DIR / f"{provider}_faiss_index_{snapshot_date}.bin")
    
    @classmethod
    def get_metadata_path(cls, provider:str, snapshot_date: str = "") -> str:
        """
        Generate the file path for metadata JSON file based on provider and snapshot date.
        Args:
            provider (str): The name of the data provider.
            snapshot_date (str, optional): The snapshot date in "YYYY-MM-DD" format. 
                Defaults to current date if not provided.
        Returns:
            str: The full file path to the metadata JSON file in the format:
                "{INDEXES_DIR}/{provider}_metadata_{snapshot_date}.json"
        """
        
        if snapshot_date == "":
            snapshot_date = datetime.now().strftime("%Y-%m-%d")
        
        return str(cls.INDEXES_DIR / f"{provider}_metadata_{snapshot_date}.json")
    
    @classmethod
    def print_config(cls) -> None:
        """
        Display the current configuration settings to the console.
        Prints a formatted table showing:
        - Environment mode (upper case)
        - Region setting
        - Historical data period in days
        - Development snapshot date
        - Data directory path
        - Indexes directory path
        Output is formatted with decorative headers and padding for readability.
        """
        
        print("\n" + "="*70)
        print("⚙️  CONFIGURATION")
        print("="*70)
        print(f"Environment:          {cls.ENVIRONMENT.value.upper()}")
        print(f"Region:               {cls.REGION}")
        print(f"Historical period:    {cls.DAYS_BACK} days")
        print(f"Dev snapshot date:    {cls.DEV_SNAPSHOT_DATE}")
        print(f"Data directory:       {cls.DATA_DIR}")
        print(f"Indexes directory:    {cls.INDEXES_DIR}")
        print("="*70 + "\n")

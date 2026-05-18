# app/services/web_search_service.py
"""
Web search fallback service using smolagents and DuckDuckGoSearchTool.

Triggered when the hybrid Azure AI Search returns zero results.
Searches on a curated whitelist of French event websites to ensure
result relevance and avoid generic/unrelated content.

Dependencies:
    pip install smolagents
"""

import os
import logging
from datetime import datetime
from typing import Optional, AsyncGenerator

from smolagents import CodeAgent, DuckDuckGoSearchTool
from smolagents.models import LiteLLMModel

logger = logging.getLogger(__name__)

# ── Curated event website whitelist ───────────────────────────────────────────
# These sites are known to list French cultural events with structured data.
# The DuckDuckGo search is restricted to these domains for relevance.

EVENT_SITES = [
    "openagenda.com",
    "billetweb.fr",
    "eventbrite.fr",
    "fnacspectacles.com",
    "sortiraparis.com",
    "sortirtoulouse.com",
    "sortirabordeaux.com",
    "agendaculturel.fr",
    "tourisme.fr",
    "france.fr",
]

SITE_FILTER = " OR ".join([f"site:{s}" for s in EVENT_SITES])


class WebSearchService:
    """
    Fallback web search service for event discovery using smolagents.

    Uses DuckDuckGoSearchTool restricted to a curated whitelist of French
    event websites. Called only when the primary Azure AI Search index
    returns zero validated results.
    """

    def __init__(self):
        """
        Initialises the smolagents CodeAgent with DuckDuckGo search tool
        and Azure OpenAI as the reasoning model.
        """
        # Use Azure OpenAI via LiteLLM for consistency with the rest of the app
        model = LiteLLMModel(
            model_id=f"azure/{os.getenv('AZURE_OPENAI_DEPLOYMENT', 'gpt-4o')}",
            api_base=os.getenv("AZURE_OPENAI_ENDPOINT", ""),
            api_key=os.getenv("AZURE_OPENAI_API_KEY", ""),
            api_version=os.getenv("AZURE_OPENAI_API_VERSION", "2024-02-15-preview"),
        )

        self.agent = CodeAgent(
            tools=[DuckDuckGoSearchTool()],
            model=model,
            max_steps=3,        # Limit agent reasoning steps for latency
            verbosity_level=0,  # Suppress internal logs
        )
        logger.info("WebSearchService initialised with DuckDuckGo + Azure OpenAI")

    def search_events(
        self,
        city: Optional[str],
        dept: Optional[str],
        target_date: datetime,
        tolerance: int,
        user_query: str,
    ) -> str:
        """
        Searches for events on curated French event websites using smolagents.

        Builds a structured prompt that constrains the agent to:
          - Search only on whitelisted event sites
          - Focus on the specified geographic area
          - Filter for the requested date window
          - Return structured results (title, date, location, URL)

        Args:
            city        (str|None): Normalized city name from QueryParser.
            dept        (str|None): Normalized department name from QueryParser.
            target_date (datetime): Reference date for the event search.
            tolerance   (int)     : Number of days after target_date to include.
            user_query  (str)     : Original user question for context.

        Returns:
            str: Agent response with formatted event results, or an error message.
        """
        geo=[]
        if city:
            geo.append(f" in city of {city}")
        if dept:
            geo.append(f" in department of {dept}")
        if not geo:
            geo.append(" in France")
        
        geo_txt = " and".join(geo)

        date_str   = target_date.strftime("%d/%m/%Y")
        end_date   = target_date
        # Compute end date for the tolerance window
        from datetime import timedelta
        end_date_str = (target_date + timedelta(days=tolerance)).strftime("%d/%m/%Y")

        prompt = (
            f"Search for cultural events in '{geo_txt}' between {date_str} and {end_date_str}. "
            f"User question context: '{user_query}'\n\n"
            f"Search ONLY on these websites: {SITE_FILTER}\n\n"
            f"For each event found, provide:\n"
            f"- Event title\n"
            f"- Date and time\n"
            f"- Location (venue name and address)\n"
            f"- Brief description (1-2 sentences)\n"
            f"- URL\n\n"
            f"Return results in French. If no events are found, say so clearly. "
            f"List at most 5 events."
        )

        try:
            logger.info(f"WebSearchService: searching events in '{geo}' around {date_str}")
            result = self.agent.run(prompt)
            logger.info("WebSearchService: search completed successfully")
            return str(result)
        except Exception as e:
            logger.error(f"WebSearchService search failed: {e}")
            return ""
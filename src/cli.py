# main.py
import argparse
import logging
from datetime import datetime
from src.rag.searchbot import SearchBot
from src.utils.token_accounting import get_accounting
from src.utils.utils import flat_date_constraints
from src.config import Config

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

def search_cli(question: str, top_k: int = 5, snapshot_date: str = ""):
    """CLI search command"""
    try:
        engine = SearchBot(embedder= Config.LLM_PROVIDER, snapshot_date=snapshot_date)
        result = engine.answer_question(question=question, top_k=top_k)
        
        print("\n" + "="*80)
        print("❓ QUESTION")
        print("="*80)
        print(question)
        
        print("\n" + "="*80)
        print("💬 ANSWER")
        print("="*80)
        print(result['answer'])
        
        if result['constraints']['date']:
            print(f"\n📅 Date: {flat_date_constraints(result['constraints']['date'])}")
        if result['constraints']['city']:
            print(f"🏙️ City: {result['constraints']['city']}")
        
        print("\n" + "="*80)
        print(f"📍 SOURCES ({len(result['sources'])} found)")
        print("="*80)
        
        for i, source in enumerate(result['sources'], 1):
            print(f"\n{i}. {source['title']}")
            print(f"   📍 {source['city']}")
            print(f"   📅 {source['dates']}")
            if source['distance']:
                print(f"   ⭐ Relevance: {int(source['distance']*100)}%")
            print(f"   🔗 {source['url']}")
        
       # Afficher rapport tokens
        #get_accounting().print_report()
        
        print(f"\n⏱️ Execution time: {result['execution_time']:.3f}s")
        print("="*80 + "\n")
    
    except Exception as e:
        logger.error(f"Error: {e}")
        exit(1)

def info():
    """Show info about available commands"""
    print("""
RAG Events - Command Line Interface

Commands:
  search    Search for events
  api       Start HTTP API server
  info      Show this help

Examples:
  python main.py search -q "Quels événements ce soir ?"
  python main.py search -q "Concerts" -d 2026-01-30 -k 10
  python main.py api
  python main.py api -p 3000

Options:
  -q, --question    Question to ask
  -d, --date        Snapshot date (YYYY-MM-DD)
  -k, --top-k       Number of results (default: 5)
  -p, --port        API port (default: 8000)
  -h, --host        API host (default: 0.0.0.0)
    """)

def main():
    parser = argparse.ArgumentParser(description="RAG Events System")
    subparsers = parser.add_subparsers(dest="command", help="Command to run")
    
    # Search command
    search_parser = subparsers.add_parser("search", help="Search for events")
    search_parser.add_argument("-q", "--question", required=True, help="Question")
    search_parser.add_argument("-d", "--date", default= Config.DEV_SNAPSHOT_DATE, help="Snapshot date (YYYY-MM-DD)")
    search_parser.add_argument("-k", "--top-k", type=int, default=5, help="Top K results")
    
    # API command
    api_parser = subparsers.add_parser("api", help="Start API server")
    api_parser.add_argument("-p", "--port", type=int, default=8000, help="Port")
    api_parser.add_argument("--host", default="0.0.0.0", help="Host")
    
    # Info command
    subparsers.add_parser("info", help="Show help")
    
    # Dans la fonction main(), ajouter :
    chat_parser = subparsers.add_parser('chat', help='Start interactive chatbot')
    chat_parser.add_argument('-d', '--date', default=Config.DEV_SNAPSHOT_DATE, 
                            help='Snapshot date YYYY-MM-DD')


    args = parser.parse_args()
    
    if args.command == "search":
        search_cli(question=args.question, top_k=args.top_k, snapshot_date=args.date)
    else:
        info()

if __name__ == "__main__":
    main()

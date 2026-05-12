import argparse
import logging
from dotenv import load_dotenv
from app.services.storage.user_storage import UserStorageService

# Configuration du logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("create_users")

def main():
    # 1. Chargement des variables d'environnement (.env)
    load_dotenv()

    # 2. Configuration du parseur d'arguments
    parser = argparse.ArgumentParser(description="Création d'un utilisateur Puls-Events dans Cosmos DB")
    
    parser.add_argument("-u", "--username", required=True, help="Nom d'utilisateur (ID unique)")
    parser.add_argument("-p", "--password", required=True, help="Mot de passe de l'utilisateur")
    parser.add_argument("-r", "--role", default="user", help="Rôle de l'utilisateur (default: user)")

    args = parser.parse_args()

    # 3. Initialisation du service
    try:
        service = UserStorageService()
        
        # Préparation des métadonnées minimales (le rôle)
        # Les réglages UI (ville, rayon) seront gérés par SettingsStorageService
        user_metadata = {"role": args.role}
        if args.role == 'guest':
            user_metadata['daily_token_limit'] = 10000
            user_metadata['max_questions_per_day'] = 5
            

        # 4. Création/Mise à jour de l'utilisateur
        service.create_user(
            username=args.username, 
            password=args.password, 
            metadata=user_metadata
        )
        
        print(f"🚀 Succès : L'utilisateur '{args.username}' a été créé/mis à jour avec le rôle '{args.role}'.")

    except Exception as e:
        logger.error(f"Échec de la création de l'utilisateur : {e}")

if __name__ == "__main__":
    main()
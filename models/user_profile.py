import asyncpg
from datetime import datetime

class UserProfile:
    """Représente le profil d'un utilisateur."""

    def __init__(self, username, db_connection, discord_name=None, last_connection=None):
        self.username = username
        self.db_connection = db_connection
        self.game_name = None
        self.langue = None
        self.localisation = None
        self.latitude = None
        self.longitude = None
        self.discord_name = discord_name
        self.last_connection = last_connection

    @classmethod
    async def get_or_create_user(cls, username, db_connection, member=None):
        print(f"🔍 Vérification du profil pour {username}")

        # Vérifier si l'utilisateur existe dans la base
        query = """
        SELECT username, discord_name, last_connection FROM user_profile WHERE username = $1
        """
        existing_user = await db_connection.fetchrow(query, username)

        if existing_user:
            print(f"✅ Profil déjà existant pour {username}")
            # Vérifier si le nom d'affichage a changé
            if member and existing_user['discord_name'] != member.display_name:
                # Mettre à jour le nom d'affichage dans la base de données
                update_query = """
                UPDATE user_profile
                SET discord_name = $1
                WHERE username = $2
                """
                await db_connection.execute(update_query, member.display_name, username)
                print(f"✅ Nom d'affichage mis à jour pour {username}")

                # Créer une copie mutable de existing_user
                existing_user = dict(existing_user)
                existing_user['discord_name'] = member.display_name

            return cls(username, db_connection, existing_user['discord_name'], existing_user['last_connection'])  # Retourne le profil sans le recréer

        # Si l'utilisateur n'existe pas, on le crée
        query = """
        INSERT INTO user_profile (username, discord_name, last_connection)
        VALUES ($1, $2, $3)
        """
        await db_connection.execute(query, username, member.display_name if member else None, datetime.now())
        print(f"✅ Nouvel utilisateur ajouté : {username}")

        # Envoie un message privé à l'utilisateur
        if member:
            try:
                await member.send(f"👋 Bonjour {username} ! Ton profil a été créé avec succès dans la base de données.")
                print(f"📩 Message envoyé à {username}")
            except Exception as e:
                print(f"❌ Erreur lors de l'envoi du message à {username}: {e}")

        return cls(username, db_connection, member.display_name if member else None, datetime.now())

    async def load_from_db(self):
        """Charge les informations de l'utilisateur depuis la base de données."""
        query = """
        SELECT game_name, langue, localisation, latitude, longitude, discord_name, last_connection
        FROM user_profile
        WHERE username = $1
        """
        try:
            result = await self.db_connection.fetchrow(query, self.username)
            if result:
                self.game_name = result["game_name"]
                self.langue = result["langue"]
                self.localisation = result["localisation"]
                self.latitude = result["latitude"]
                self.longitude = result["longitude"]
                self.discord_name = result["discord_name"]
                self.last_connection = result["last_connection"]
        except Exception as e:
            print(f"Erreur lors du chargement du profil utilisateur depuis la base de données : {e}")

    async def create_in_db(self):
        """Crée un nouveau profil utilisateur dans la base de données."""
        query = """
        INSERT INTO user_profile (username)
        VALUES ($1)
        """
        try:
            await self.db_connection.execute(query, self.username)
            print(f"Nouvel utilisateur ajouté : {self.username}")
        except Exception as e:
            print(f"Erreur lors de l'insertion de l'utilisateur : {e}")

    async def save(self):
        """Enregistre les modifications de l'utilisateur dans la base de données."""
        query = """
        UPDATE user_profile
        SET discord_name = $1, last_connection = $2
        WHERE username = $3;
        """
        try:
            await self.db_connection.execute(query, self.discord_name, self.last_connection, self.username)
            print(f"Profil mis à jour pour {self.username}")
        except Exception as e:
            print(f"Erreur lors de la mise à jour du profil utilisateur : {e}")

    def __str__(self):
        """Représentation en chaîne du profil utilisateur."""
        return (f"UserProfile(username={self.username}, game_name={self.game_name}, "
                f"langue={self.langue}, localisation={self.localisation}, "
                f"latitude={self.latitude}, longitude={self.longitude}, "
                f"discord_name={self.discord_name}, last_connection={self.last_connection})")

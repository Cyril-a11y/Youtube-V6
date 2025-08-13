"""
Script pour uploader la miniature PNG sur YouTube.

⚠️ Actuellement désactivé.
Pour l’activer :
1. Décommente le bloc de code principal
2. Assure-toi que ton fichier .env contient les infos YouTube OAuth2
3. Ajoute les dépendances nécessaires : google-api-python-client, google-auth-oauthlib
"""

# import os
# from google.oauth2.credentials import Credentials
# from googleapiclient.discovery import build
# from config import YOUTUBE_VIDEO_ID, YOUTUBE_CLIENT_ID, YOUTUBE_CLIENT_SECRET, YOUTUBE_REFRESH_TOKEN, THUMBNAIL_PNG

# def upload_thumbnail():
#     if not os.path.exists(THUMBNAIL_PNG):
#         print(f"❌ Miniature PNG introuvable : {THUMBNAIL_PNG}")
#         return

#     creds = Credentials(
#         None,
#         refresh_token=YOUTUBE_REFRESH_TOKEN,
#         token_uri="https://oauth2.googleapis.com/token",
#         client_id=YOUTUBE_CLIENT_ID,
#         client_secret=YOUTUBE_CLIENT_SECRET,
#         scopes=["https://www.googleapis.com/auth/youtube.upload"]
#     )

#     youtube = build("youtube", "v3", credentials=creds)

#     request = youtube.thumbnails().set(
#         videoId=YOUTUBE_VIDEO_ID,
#         media_body=THUMBNAIL_PNG
#     )
#     response = request.execute()
#     print(f"✅ Miniature mise à jour : {response}")

if __name__ == "__main__":
    print("🚫 Upload miniature désactivé. Décommente le code pour l'activer.")

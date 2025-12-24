import cv2
import pytesseract
from PIL import Image
import json
import re
import os
import numpy as np

# Définir le chemin vers l'exécutable Tesseract
pytesseract.pytesseract.tesseract_cmd = r'/usr/local/bin/tesseract'  # Remplacez par le chemin correct vers Tesseract

def process_image(image_path, del_image=True):
    try:
        # Créer le dossier temporaire s'il n'existe pas
        temp_dir = "temp"
        if not os.path.exists(temp_dir):
            os.makedirs(temp_dir)

        # Déplacer l'image dans le dossier temporaire avec un préfixe
        base_name = os.path.basename(image_path)
        new_image_path = os.path.join(temp_dir, f"template_{base_name}")
        os.rename(image_path, new_image_path)
        print("image_path :", new_image_path)

        # Charger l'image avec OpenCV
        image = cv2.imread(new_image_path)

        # Convertir l'image en niveaux de gris
        gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)



        # Appliquer un flou pour réduire le bruit
        blurred = cv2.GaussianBlur(gray, (5, 5), 0)

        # Appliquer un seuillage pour améliorer le contraste
        _, thresh = cv2.threshold(blurred, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)

        # Convertir l'image OpenCV en image PIL
        image_pil = Image.fromarray(thresh)

        # Utiliser Tesseract pour extraire le texte
        extracted_text = pytesseract.image_to_string(image_pil, lang="eng")

        # Afficher le texte extrait pour analyse
        print("Texte extrait:")
        print(extracted_text)

        # Extraire le nom du personnage
        nom_match = re.search(r'([A-Za-z]+) - \d+', extracted_text)
        nom = nom_match.group(1) if nom_match else ""

        # Extraire les valeurs numériques des statistiques
        points_match = re.search(r'([A-Za-z]+) - (\d+)', extracted_text)
        points = points_match.group(2) if points_match else ""

        stats = {
            "Nom": nom,
            "Puissance Globale": re.search(r'PUISSANCE GLOBALE\s+(\d+)', extracted_text),
            "Agilité": re.search(r'AGILITE\s+(\d+)', extracted_text),
            "Endurance": re.search(r'ENDURANCE\s+(\d+)', extracted_text),
            "Service": re.search(r'SERVICE\s+(\d+)', extracted_text),
            "Volée": re.search(r'VOLEE\s+(\d+)', extracted_text),
            "Coup Droit": re.search(r'COUP DROIT\s+(\d+)', extracted_text),
            "Revers": re.search(r'REVERS\s+(\d+)', extracted_text)
        }

        # Corriger les valeurs numériques des statistiques
        for key, match in stats.items():
            if match:
                stats[key] = match.group(1)
            else:
                stats[key] = ""

        # Vérifier que toutes les valeurs nécessaires sont présentes
        if not all(stats.values()):
            print("Erreur : Certaines valeurs nécessaires n'ont pas été extraites.")
            return None

        # Construire les données JSON
        character_data = {
            "personnage": {
                "Nom": stats["Nom"],
                "Puissance Globale": stats["Puissance Globale"],
                "points": points,
                "Agilité": stats["Agilité"],
                "Endurance": stats["Endurance"],
                "Service": stats["Service"],
                "Volée": stats["Volée"],
                "Coup Droit": stats["Coup Droit"],
                "Revers": stats["Revers"]
            }
        }

        # Supprimer l'image si demandé
        if del_image and os.path.exists(new_image_path):
            os.remove(new_image_path)

        # Enregistrer les données au format JSON
        json_path = os.path.join(temp_dir, "personnage.json")  # Définir le chemin du fichier JSON
        with open(json_path, "w", encoding="utf-8") as json_file:
            json.dump(character_data, json_file, indent=4, ensure_ascii=False)

        print(f"Fichier JSON généré : {json_path}")
        return json_path

    except Exception as e:
        print(f"Erreur lors du traitement de l'image : {e}")
        return None

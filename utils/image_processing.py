"""
Module de traitement d'images pour l'OCR.

Les dépendances lourdes (OpenCV, Pillow, pytesseract) sont chargées
en lazy loading pour accélérer le démarrage du bot.
"""

import json
import re
import os
from pathlib import Path

from config import TEMP_DIR
from utils.logger import get_logger

logger = get_logger("utils.image_processing")

# =============================================================================
# Lazy loading des dépendances lourdes
# =============================================================================
_cv2 = None
_pytesseract = None
_np = None


def _get_cv2():
    """Charge OpenCV en lazy loading."""
    global _cv2
    if _cv2 is None:
        try:
            import cv2
            _cv2 = cv2
        except ImportError:
            raise ImportError(
                "opencv-python-headless n'est pas installé. "
                "Installez-le avec: pip install opencv-python-headless"
            )
    return _cv2


def _get_pytesseract():
    """Charge pytesseract en lazy loading."""
    global _pytesseract
    if _pytesseract is None:
        try:
            import pytesseract
            _pytesseract = pytesseract
        except ImportError:
            raise ImportError(
                "pytesseract n'est pas installé. "
                "Installez-le avec: pip install pytesseract"
            )
    return _pytesseract


def _get_numpy():
    """Charge numpy en lazy loading."""
    global _np
    if _np is None:
        try:
            import numpy as np
            _np = np
        except ImportError:
            raise ImportError(
                "numpy n'est pas installé. "
                "Installez-le avec: pip install numpy"
            )
    return _np

def preprocess_image(image):
    """Prétraite l'image pour améliorer la reconnaissance de texte.

    Args:
        image: Image numpy array (BGR)

    Returns:
        Image binaire prétraitée
    """
    cv2 = _get_cv2()

    try:
        # Log des dimensions de l'image
        logger.debug(f"Dimensions de l'image: {image.shape}")

        # Convertir en niveaux de gris
        gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)

        # Redimensionner si l'image est trop grande
        height, width = gray.shape
        if height > 1000:
            scale = 1000 / height
            new_width = int(width * scale)
            gray = cv2.resize(gray, (new_width, 1000))
            logger.debug(f"Image redimensionnée à: {gray.shape}")

        # Améliorer le contraste
        clahe = cv2.createCLAHE(clipLimit=3.0, tileGridSize=(8, 8))
        gray = clahe.apply(gray)

        # Binarisation adaptative
        binary = cv2.adaptiveThreshold(
            gray,
            255,
            cv2.ADAPTIVE_THRESH_GAUSSIAN_C,
            cv2.THRESH_BINARY,
            21,  # Augmenté pour mieux gérer le texte
            11
        )

        return binary

    except Exception as e:
        logger.error(f"Erreur lors du prétraitement: {str(e)}")
        raise

def extract_text_with_debug(image) -> str:
    """Extrait le texte avec plusieurs tentatives et configurations.

    Args:
        image: Image numpy array prétraitée

    Returns:
        Texte extrait de l'image
    """
    pytesseract = _get_pytesseract()

    configs = [
        '--oem 3 --psm 6',  # Configuration par défaut
        '--oem 3 --psm 4',  # Page segmentée comme du texte simple
        '--oem 3 --psm 3',  # Page complète
    ]

    best_text = ""
    max_numbers = 0

    for config in configs:
        try:
            text = pytesseract.image_to_string(image, lang='eng', config=config)
            logger.debug(f"Texte extrait avec config {config}:")
            logger.debug(text)

            # Compter le nombre de chiffres trouvés
            numbers_found = len(re.findall(r'\d+', text))
            if numbers_found > max_numbers:
                max_numbers = numbers_found
                best_text = text

        except Exception as e:
            logger.error(f"Erreur avec config {config}: {str(e)}")
            continue

    return best_text

def process_image(image_path: str, del_image: bool = True) -> str:
    """Traite une image pour en extraire les informations du personnage.

    Args:
        image_path: Chemin vers l'image à traiter
        del_image: Si True, supprime l'image après traitement

    Returns:
        Chemin vers le fichier JSON généré
    """
    cv2 = _get_cv2()

    try:
        # Vérification du chemin de l'image
        if not os.path.exists(image_path):
            raise FileNotFoundError(f"Image non trouvée: {image_path}")

        logger.info(f"Traitement de l'image: {image_path}")

        # Lecture de l'image
        image = cv2.imread(image_path)
        if image is None:
            raise ValueError("Impossible de lire l'image")

        # Prétraitement
        processed = preprocess_image(image)

        # Sauvegarde de l'image prétraitée pour debug
        debug_path = TEMP_DIR / "debug_processed.png"
        cv2.imwrite(str(debug_path), processed)
        logger.debug(f"Image prétraitée sauvegardée: {debug_path}")

        # Extraction du texte
        extracted_text = extract_text_with_debug(processed)

        # Patterns de recherche avec plus de flexibilité
        patterns = {
            'nom': r'([A-Za-z]+)\s*-\s*(\d+)',
            'puissance': r'(?:PUISSANCE|PUIS\.?)\s*GLOBALE\s*(\d+)',
            'agilite': r'(?:AGILIT[EÉ]|AGI\.?)\s*(\d+)',
            'endurance': r'(?:ENDURANCE|END\.?)\s*(\d+)',
            'service': r'(?:SERVICE|SER\.?)\s*(\d+)',
            'volee': r'(?:VOL[EÉ]E|VOL\.?)\s*(\d+)',
            'coup_droit': r'(?:COUP\s*DROIT|CD\.?)\s*(\d+)',
            'revers': r'(?:REVERS|REV\.?)\s*(\d+)'
        }

        # Extraction avec log
        matches = {}
        for key, pattern in patterns.items():
            match = re.search(pattern, extracted_text, re.IGNORECASE)
            matches[key] = match
            logger.debug(f"Recherche {key}: {'Trouvé' if match else 'Non trouvé'}")
            if match:
                logger.debug(f"Valeur trouvée: {match.group(1)}")

        # Construction des données
        character_data = {
            "personnage": {
                "Nom": matches['nom'].group(1) if matches['nom'] else "",
                "Puissance Globale": matches['puissance'].group(1) if matches['puissance'] else "",
                "points": matches['nom'].group(2) if matches['nom'] else "",
                "Agilité": matches['agilite'].group(1) if matches['agilite'] else "",
                "Endurance": matches['endurance'].group(1) if matches['endurance'] else "",
                "Service": matches['service'].group(1) if matches['service'] else "",
                "Volée": matches['volee'].group(1) if matches['volee'] else "",
                "Coup Droit": matches['coup_droit'].group(1) if matches['coup_droit'] else "",
                "Revers": matches['revers'].group(1) if matches['revers'] else ""
            }
        }

        # Log des données extraites
        logger.debug("Données extraites:")
        logger.debug(json.dumps(character_data, indent=2))

        # Vérification des données
        missing_fields = [k for k, v in character_data["personnage"].items() if not v]
        if missing_fields:
            logger.error(f"Champs manquants: {missing_fields}")
            raise ValueError(f"Données manquantes: {', '.join(missing_fields)}")

        # Sauvegarde JSON
        json_path = TEMP_DIR / "personnage.json"
        with open(json_path, "w", encoding="utf-8") as json_file:
            json.dump(character_data, json_file, indent=4, ensure_ascii=False)

        logger.info(f"Fichier JSON créé: {json_path}")

        # Nettoyage si demandé
        if del_image and os.path.exists(image_path):
            os.remove(image_path)
            logger.debug(f"Image originale supprimée: {image_path}")

        return str(json_path)

    except Exception as e:
        logger.error(f"Erreur lors du traitement: {str(e)}", exc_info=True)
        # Ne pas lever l'exception, retourner un chemin par défaut
        return str(TEMP_DIR / "error.json")

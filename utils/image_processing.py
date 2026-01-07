"""
Module de traitement d'images pour l'OCR Tennis Clash.

Les dependances lourdes (OpenCV, Pillow, pytesseract) sont chargees
en lazy loading pour accelerer le demarrage du bot.
Thread-safe grace a un Lock.

Strategies d'extraction:
1. Detection du cadre blanc des stats (region fixe)
2. Extraction ligne par ligne avec preprocessing agressif
3. OCR cible avec whitelist de chiffres
"""

import json
import re
import os
import threading
from dataclasses import dataclass
from pathlib import Path
from typing import Optional, Dict, Tuple

from config import TEMP_DIR
from utils.logger import get_logger

logger = get_logger("utils.image_processing")

# =============================================================================
# Lazy loading des dépendances lourdes (thread-safe)
# =============================================================================
_cv2 = None
_pytesseract = None
_np = None
_import_lock = threading.Lock()


def _get_cv2():
    """Charge OpenCV en lazy loading (thread-safe)."""
    global _cv2
    if _cv2 is None:
        with _import_lock:
            if _cv2 is None:  # Double-check après acquisition du lock
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
    """Charge pytesseract en lazy loading (thread-safe)."""
    global _pytesseract
    if _pytesseract is None:
        with _import_lock:
            if _pytesseract is None:  # Double-check après acquisition du lock
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
    """Charge numpy en lazy loading (thread-safe)."""
    global _np
    if _np is None:
        with _import_lock:
            if _np is None:  # Double-check après acquisition du lock
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

    Utilise les reglages optimises pour Tennis Clash:
    - Luminosite tres basse (-127)
    - Contraste eleve (x2)

    Args:
        image: Image numpy array (BGR)

    Returns:
        Image preprocessee pour OCR
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

        # Reglages optimises pour Tennis Clash (trouves via GIMP)
        # Luminosite = -127, Contraste = 84 (equiv alpha=2.0)
        adjusted = cv2.convertScaleAbs(gray, alpha=2.0, beta=-127)

        # Binarisation avec seuil d'Otsu pour nettoyer
        _, binary = cv2.threshold(adjusted, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)

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


# =============================================================================
# Extraction optimisee pour Tennis Clash (v2)
# =============================================================================

@dataclass
class ExtractedEquipment:
    """Un equipement extrait d'une capture."""
    slot: int                       # 1-6
    card_name: Optional[str] = None
    card_level: Optional[int] = None


@dataclass
class ExtractedStats:
    """Donnees extraites d'une capture Tennis Clash."""
    character_name: Optional[str] = None
    points: Optional[int] = None
    global_power: Optional[int] = None
    agility: Optional[int] = None
    endurance: Optional[int] = None
    serve: Optional[int] = None
    volley: Optional[int] = None
    forehand: Optional[int] = None
    backhand: Optional[int] = None
    equipment: list = None          # Liste de ExtractedEquipment
    confidence: float = 0.0         # Score de confiance 0-1
    warnings: list = None

    def __post_init__(self):
        if self.warnings is None:
            self.warnings = []
        if self.equipment is None:
            self.equipment = []

    def is_valid(self) -> bool:
        """Verifie si les donnees essentielles sont presentes."""
        return (
            self.character_name is not None and
            self.global_power is not None and
            self.confidence >= 0.5
        )

    def to_dict(self) -> dict:
        """Convertit en dictionnaire pour affichage."""
        return {
            "Personnage": self.character_name or "?",
            "Points": self.points,
            "Puissance Globale": self.global_power,
            "Agilite": self.agility,
            "Endurance": self.endurance,
            "Service": self.serve,
            "Volee": self.volley,
            "Coup Droit": self.forehand,
            "Revers": self.backhand,
        }


def _find_stats_box(image) -> Optional[Tuple[int, int, int, int]]:
    """Detecte le cadre blanc des statistiques.

    Le cadre est caracterise par:
    - Fond blanc/clair
    - Position sur la droite de l'image
    - Contient le texte PUISSANCE GLOBALE

    Returns:
        Tuple (x, y, w, h) de la region ou None si non trouve
    """
    cv2 = _get_cv2()
    np = _get_numpy()

    height, width = image.shape[:2]

    # Le cadre des stats est toujours dans la moitie droite
    right_half = image[:, width // 2:]

    # Convertir en HSV pour detecter le blanc
    hsv = cv2.cvtColor(right_half, cv2.COLOR_BGR2HSV)

    # Masque pour le blanc (saturation faible, luminosite haute)
    lower_white = np.array([0, 0, 200])
    upper_white = np.array([180, 30, 255])
    mask = cv2.inRange(hsv, lower_white, upper_white)

    # Trouver les contours
    contours, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)

    # Chercher le plus grand rectangle blanc
    best_box = None
    best_area = 0

    for contour in contours:
        x, y, w, h = cv2.boundingRect(contour)
        area = w * h

        # Le cadre doit etre significatif et plus haut que large
        if area > best_area and h > w * 0.5 and area > (height * width * 0.02):
            best_area = area
            # Ajuster x pour la position absolue (on etait sur la moitie droite)
            best_box = (x + width // 2, y, w, h)

    return best_box


def _extract_number_from_region(image, region: Tuple[int, int, int, int]) -> Optional[int]:
    """Extrait un nombre d'une region specifique.

    Args:
        image: Image complete
        region: Tuple (x, y, w, h)

    Returns:
        Nombre extrait ou None
    """
    cv2 = _get_cv2()
    pytesseract = _get_pytesseract()

    x, y, w, h = region
    crop = image[y:y+h, x:x+w]

    # Convertir en niveaux de gris
    gray = cv2.cvtColor(crop, cv2.COLOR_BGR2GRAY)

    # Binarisation avec seuil d'Otsu (adaptatif)
    _, binary = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)

    # Inverser si le texte est clair sur fond sombre
    if binary.mean() > 127:
        binary = cv2.bitwise_not(binary)

    # OCR avec whitelist de chiffres uniquement
    config = '--oem 3 --psm 7 -c tessedit_char_whitelist=0123456789'
    try:
        text = pytesseract.image_to_string(binary, config=config).strip()
        if text and text.isdigit():
            return int(text)
    except Exception as e:
        logger.debug(f"OCR region failed: {e}")

    return None


def _extract_text_from_region(image, region: Tuple[int, int, int, int]) -> Optional[str]:
    """Extrait du texte d'une region specifique.

    Args:
        image: Image complete
        region: Tuple (x, y, w, h)

    Returns:
        Texte extrait ou None
    """
    cv2 = _get_cv2()
    pytesseract = _get_pytesseract()

    x, y, w, h = region
    crop = image[y:y+h, x:x+w]

    # Convertir en niveaux de gris
    gray = cv2.cvtColor(crop, cv2.COLOR_BGR2GRAY)

    # Ameliorer le contraste
    clahe = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8, 8))
    gray = clahe.apply(gray)

    # Binarisation
    _, binary = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)

    # OCR
    config = '--oem 3 --psm 7'
    try:
        text = pytesseract.image_to_string(binary, config=config).strip()
        return text if text else None
    except Exception as e:
        logger.debug(f"OCR text region failed: {e}")

    return None


def _preprocess_for_stats(image):
    """Preprocessing optimise pour les stats (nom perso + attributs).

    Reglages: luminosite=-127, contraste=2.0
    """
    cv2 = _get_cv2()
    gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
    adjusted = cv2.convertScaleAbs(gray, alpha=2.0, beta=-127)
    _, binary = cv2.threshold(adjusted, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
    return binary


def _preprocess_for_card_names(image):
    """Preprocessing optimise pour les noms de cartes.

    Reglages: luminosite=54, contraste=2.5
    """
    cv2 = _get_cv2()
    gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
    adjusted = cv2.convertScaleAbs(gray, alpha=2.5, beta=54)
    _, binary = cv2.threshold(adjusted, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
    return binary


def _preprocess_for_card_levels(image):
    """Preprocessing optimise pour les niveaux de cartes.

    Reglages: luminosite=0, contraste=1.5 (initial)
    """
    cv2 = _get_cv2()
    gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
    adjusted = cv2.convertScaleAbs(gray, alpha=1.5, beta=0)
    _, binary = cv2.threshold(adjusted, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
    return binary


def extract_stats_v2(image_path: str) -> ExtractedStats:
    """Extrait les statistiques d'une capture Tennis Clash (methode optimisee).

    Utilise une approche multi-pass:
    1. Pass stats: nom perso + 6 attributs (luminosite=-127, contraste=2.0)
    2. Pass card names: noms des 6 cartes (luminosite=54, contraste=2.5)
    3. Pass card levels: niveaux des 6 cartes (luminosite=0, contraste=1.5)

    Args:
        image_path: Chemin vers l'image

    Returns:
        ExtractedStats avec les donnees extraites et score de confiance
    """
    cv2 = _get_cv2()
    pytesseract = _get_pytesseract()

    result = ExtractedStats()

    if not os.path.exists(image_path):
        result.warnings.append("Image non trouvee")
        return result

    try:
        # Lire l'image
        image = cv2.imread(image_path)
        if image is None:
            result.warnings.append("Impossible de lire l'image")
            return result

        height, width = image.shape[:2]
        logger.debug(f"Image: {width}x{height}")

        # =====================================================================
        # PASS 1: Stats (nom perso + attributs)
        # =====================================================================
        processed_stats = _preprocess_for_stats(image)
        text_stats = extract_text_with_debug(processed_stats)
        logger.debug(f"Pass 1 (stats):\n{text_stats[:500]}...")

        found_count = 0

        # Nom et points: "Mei-Li • 1770" ou "Mei-Li - 1770"
        name_pattern = r'([A-Za-z][A-Za-z\-\.]+(?:\s+[A-Za-z]+)?)\s*[\-•·]\s*(\d{3,4})'
        name_match = re.search(name_pattern, text_stats)
        if name_match:
            result.character_name = name_match.group(1).strip()
            result.points = int(name_match.group(2))
            found_count += 2
        else:
            # Essayer juste le nom
            name_only = re.search(r'([A-Z][a-z]+(?:[- ][A-Z][a-z]+)?)\s*[\-•·]', text_stats)
            if name_only:
                result.character_name = name_only.group(1).strip()
                found_count += 1
                result.warnings.append("Points non detectes")

        # Stats patterns (plus flexibles - OCR peut mal lire certains caracteres)
        stat_patterns = {
            'global_power': r'(?:PUISSANCE\s*GLOBALE|PUIS[.\s]*GLOB)[^\d]*(\d{2,3})',
            'agility': r'(?:AGILIT[EÉ]|AGI)[^\d]*(\d{2,3})',
            'endurance': r'(?:ENDUR(?:ANCE)?|END(?:UR)?)[^\d]*(\d{2,3})',
            'serve': r'(?:SERVICE|SERV)[^\d]*(\d{2,3})',
            'volley': r'(?:VOL[EÉ]E|VOL)[^\d]*(\d{2,3})',
            'forehand': r'(?:COUP\s*DROIT|CD)[^\d]*(\d{2,3})',
            'backhand': r'(?:REVERS|REV)[^\d]*(\d{2,3})',
        }

        for attr, pattern in stat_patterns.items():
            match = re.search(pattern, text_stats, re.IGNORECASE)
            if match:
                value = int(match.group(1))
                if 1 <= value <= 999:
                    setattr(result, attr, value)
                    found_count += 1
                else:
                    result.warnings.append(f"{attr}: valeur hors limite ({value})")
            else:
                result.warnings.append(f"{attr}: non detecte")

        # =====================================================================
        # PASS 2 & 3: Equipements (zone basse de l'image)
        # =====================================================================
        # Les equipements sont dans la partie basse de l'image (50% du bas)
        # pour capturer les 2 lignes de cartes
        equip_y_start = int(height * 0.5)
        equip_region = image[equip_y_start:, :]

        # Sauvegarder pour debug
        debug_equip_path = TEMP_DIR / "debug_equipment.png"
        cv2.imwrite(str(debug_equip_path), equip_region)
        logger.debug(f"Zone equipement sauvegardee: {debug_equip_path}")

        # Pass 2: OCR sur la zone equipement - essayer plusieurs preprocessings
        # Essai 1: meme preprocessing que stats (qui fonctionne)
        processed_stats_style = _preprocess_for_stats(equip_region)
        debug_path1 = TEMP_DIR / "debug_equip_stats_style.png"
        cv2.imwrite(str(debug_path1), processed_stats_style)
        text_stats_style = extract_text_with_debug(processed_stats_style)

        # Essai 2: preprocessing card names
        processed_cards = _preprocess_for_card_names(equip_region)
        debug_path2 = TEMP_DIR / "debug_equip_cards_style.png"
        cv2.imwrite(str(debug_path2), processed_cards)
        text_cards_style = extract_text_with_debug(processed_cards)

        # Essai 3: grayscale simple avec Otsu
        gray_equip = cv2.cvtColor(equip_region, cv2.COLOR_BGR2GRAY)
        _, binary_simple = cv2.threshold(gray_equip, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
        debug_path3 = TEMP_DIR / "debug_equip_simple.png"
        cv2.imwrite(str(debug_path3), binary_simple)
        text_simple = extract_text_with_debug(binary_simple)

        # Combiner tous les resultats
        text_cards = f"{text_stats_style}\n{text_cards_style}\n{text_simple}"

        # Log IMPORTANT pour debug - texte brut extrait
        logger.info(f"=== OCR EQUIPEMENT (3 passes) ===")
        logger.info(f"Pass stats_style: {text_stats_style[:200] if text_stats_style else 'VIDE'}")
        logger.info(f"Pass cards_style: {text_cards_style[:200] if text_cards_style else 'VIDE'}")
        logger.info(f"Pass simple: {text_simple[:200] if text_simple else 'VIDE'}")
        logger.info(f"=== FIN OCR ===")

        # Mapping complet des cartes vers leur slot
        # Source: liste officielle Tennis Clash (FR/EN)
        CARD_TO_SLOT = {
            # Slot 1 - Raquette / Racket
            "basique": 1, "starter racket": 1,
            "aigle": 1, "eagle": 1,
            "panthere": 1, "panthère": 1, "panther": 1, "panter": 1,
            "samourai": 1, "samouraï": 1,
            "patriote": 1, "patriot": 1,
            "outback": 1,
            "marteau": 1, "hammer": 1,
            "mille": 1, "bullseye": 1,
            "zeus": 1,
            # Slot 2 - Grip
            "guerrier": 2, "warrior": 2,
            "machette": 2, "machete": 2,
            "katana": 2,
            "griffe": 2, "talon": 2,
            "cobra": 2,
            "forge": 2,
            "tactique": 2, "tactical": 2,
            "titan": 2,
            # Slot 3 - Chaussures / Shoes
            "raptor": 3,
            "chasseur": 3, "hunter": 3,
            "enclume": 3, "anvil": 3,
            "ballistique": 3, "balistique": 3, "ballistic": 3,
            "plume": 3, "feather": 3,
            "piranha": 3,
            "shuriken": 3,
            "hades": 3, "hadès": 3,
            # Slot 4 - Poignet / Wristband
            "missile": 4, "rocket": 4,
            "ara": 4, "macaw": 4,
            "kodiak": 4,
            "bouclier": 4, "shield": 4,
            "tomahawk": 4,
            "pirate": 4, "jolly": 4,
            "koi": 4, "koï": 4,
            "gladiateur": 4, "gladiator": 4,
            # Slot 5 - Nutrition
            "vegane": 5, "végane": 5, "vegan": 5,
            "antioxydants": 5, "antioxidants": 5,
            "hydratation": 5,
            "energie": 5, "énergie": 5, "energy": 5,
            "proteine": 5, "protéine": 5, "protein": 5,
            "macrobiotique": 5, "macrobiotic": 5,
            "cetogene": 5, "cétogène": 5, "keto": 5,
            "glucides": 5, "carboload": 5,
            # Slot 6 - Entrainement / Workout
            "pliometrie": 6, "pliométrie": 6, "plyometrics": 6,
            "musculation": 6, "weight": 6, "lifting": 6,
            "endurance": 6,
            "alpinisme": 6, "mountain": 6, "climber": 6,
            "vitesse": 6, "sprint": 6,
            "halterophilie": 6, "haltérophilie": 6, "powerlifting": 6,
            "elastique": 6, "élastique": 6, "resistance": 6,
            "fentes": 6, "lunges": 6,
        }

        # Chercher les cartes dans le texte OCR
        text_cards_lower = text_cards.lower()
        # Normaliser les accents pour le matching
        text_normalized = text_cards_lower.replace('é', 'e').replace('è', 'e').replace('ê', 'e')
        text_normalized = text_normalized.replace('ï', 'i').replace('ô', 'o').replace('à', 'a')

        # Dictionnaire slot -> (card_name, level)
        found_equipment = {}  # slot -> {"name": str, "level": int}

        # Pattern pour "Le/La Xxx" suivi d'un nombre
        card_pattern = r"(?:le |la |l[''`])?(\w+)(?:[^\d]*?)(\d{1,2})"
        matches = re.findall(card_pattern, text_normalized)

        for name, level_str in matches:
            level = int(level_str)
            if not (8 <= level <= 20):
                continue

            # Chercher dans le mapping
            for card_key, slot in CARD_TO_SLOT.items():
                card_normalized = card_key.replace('é', 'e').replace('è', 'e').replace('ê', 'e')
                card_normalized = card_normalized.replace('ï', 'i').replace('ô', 'o').replace('à', 'a')

                if card_normalized in name or name in card_normalized:
                    if slot not in found_equipment:
                        found_equipment[slot] = {"name": card_key.capitalize(), "level": level}
                        logger.info(f"Carte detectee: {card_key} -> slot {slot}, niveau {level}")
                    break

        # Chercher aussi les noms seuls (sans niveau associe)
        for card_key, slot in CARD_TO_SLOT.items():
            if slot in found_equipment:
                continue
            card_normalized = card_key.replace('é', 'e').replace('è', 'e').replace('ê', 'e')
            card_normalized = card_normalized.replace('ï', 'i').replace('ô', 'o').replace('à', 'a')
            if card_normalized in text_normalized:
                found_equipment[slot] = {"name": card_key.capitalize(), "level": None}
                logger.info(f"Carte detectee (sans niveau): {card_key} -> slot {slot}")

        logger.info(f"Equipements trouves: {found_equipment}")

        # =====================================================================
        # Assembler les equipements
        # =====================================================================
        for slot in range(1, 7):
            eq = ExtractedEquipment(slot=slot)
            if slot in found_equipment:
                eq.card_name = found_equipment[slot]["name"]
                eq.card_level = found_equipment[slot]["level"]
                if eq.card_name:
                    found_count += 1
                if eq.card_level:
                    found_count += 1
            result.equipment.append(eq)

        # Calculer le score de confiance
        # 9 champs stats + 12 champs equipements (6 noms + 6 niveaux) = 21 total
        total_fields = 21
        result.confidence = found_count / total_fields

        logger.info(f"Extraction: {found_count}/{total_fields} champs (confiance: {result.confidence:.0%})")

        return result

    except Exception as e:
        logger.error(f"Erreur extraction v2: {e}", exc_info=True)
        result.warnings.append(f"Erreur: {str(e)}")
        return result


def format_stats_preview(stats: ExtractedStats, lang: str = "FR") -> str:
    """Formate les stats pour preview avant enregistrement.

    Args:
        stats: Donnees extraites
        lang: Langue (FR/EN)

    Returns:
        Texte formate pour affichage Discord
    """
    from constants import EquipmentSlots

    labels = {
        "FR": {
            "character": "Personnage",
            "points": "Points",
            "power": "Puissance Globale",
            "agility": "Agilite",
            "endurance": "Endurance",
            "serve": "Service",
            "volley": "Volee",
            "forehand": "Coup Droit",
            "backhand": "Revers",
            "equipment": "Equipement",
            "confidence": "Confiance",
            "warnings": "Avertissements",
        },
        "EN": {
            "character": "Character",
            "points": "Points",
            "power": "Global Power",
            "agility": "Agility",
            "endurance": "Endurance",
            "serve": "Serve",
            "volley": "Volley",
            "forehand": "Forehand",
            "backhand": "Backhand",
            "equipment": "Equipment",
            "confidence": "Confidence",
            "warnings": "Warnings",
        }
    }

    l = labels.get(lang.upper(), labels["FR"])

    lines = [
        f"**{l['character']}:** {stats.character_name or '?'}",
        f"**{l['points']}:** {stats.points or '?'}",
        "",
        f"**{l['power']}:** {stats.global_power or '?'}",
        f"**{l['agility']}:** {stats.agility or '?'}",
        f"**{l['endurance']}:** {stats.endurance or '?'}",
        f"**{l['serve']}:** {stats.serve or '?'}",
        f"**{l['volley']}:** {stats.volley or '?'}",
        f"**{l['forehand']}:** {stats.forehand or '?'}",
        f"**{l['backhand']}:** {stats.backhand or '?'}",
    ]

    # Ajouter les equipements
    if stats.equipment:
        lines.append("")
        lines.append(f"**{l['equipment']}:**")
        for eq in stats.equipment:
            slot_name = EquipmentSlots.get_name(eq.slot)
            if eq.card_name and eq.card_level:
                lines.append(f"  {slot_name}: {eq.card_name} (niv.{eq.card_level})")
            elif eq.card_name:
                lines.append(f"  {slot_name}: {eq.card_name}")
            elif eq.card_level:
                lines.append(f"  {slot_name}: ??? (niv.{eq.card_level})")
            else:
                lines.append(f"  {slot_name}: ???")

    lines.append("")
    lines.append(f"**{l['confidence']}:** {stats.confidence:.0%}")

    if stats.warnings:
        lines.append(f"\n**{l['warnings']}:** {len(stats.warnings)}")

    return "\n".join(lines)

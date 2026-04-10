import unicodedata
import re
import json
from pathlib import Path
from typing import Optional

PARENT = Path(__file__).parent
try:
    MAPPING_DATA = json.loads((PARENT / "location_mapping.json").read_text(encoding="utf-8"))
    CITY_MAPPINGS = MAPPING_DATA.get("cities", {})
    DISTRICT_MAPPINGS = MAPPING_DATA.get("districts", {})
except FileNotFoundError:
    CITY_MAPPINGS = {}
    DISTRICT_MAPPINGS = {}

def normalize_for_id(text: str, entity_type: str = "general", context_city: Optional[str] = None) -> str:
    """
    Cleans text for ID generation.
    entity_type: 'city', 'district', or 'general'
    context_city: The standardized city key (e.g., 'HCMC') required if entity_type is 'district'
    """
    if not text:
        return ""

    # 1. Base clean: remove accents, strip spaces, lowercase
    normalized_base = unicodedata.normalize('NFD', text).encode('ascii', 'ignore').decode('utf-8')
    clean_lower = re.sub(r'[^a-zA-Z0-9]', '', normalized_base).lower()

    # 2. Map Cities
    if entity_type == "city" and CITY_MAPPINGS:
        for standard_key, aliases in CITY_MAPPINGS.items():
            if clean_lower in aliases:
                return standard_key

    # 3. Map Districts (Requires the City Context to avoid collisions)
    elif entity_type == "district" and context_city and DISTRICT_MAPPINGS:
        city_districts = DISTRICT_MAPPINGS.get(context_city, {})
        for standard_key, aliases in city_districts.items():
            if clean_lower in aliases:
                return standard_key

    # 4. Fallback for general text (Categories, Streets, or unmapped locations)
    return re.sub(r'[^a-zA-Z0-9]', '', normalized_base).title()
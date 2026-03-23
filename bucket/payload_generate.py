import math
import pandas as pd
import requests
import json
import random
import uuid
import re
from pathlib import Path
from typing import List, Dict, Any
from token_generate import create_admin_token # Using your dynamic token generator

# --- Configuration ---
API_URL = "http://localhost:8000/ingestion/batch"
TOKEN = create_admin_token("admin", 30)
BATCH_SIZE = 500

# Load Catalog
def load_catalog():
    path = Path.cwd() / "dummy_product.json"
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}

DUMMY_CATALOG = load_catalog()

def clean_for_backend(val: Any, fallback: str = "Unknown") -> str:
    """
    Extremely strict cleaner. 
    1. Handles NaNs/None.
    2. Strips special characters to ensure backend 'normalize_for_id' 
       never returns None (which causes the join() TypeError).
    """
    if pd.isna(val) or val is None:
        return fallback
    # Remove symbols that might break backend normalization logic
    cleaned = re.sub(r'[^\w\s]', '', str(val))
    cleaned = cleaned.strip()
    return cleaned if cleaned else fallback

def generate_realistic_menu() -> List[Dict[str, Any]]:
    """Generates menu items with UNIQUE IDs to prevent DB write collisions."""
    if not DUMMY_CATALOG:
        return []
        
    menu = []
    available_keys = [k for k in DUMMY_CATALOG.keys() if "items" in DUMMY_CATALOG[k]]
    if not available_keys:
        return []

    # Pick 2-3 random categories
    selected_cats = random.sample(available_keys, k=min(len(available_keys), random.randint(2, 3)))
    
    for cat_id in selected_cats:
        cat_data = DUMMY_CATALOG[cat_id]
        items_list = cat_data.get("items", [])
        
        # Pick 1-2 items per category
        num_items = min(len(items_list), random.randint(1, 2))
        chosen_items = random.sample(items_list, k=num_items)
        
        for item_name in chosen_items:
            price_range = cat_data.get("price_range", [20000, 50000])
            if len(price_range) < 2: price_range = [20000, 50000]
            
            price = random.randrange(price_range[0], price_range[1] + 1, 1000)
            
            # Format: {CAT_CODE}_{SHORT_UUID} for strict uniqueness
            safe_name = re.sub(r'\W+', '_', str(item_name).lower().strip())
            unique_id = f"prod_{safe_name}"
            
            menu.append({
                "id": str(unique_id),
                "product_name": str(item_name),
                "price": float(price)
            })
    return menu

def transform_row_to_poi(row: pd.Series) -> Dict[str, Any]:
    """Sanitized transformation logic for Travel Lung Tung Schema."""
    
    # Required for Backend ID Generation (Cannot be None)
    category_name  = clean_for_backend(row.get('poi_category'), "General")
    addr_district  = clean_for_backend(row.get('addr_district'), "Unknown District")
    addr_city      = clean_for_backend(row.get('addr_city'), "Hồ Chí Minh")
    
    # General Metadata
    name           = clean_for_backend(row.get('name'), "Unnamed POI")
    operation_time = clean_for_backend(row.get('opening_ho'), "08:00 - 22:00")
    
    # Address extraction
    addr_house     = clean_for_backend(row.get('addr_house'))
    addr_street    = clean_for_backend(row.get('addr_stree'))
    addr_ward      = clean_for_backend(row.get('addr_ward'))
    
    # Street logic: ensuring it's never just whitespace
    full_street = f"{addr_house} {addr_street}".strip() or "Unknown Street"

    # Menu Generation (Coffee-related only)
    is_coffee = any(kw in category_name.lower() for kw in ["coffee", "cafe", "cà phê"])
    dummy_menu = generate_realistic_menu() if is_coffee else []

    return {
        "id": "", # Backend generates this using ID_PARTS + UUID
        "name": name,
        "longitude": float(row['lon']),
        "latitude": float(row['lat']),
        "operation_time": operation_time,
        "address": {
            "street_name": full_street,
            "district": addr_district,
            "ward": addr_ward,
            "city": addr_city,
            "nation": "Vietnam"
        },
        "poi_categories": [
            {
                "id": f"cat_{category_name.lower().replace(' ', '_')}",
                "name": category_name,
                "context": f"A {category_name.lower()} located in {addr_city}."
            }
        ],
        "tag": {
            "id": "tag_imported",
            "name": "Imported from GIS"
        },
        "menu": dummy_menu
    }

def ingest_dataframe(df: pd.DataFrame):
    headers = {"Authorization": f"Bearer {TOKEN}", "Content-Type": "application/json"}
    
    # Drop records missing spatial data immediately
    df = df.dropna(subset=['lon', 'lat'])
    
    print(f"🔄 Preparing {len(df)} records for ingestion...")
    payloads = [transform_row_to_poi(row) for _, row in df.iterrows()]
    
    total_chunks = math.ceil(len(payloads) / BATCH_SIZE)
    success_count = 0
    
    for i in range(total_chunks):
        chunk = payloads[i * BATCH_SIZE : (i + 1) * BATCH_SIZE]
        print(f"📦 Sending Chunk {i + 1}/{total_chunks}...")
        
        try:
            response = requests.post(API_URL, headers=headers, json=chunk)
            if response.status_code == 202:
                print(f"   ✅ Chunk accepted.")
                success_count += len(chunk)
            else:
                print(f"   ❌ Chunk Failed: {response.status_code}")
                print(f"   Details: {response.text}")
        except Exception as e:
            print(f"   ⚠️ Network error: {e}")

    print(f"\n🎉 Ingestion sequence finished! {success_count}/{len(payloads)} records sent.")

if __name__ == "__main__":
    import geopandas as gpd
    try:
        gpf = gpd.read_file(Path.cwd() / "hcm_pois_final.geojson")
        # Clean GIS internal columns
        cols_to_drop = [c for c in ["geometry", "cluster", "processed_name"] if c in gpf.columns]
        gpf.drop(cols_to_drop, axis=1, inplace=True)
        ingest_dataframe(gpf)
    except Exception as e:
        print(f"❌ Script Error: {e}")
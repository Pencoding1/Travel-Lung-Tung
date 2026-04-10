import logging
import json
from typing import List, Dict, Any

# 1. Import your Infrastructure
from app.core.config.settings import db_settings
from app.core.infrastructure.db.database.connector import MemgraphConnector
from app.core.infrastructure.db.uow import MemgraphUnitOfWork

# 2. Import your Services
from app.core.services.management import POIManagementService
from app.core.services.ingestion import POIIngestionService

# Setup basic logging to see what's happening
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# --- MOCK OTA DATA ---
MOCK_BATCH_PAYLOAD: List[Dict[str, Any]] = [
    {
        "id": "poi_hiddengem_001",  # <--- Add this
        "name": "The Hidden Gem Cafe",
        "longitude": 106.7009,
        "latitude": 10.7769,
        "address": {
            "street_name": "15 Le Loi",
            "district": "District 1",
            "city": "Ho Chi Minh City",
            "nation": "Vietnam"
        },
        "contact_info": {
            "phone_number": "02838221234",
            "email": "hello@hiddengem.vn",
            "website": "https://hiddengem.vn"
        },
        "operation_time": "08:00 - 22:00",
        "tag": {"id": "tag_coffee", "name": "Specialty Coffee"},
        "poi_categories": [
            {"id": "cat_cafe", "name": "Cafe", "context": "A place serving coffee and light pastries."}
        ],
        "description": {
            "poi_id": "poi_hiddengem_001",
            "review_id": "rev_123",
            "summary_id": "sum_123",
            "seo_doc_id": "seo_123",
            "faq": {"wifi": "Yes, free"}
        },
        "menu": [
            {"id": "prod_1", "product_name": "Iced Latte", "price": 55000.0}
        ]
    },
    {
        "id": "Cafe_Hochiminhcity_District1_Hamnghi_20260318_002", # Match your naming convention
        "name": "Ben Thanh Market Food Stall",
        "longitude": 106.6975,
        "latitude": 10.7725,
        "address": {
            "street_name": "Ham Nghi", # Added this
            "district": "District 1",
            "city": "Ho Chi Minh City",
            "nation": "Vietnam"
        },
        "contact_info": {
            "phone_number": "+84901234567",
            "email": "stall@benthanh.com",
            "website": "https://benthanh.market" # Added this
        },
        "operation_time": "06:00 - 18:00",
        "tag": {"id": "tag_streetfood", "name": "Street Food"},
        "poi_categories": [
            {"id": "cat_food", "name": "Local Food", "context": "Traditional Vietnamese street food stall."}
        ],
        "poi_categories": [],
        "menu": []
    }
]

def run_integration_tests():
    logger.info("Starting Graph Integration Tests...")

    # 1. Initialize the Database Connection
    logger.info("1. Connecting to Memgraph...")
    connector = MemgraphConnector(db_settings=db_settings)

    try:
        # 2. Test Management Service (Single Create)
        logger.info("2. Testing Single POI Creation (Management Service)...")
        uow = MemgraphUnitOfWork(connector)
        management_service = POIManagementService(uow)
        
        single_payload = MOCK_BATCH_PAYLOAD[0]
        created_poi = management_service.create(single_payload)
        logger.info(f"✅ Successfully created POI: {created_poi['id']}")

        # 3. Test Ingestion Service (Batch Create with UNWIND)
        logger.info("3. Testing Batch Ingestion (Ingestion Service)...")
        ingestion_service = POIIngestionService(uow)
        
        batch_results = ingestion_service.process_ota_batch(MOCK_BATCH_PAYLOAD)
        logger.info(f"✅ Batch Results: {json.dumps(batch_results, indent=2)}")

    except Exception as e:
        logger.error(f"❌ TEST FAILED: {str(e)}")
    finally:
        # Clean up the connection pool
        connector.close()
        logger.info("Tests complete. Connection closed.")

if __name__ == "__main__":
    run_integration_tests()
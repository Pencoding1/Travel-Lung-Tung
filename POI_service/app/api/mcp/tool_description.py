# app/core/utils/tool_descriptions.py
GET_POI_DETAILS_DESC = """
Fetches comprehensive structured data, contact info, and geographically nearby locations for a specific Point of Interest (POI) ID.
Use this tool when the user asks for details about a specific place.
Optional evidence: when `administrative_scope` is `source_snapshot_area_only`, the address is a source display claim only and `administrative_context` is NOT a verified present-day jurisdiction. `source_metadata` (when present) is dataset lineage; do not present unknown fields as known.
"""

GET_ITINERARY_ROUTE_DESC = """
Calculates the real-world route, total distance, time, and turn-by-turn directions between a list of POI IDs using GraphHopper.
AI Agent Rules:
- Pass an array of exact POI_IDs in the order they should be visited.
- Valid vehicles: 'car', 'foot', 'bike'.
"""

GET_EXPLORE_DESC="""
Searches for Points of Interest. You MUST use exact _id parameters (city_id, district_id, street_id, category_id) obtained from the discovery tools. DO NOT pass normal text names here.
    Provide at least one search criterion. All supplied ids are applied together (conjunction), and a category_id is matched exactly, never replaced by a display name.
    Use this for discovery when you do not have a specific POI ID.
    Returns a token-optimized list of matching places with their IDs, which you MUST then pass to get_poi_details or get_itinerary_route.
    When an item has `administrative_scope` = "source_snapshot_area_only", its address is a source display claim and its administrative context is unverified, not present-day jurisdiction.
    Source-snapshot mode is explicit and separate from current geography:
    - source_discovery="snapshots" lists dataset snapshots (namespace + input SHA) usable for source selection.
    - source_discovery="source_areas" with source_snapshot={dataset_namespace, input_sha256} lists raw source labels and stable source_area_id selectors.
    - source_scope={dataset_namespace, input_sha256, source_area_id} retrieves only records that qualify for that exact source snapshot/area. It cannot be combined with current city_id/district_id/street_id. A returned source_context is a source-area claim, never a present-day DistrictID, and raw lineage stays server-side.
"""


GET_ALL_AVAILABLE_CATEGORIES="""Fetches a complete list of all valid POI categories and their exact IDs. 
ALWAYS trigger this tool FIRST if you want to search explore_pois by category, so you do not guess or hallucinate the category_id.
"""
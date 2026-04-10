# app/core/utils/tool_descriptions.py
GET_POI_DETAILS_DESC = """
Fetches comprehensive structured data, contact info, and geographically nearby locations for a specific Point of Interest (POI) ID.
Use this tool when the user asks for details about a specific place.
"""

GET_ITINERARY_ROUTE_DESC = """
Calculates the real-world route, total distance, time, and turn-by-turn directions between a list of POI IDs using GraphHopper.
AI Agent Rules:
- Pass an array of exact POI_IDs in the order they should be visited.
- Valid vehicles: 'car', 'foot', 'bike'.
"""

GET_EXPLORE_DESC="""
Searches for Points of Interest. Provide at least one search criterion. 
    Use this for discovery when you do not have a specific POI ID. 
    Returns a token-optimized list of matching places with their IDs, which you MUST then pass to get_poi_details or get_itinerary_route."""


GET_ALL_AVAILABLE_CATEGORIES="""Fetches a complete list of all valid POI categories and their exact IDs. 
ALWAYS trigger this tool FIRST if you want to search explore_pois by category, so you do not guess or hallucinate the category_id.
"""
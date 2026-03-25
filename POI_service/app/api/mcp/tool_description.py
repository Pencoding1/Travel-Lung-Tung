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
import requests
import json

def get_route():
    # Your local GraphHopper endpoint
    url = "http://localhost:8989/route"

    # Coordinates: Lat, Lon
    airport = "10.8116,106.6611" # Tan Son Nhat
    market = "10.7725,106.6980"  # Ben Thanh Market

    # API parameters
    params = {
        "point": [airport, market],
        "profile": "car",
        "locale": "vi",           # Change to "vi" for Vietnamese turn-by-turn instructions
        "calc_points": "true",    # Returns the geometry of the route
        "instructions": "true"    # Returns turn-by-turn text
    }

    try:
        response = requests.get(url, params=params)
        response.raise_for_status() # Raise an exception for bad status codes
        
        data = response.json()
        
        # Extract the primary route
        path = data["paths"][0]
        distance_km = path["distance"] / 1000
        time_mins = path["time"] / (1000 * 60)
        
        print(f"✅ Route Success!")
        print(f"Path: {path}")
        print(f"Distance: {distance_km:.2f} km")
        print(f"Estimated Time: {time_mins:.2f} minutes")
        
        print("\nFirst 3 Instructions:")
        for instruction in path["instructions"][:3]:
            print(f"- {instruction['text']} (for {instruction['distance']} meters)")

    except requests.exceptions.RequestException as e:
        print(f"❌ API Request failed: {e}")

if __name__ == "__main__":
    get_route()
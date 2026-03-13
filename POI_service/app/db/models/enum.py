from enum import Enum

class BudgetLevel(str, Enum):
    BUDGET = "budget"       # Prioritizes free/cheap POIs
    STANDARD = "standard"   # Mid-range
    LUXURY = "luxury"       # Premium experiences

    @property
    def description(self) -> str:
        mapping = {
            BudgetLevel.BUDGET: "Prioritizes free or cheap POIs, street food, and budget-friendly activities.",
            BudgetLevel.STANDARD: "Mid-range spending, balancing quality and cost for a comfortable trip.",
            BudgetLevel.LUXURY: "Premium experiences, fine dining, exclusive access, and high-end services."
        }
        return mapping[self]

class TravelPace(str, Enum):
    RELAXED = "relaxed"     # Fewer stops, longer duration (e.g., 2-3 hours per POI)
    MODERATE = "moderate"   # Standard touring (e.g., 1-1.5 hours per POI)
    PACKED = "packed"       # Fast-paced, maximizing locations (e.g., 30-45 mins per POI)

    @property
    def description(self) -> str:
        mapping = {
            TravelPace.RELAXED: "Fewer stops, longer duration (2-3 hours per POI). Focuses on deep exploration, resting, and soaking in the atmosphere.",
            TravelPace.MODERATE: "Standard touring (1-1.5 hours per POI). A balanced mix of sightseeing without feeling too rushed.",
            TravelPace.PACKED: "Fast-paced, maximizing locations (30-45 mins per POI). Highly active itinerary to see as many places as possible."
        }
        return mapping[self]

    @property
    def base_duration_minutes(self) -> int:
        """
        Translates the qualitative category into an exact mathematical integer 
        for Stage 3 (The Heuristic Optimizer) to calculate visit_time and end_visit_time.
        """
        mapping = {
            TravelPace.RELAXED: 150,  # 2.5 hours baseline
            TravelPace.MODERATE: 90,  # 1.5 hours baseline
            TravelPace.PACKED: 45     # 45 minutes baseline
        }
        return mapping[self]
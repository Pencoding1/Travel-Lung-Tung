from typing import List, Any

from app.core.base.repository import BaseFirebaseRepository
from app.db.models.Graph_Entities import Stop, Itinerary
from app.db.database.connector import FireStoreConnector
from app.core.interaces.repositories import IItineraryRepository

class FirebaseItineraryRepository(BaseFirebaseRepository[Itinerary], IItineraryRepository):
    def __init__(self, connector: FireStoreConnector):
        super().__init__(connector, collection_name="itineraries", model_class=Itinerary)

    def get_by_start_poi(self, poi_id: str) -> List[Itinerary]:
        docs: Any = self.collection.where("start_poi_id", "==", poi_id).stream()
        return [self.model_class(**doc.to_dict()) for doc in docs]

    def get_by_end_poi(self, poi_id: str) -> List[Itinerary]:
        docs: Any = self.collection.where("end_poi_id", "==", poi_id).stream()
        return [self.model_class(**doc.to_dict()) for doc in docs]

    def get_stops_list(self, id: str) -> List[Stop]:
        # Leverages the inherited get_by_id which parses the nested 'stops' array instantly
        itinerary = self.get_by_id(id)
        if itinerary:
            return itinerary.stops
        return []
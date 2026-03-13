from typing import List, Optional, Any
from datetime import datetime

from app.core.base.repository import BaseFirebaseRepository
from app.db.models.Graph_Entities import Stop
from app.db.database.connector import FireStoreConnector
from app.core.interaces.repositories import IStopRepository

class FirebaseStopRepository(BaseFirebaseRepository[Stop], IStopRepository):
    def __init__(self, connector: FireStoreConnector):
        super().__init__(connector, collection_name="stops", model_class=Stop)

    def get_by_id(self, id: str) -> Optional[Stop]:
        docs: Any = self.collection.where("poi_id", "==", id).limit(1).stream()
        for doc in docs:
            return self.model_class(**doc.to_dict())
        return None

    def update(self, id: str, entity: Stop) -> Stop:
        docs: Any = self.collection.where("poi_id", "==", id).limit(1).stream()
        for doc in docs:
            data = entity.model_dump(mode='json', exclude_unset=True)
            doc.reference.update(data)
            return entity
        raise ValueError(f"Stop with poi_id {id} not found.")

    def delete(self, id: str) -> bool:
        docs: Any = self.collection.where("poi_id", "==", id).limit(1).stream()
        for doc in docs:
            doc.reference.delete()
            return True
        return False

    # ---------------------------------------------------------
    # SPECIFIC QUERIES
    # ---------------------------------------------------------
    def get_by_budget(self, max_budget: float, skip: int = 0, limit: int = 100) -> List[Stop]:
        docs: Any = self.collection.where("budget", "<=", max_budget).offset(skip).limit(limit).stream()
        return [self.model_class(**doc.to_dict()) for doc in docs]

    def get_by_date(self, target_date: datetime, skip: int = 0, limit: int = 100) -> List[Stop]:
        # BaseFirebaseRepository saves datetimes as ISO strings. 
        # We query the date by looking for anything between 00:00:00 and 23:59:59 on that day.
        date_prefix = target_date.strftime("%Y-%m-%d")
        start_str = f"{date_prefix}T00:00:00"
        end_str = f"{date_prefix}T23:59:59"
        
        docs: Any = (self.collection
                     .where("date", ">=", start_str)
                     .where("date", "<=", end_str)
                     .offset(skip).limit(limit).stream())
        
        return [self.model_class(**doc.to_dict()) for doc in docs]

    def get_by_duration_bucket(self, bucket_index: int, skip: int = 0, limit: int = 100) -> List[Stop]:
        """
        Firestore cannot dynamically compute fields during a query. We fetch documents 
        and filter them in Python memory based on the 15-minute interval bucket.
        (e.g., bucket_index 0 = 0-15m, bucket_index 1 = 15-30m)
        """
        min_minutes = bucket_index * 15
        max_minutes = (bucket_index + 1) * 15
        
        docs: Any = self.collection.stream()
        filtered_stops = []
        
        for doc in docs:
            stop = self.model_class(**doc.to_dict())
            # Calculate duration in minutes from the Pydantic datetime fields
            duration = (stop.end_visit_time - stop.visit_time).total_seconds() / 60
            
            if min_minutes <= duration < max_minutes:
                filtered_stops.append(stop)
                
        # Manually apply pagination after memory filtering
        return filtered_stops[skip : skip + limit]

from pathlib import Path

from pydantic import BaseModel, Field
from typing import List, Dict, Optional, Any, Literal

from hashlib import sha256


class RawDataRecord(BaseModel):
    source_id: str = ""
    raw_content: str
    metadata: Dict[str, Any] = Field(default_factory=dict)

    status: Literal["pending", "success", "failed"] = "pending"
    error_log: Optional[Any] = None

    def generate_id(self) -> None:
        """Reads the file, generates a SHA256 hash, and sets it as the source_id."""
        try:
            text_content = Path(self.raw_content).read_text(encoding="utf-8")
            file_hash = sha256(text_content.encode('utf-8')).hexdigest()
            self.source_id = file_hash
            
        except Exception as e:
            self.status = "failed"
            self.error_log = str(e)

    def __hash__(self) -> int:
        return hash(self.source_id)
    
    def __eq__(self, other: object) -> bool:
        if not isinstance(other, RawDataRecord):
            return False
        return self.source_id == other.source_id


class TransformRecord(BaseModel):
    records_id: str
    clean_text: Optional[str] = None
    chunks: List[str] = Field(default_factory=list)
    embeddings: List[List[float]] = Field(default_factory=list)

    status: Literal["pending", "success", "failed"] = "pending"
    error_log: Optional[Any] = None

class GraphOutput(BaseModel):
    graph_nodes: List[Dict[str, Any]] = Field(default_factory=list)
    graph_relationships: List[Dict[str, Any]] = Field(default_factory=list)

    status: Literal["pending", "success", "failed"] = "pending"
    error_log: Optional[Any] = None

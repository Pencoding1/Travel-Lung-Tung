"""
Docstring for pipelines.data_ingestion.base.PipelineBase

We choose ELT pipeline as base pipeline for Data Ingestion pipeline because we need transform documents into
suitable structure for graph and vector database. Including:

- Cleaning Process: remove header, footer, copyright, unrelated or meaningless part can exist in crawled docs.
- Extraction Process: extract parts within the webpage such as comment or review in Website about a tour.
- Data Classification: classify difference context document into difference type to create metadata, improving indexing process.
- Deduplication & Filtering: remove unrelated docs or duplicated docs. Applying PII for personal privacy.
- RAG process:
    + Chunking: split documents into several chunks using markdown structure based strategy before embedding the text.
    + Embedding: use vietnamese embedding model to embed the chunks
    + Indexing and storage: # TODO write this part
- GraphRAG process:
    + NER: for extracting entities
    + Relationship extraction: using LLM to read and identify the connection between entities.
    + # TODO add more here
"""

from config.data_ingestion import IngestionConfig
from abc import ABC, abstractmethod
from typing import List, Any

class BaseDataIngestion(ABC):
    def __init__(self, config: IngestionConfig) -> None:
        self.model_name = config.MODEL_NAME
        self.batch_size = config.BATCH_SIZE
        self.data_source = config.DATA_SOURCE
    
    @abstractmethod
    def extract(self):...

    @abstractmethod
    def load(self):...

    @abstractmethod
    def transform(self):...

    def apply(self):...
    # TODO: add the base pipeline overhere. First define preprocessing step.
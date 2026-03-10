from abc import ABC, abstractmethod

class BaseService(ABC):
    def __init__(self, db_context:):
        
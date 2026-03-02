from abc import ABC, abstractmethod

class IExtractorStrategy(ABC):
    
    @abstractmethod
    def parse_clean(self):...

    @abstractmethod
    def load_schema(self):...

    @abstractmethod
    def load_js(self):...
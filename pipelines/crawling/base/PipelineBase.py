from abc import ABC, abstractmethod
from typing import List, Any
from ....db.models.Raws import RawTripInfo

class BaseCrawler(ABC):
    
    def __init__(self, source_name):
        self.source_name = source_name
        self._results: List[RawTripInfo] = []
    
    @abstractmethod
    def crawl(self, targets: List[str] | str) -> None:
        """
            abstract method cho việc cào dữ liệu
        """
        pass

    @abstractmethod
    def parse(self, raw_content: Any) -> List[RawTripInfo]:
        """
            Chức năng chính là parse dữ liệu từ html hoặc pdf thành dạng RawTripInfo
        """
        pass

    def run(self, target) -> None:
        raw_data = self.crawl(target)
        structured_data = self.parse(raw_data)
        self._results.extend(structured_data)
        for item in self._results:
            item.metadata['crawler'] = self.source_name

        self._validate_and_save()

    def _validate_and_save(self) -> None:...
        # TODO: write validate code
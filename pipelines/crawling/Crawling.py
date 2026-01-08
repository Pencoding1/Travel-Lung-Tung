from typing import List
from ...db.models.Raws import RawTripInfo
from base.PipelineBase import BaseCrawler
from bs4 import BeautifulSoup

import requests

# NOTE: Đối với hệ thống agentic thì toàn bộ code triển khai agent phải được để trong một folder riêng. Không gom hết vào trong này.
# NOTE: Tốt nhất bên trong folder crawling nên tạo thêm một folder là agent để giải quyết vấn đề deep research
class AgenticCrawler(BaseCrawler):
    def __init__(self):
        super().__init__(source_name="Deep Research")
    
    def crawl(self, targets: List[str] | str) -> None:
        # TODO: Hoàn thành code cào dữ liệu ở đây
        pass

    def parse(self, agent_output: dict) -> List[RawTripInfo]:
        results: List[RawTripInfo] = None
        # TODO: Thực hiện parse dữ liệu ở đây

        return results

# NOTE: Đối với cào tay thì nên triển khai thêm các cơ chế lật trang, chuyển trang,...để lấy hết dữ liệu.
# NOTE: ngoài ra dữ liệu còn có ảnh dưới dạng URL được nhúng trong file html thì phải được lấy ra và lưu trữ lại.
# NOTE: Model RawTripInfo đã có sẵn hàm add_image và get_image_bytes để lưu hình ảnh và xuất hình ảnh. Không viết lại hai hàm này
class ManualCrawler(BaseCrawler):
    def __init__(self):
        super().__init__(source_name="Manual")
    
    def crawl(self, url:str | List[str]) -> None:
        # TODO: Hoàn thành code cào dữ liệu ở đây
        if isinstance(url, list):
            responses = [requests.get(u).text for u in url]
        elif isinstance(url, str):
            responses = requests.get(url)
            raw = responses.text
        else: raise TypeError(f"The url should be a list of url or a single url. Not {type(url)}")
        # TODO: Có thể phát triển tiếp để lật từng trang hoặc dừng ở đây và chuyển qua parse dữ liệu
        pass

    def parse(self, html: str) -> List[RawTripInfo]:
        results: List[RawTripInfo] = None
        # TODO: Thực hiện parse dữ liệu ở đây
        return results
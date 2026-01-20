import os
import json
import uuid
import re
import requests
from typing import List, Dict, Any, Union
from datetime import datetime

from db.models.Raws import RawTripInfo 
from pipelines.crawling.base.PipelineBase import BaseCrawler
from anthropic import Anthropic

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

class ManualCrawler(BaseCrawler):
    def __init__(self):
        super().__init__(source_name="Manual")
        
        # Load API Keys
        self.anthropic_key = os.getenv("ANTHROPIC_API_KEY")
        self.firecrawl_key = os.getenv("FIRECRAWL_API_KEY")
        
        if self.anthropic_key:
            self.ai_client = Anthropic(api_key=self.anthropic_key)
        
        # Kho chứa dữ liệu: Map URL -> Markdown Content
        self.crawled_contents: Dict[str, str] = {}

    def _fetch_markdown(self, target_url: str) -> str:
        """
        Hàm helper: Gửi URL tới Firecrawl để lấy Markdown sạch.
        Thay thế cho requests.get() thông thường để tránh bị chặn và lọc rác HTML.
        """
        if not self.firecrawl_key:
            print(" Thiếu FIRECRAWL_API_KEY")
            return ""
            
        try:
            print(f" Firecrawl: Đang xử lý {target_url}...")
            headers = {
                "Authorization": f"Bearer {self.firecrawl_key}",
                "Content-Type": "application/json"
            }
            # Cấu hình lấy Markdown và lọc tag rác
            payload = {
                "url": target_url,
                "formats": ["markdown"],
                "onlyMainContent": True,
                "excludeTags": ["nav", "footer", "script", "style"]
            }
            # Gọi API trực tiếp (đảm bảo ổn định hơn thư viện)
            response = requests.post(
                "https://api.firecrawl.dev/v1/scrape", 
                headers=headers, json=payload, timeout=60
            )
            
            if response.status_code == 200:
                data = response.json()
                md = data.get('data', {}).get('markdown', '') or data.get('markdown', '')
                print(f" Thành công: {len(md)} ký tự.")
                return md
            else:
                print(f" Thất bại ({response.status_code}): {response.text}")
                return ""
        except Exception as e:
            print(f" Lỗi kết nối: {e}")
            return ""

    def crawl(self, url: str | List[str]) -> None:
        """
        Thực hiện cào dữ liệu. Giữ nguyên cấu trúc xử lý List/String theo yêu cầu.
        """
        # --- CODE GIỮ NGUYÊN CẤU TRÚC LOGIC CỦA BẠN ---
        if isinstance(url, list):
            # Duyệt qua từng URL và lấy content
            for u in url:
                # Sử dụng hàm helper _fetch_markdown thay vì requests.get(u).text
                # Lý do: Để lấy Markdown sạch cho AI thay vì HTML thô nhiều rác
                content = self._fetch_markdown(u)
                if content:
                    self.crawled_contents[u] = content
                    
        elif isinstance(url, str):
            # Xử lý URL đơn
            content = self._fetch_markdown(url)
            if content:
                self.crawled_contents[url] = content
                
        else: 
            raise TypeError(f"The url should be a list of url or a single url. Not {type(url)}")
        # ------------------------------------------------

    def parse(self, html: str) -> List[RawTripInfo]:
        """
        Tham số 'html' ở đây sẽ nhận vào Markdown content từ bước crawl.
        """
        results: List[RawTripInfo] = []
        
        if not html or not self.ai_client:
            return results

        print(f"🧠 Claude đang phân tích dữ liệu...")

        # Prompt: Yêu cầu trích xuất JSON và link ảnh
        system_prompt = """
        You are a data extraction expert. Task: Extract tour information into a JSON object.
        RULES:
        1. Output MUST be valid JSON with a root key "tours" containing a list.
        2. Fields: title, price (keep formatting like '4.990.000 đ'), duration, summary (generate from title), sourceUrl.
        3. IMAGE EXTRACTION: Find image URLs in markdown `![alt](url)` and put them into `metadata['detected_image_urls']` (List[str]).
        4. Leave 'images' list empty (root level) because we will fill it with base64 later.
        5. Return ONLY JSON.
        """

        try:
            # Gọi API Claude 3.5 Sonnet
            message = self.ai_client.messages.create(
                model="claude-3-haiku-20240307",
                max_tokens=4096,
                system=system_prompt,
                messages=[{"role": "user", "content": f"Extract tours:\n\n{html[:35000]}"}]
            )
            
            # Xử lý kết quả trả về
            txt = message.content[0].text.strip()
            json_match = re.search(r'\{.*\}', txt, re.DOTALL)
            
            if not json_match:
                print(" Claude không trả về JSON.")
                return results
                
            data = json.loads(json_match.group(0))
            tours_list = data.get('tours', [])
            
            # Fallback tìm ảnh bằng Regex nếu AI bỏ sót
            fallback_images = re.findall(r'!\[.*?\]\((https?://[^\s)]+)\)', html)

            # Map dữ liệu vào RawTripInfo và Xử lý ảnh
            for i, item in enumerate(tours_list):
                # Điền các giá trị mặc định cho RawTripInfo
                item['ID'] = str(uuid.uuid4())
                if 'sourceUrl' not in item: item['sourceUrl'] = "https://travel.com.vn"
                item['crawled_at'] = datetime.now()
                item['source_published_at'] = datetime.now()
                item['doc_type'] = 'html'
                
                # Fix lỗi thiếu trường bắt buộc
                if 'summary' not in item: item['summary'] = item.get('title', '')
                if 'raw_text' not in item: item['raw_text'] = f"{item.get('title')} {item.get('price', '')}"

                try:
                    # Tạo object RawTripInfo
                    tour_obj = RawTripInfo(**item)
                    
                    # --- KẾ THỪA LOGIC ẢNH TỪ & ---
                    # 1. Lấy URL ảnh (ưu tiên AI detect, nếu không có thì dùng Regex fallback)
                    img_urls = item.get('metadata', {}).get('detected_image_urls', [])
                    if not img_urls and fallback_images:
                        # Gán ảnh tương ứng theo thứ tự hoặc ảnh đầu tiên
                        img_urls = [fallback_images[i]] if i < len(fallback_images) else [fallback_images[0]]

                    # 2. Tải ảnh và chuyển đổi sang Base64
                    if img_urls:
                        # Lấy ảnh đầu tiên làm đại diện
                        first_img_url = img_urls[0]
                        try:
                            # print(f" Đang tải ảnh: {first_img_url}")
                            img_resp = requests.get(first_img_url, timeout=10)
                            if img_resp.status_code == 200:
                                # Gọi hàm add_images của RawTripInfo
                                # Hàm này sẽ gọi ImageProcessor.bytes_to_base64 trong datachef.py
                                tour_obj.add_images(img_resp.content)
                        except Exception as e:
                            print(f" Lỗi tải ảnh: {e}")

                    results.append(tour_obj)
                    
                except Exception as e:
                    print(f" Lỗi validate data: {e}")
                    continue

        except Exception as e:
            print(f" Parse error: {e}")
        return results
    
    # 3. HÀM MAIN TEST (CHẠY TRỰC TIẾP FILE NÀY)
# ============================================================================
if __name__ == "__main__":
    print("\n" + "="*60)
    print(" ĐANG CHẠY TEST TRỰC TIẾP TẠI FILE CRAWLING.PY")
    print("="*60)
    
    if not os.getenv("ANTHROPIC_API_KEY"):
        os.environ["ANTHROPIC_API_KEY"] = "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" 
    if not os.getenv("FIRECRAWL_API_KEY"):
        os.environ["FIRECRAWL_API_KEY"] = "fc-a7828ceafcfb4278b9051cb5848c417e"

    # Khởi tạo
    crawler = ManualCrawler()
    target = "https://travel.com.vn/du-lich-ho-chi-minh.aspx"
    
    # Test Crawl
    print(f"📡 Crawl: {target}")
    crawler.crawl(target) # Sẽ gọi logic _fetch_markdown bên trong
    
    # Lấy dữ liệu raw
    raw_md = crawler.crawled_contents.get(target)
    
    if raw_md:
        # Test Parse
        print("🧠 Parse & Download ảnh...")
        data = crawler.parse(raw_md)
        
        print("\n" + "="*60)
        print(f"📊 KẾT QUẢ: {len(data)} TOUR")
        print("="*60)
        
        for idx, t in enumerate(data, 1):
            print(f"Tour #{idx}: {t.title}")
            print(f" - Giá: {t.metadata.get('price', 'N/A')}")
            if t.images:
                print(f" - Ảnh: ✅ Đã có Base64 (Len: {len(t.images[0])})")
            else:
                print(" - Ảnh: ⚠️ Không có")
            print("-" * 30)
    else:
        print("❌ Không có dữ liệu để parse.")
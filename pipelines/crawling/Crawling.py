import os
import json
import uuid
import re
import requests
import asyncio
from typing import List, Dict, Any, Union, Optional, Tuple, Literal
from datetime import datetime
from playwright.async_api import async_playwright
from readability import Document
from bs4 import BeautifulSoup
from pydantic import BaseModel, Field, HttpUrl
from dateutil import parser
from openai import AsyncOpenAI
from db.models.Raws import RawTripInfo
from pipelines.crawling.base.PipelineBase import BaseCrawler



# ==============================================================================
# CÁC CLASS HỖ TRỢ (TỪ MAIN.PY)
# ==============================================================================


class ContentProcessor:
    @staticmethod
    def extract_main_content(html_content: str) -> Tuple[str, str]:
        soup = BeautifulSoup(html_content, 'lxml')
        title = "No title"
        if soup.title and soup.title.string:
            title = soup.title.string
        elif soup.find('h1'):
            title = soup.find('h1').get_text()
        try:
            doc = Document(html_content)
            readability_content = doc.summary()
            if len(readability_content) > 200:
                return title, readability_content
        except Exception as e:
            print(f"Lỗi extract main content: {e}")

        for element in soup(["script", "style", "iframe", "noscript", "aside", "nav", "footer", "header"]):
            element.decompose()

        content_candidates = [
            'article', 'main',
            {'class_': 'post-content'}, {'class_': 'entry-content'},
            {'id': 'content'}, {'id': 'main'}
        ]

        main_tag = None
        for selector in content_candidates:
            if isinstance(selector, str):
                main_tag = soup.find(selector)
            else:
                main_tag = soup.find('div', **selector)
            if main_tag: break
        raw_html = str(main_tag) if main_tag else str(soup.body) if soup.body else html_content
        return title, raw_html

    @staticmethod
    def extract_images(html_snippet: str, limit: int = 10) -> List[bytes]:
        soup = BeautifulSoup(html_snippet, 'lxml')
        img_tags = soup.find_all('img')
        valid_images = []
        for img in img_tags:
            if len(valid_images) >= limit: break
            src = img.get('data-src') or img.get('src')
            if not src: continue
            if src.startswith('//'): src = 'https:' + src
            if src.startswith('http'):
                try:
                    resp = requests.get(src, timeout=3)
                    if resp.status_code == 200:
                        valid_images.append(resp.content)
                except Exception as e:
                    print(f"Lỗi tải ảnh {src}: {e}")
        return valid_images

    @staticmethod
    def extract_published_date(html_content: str) -> Optional[datetime]:
        if not html_content: return None
        soup = BeautifulSoup(html_content, 'lxml')
        scripts = soup.find_all('script', type='application/ld+json')
        for script in scripts:
            try:
                data = json.loads(script.string)
                candidates = data if isinstance(data, list) else [data]
                for item in candidates:
                    date_str = item.get('datePublished') or item.get('dateCreated') or item.get('uploadDate')
                    if date_str: return parser.parse(str(date_str).strip())
            except Exception as e:
                print(f"Lỗi parse date JSON-LD: {e}")

        meta_selector = "meta[property='article:published_time'], meta[property='og:published_time'], meta[itemprop='datePublished']"
        meta_tag = soup.select_one(meta_selector)
        if meta_tag and meta_tag.get("content"):
            try:
                return parser.parse(str(meta_tag["content"]).strip())
            except Exception as e:
                print(f"Lỗi parse date Meta tag: {e}")

        time_tag = soup.find("time")
        if time_tag:
            val = time_tag.get("datetime") or time_tag.get_text()
            try:
                return parser.parse(str(val).strip())
            except Exception as e:
                print(f"Lỗi parse date Time tag: {e}")

        class_tag = soup.select_one(".date, .post-date, .published")
        if class_tag:
            try:
                return parser.parse(class_tag.get_text().strip(), fuzzy=True)
            except Exception as e:
                print(f"Lỗi parse date Class tag: {e}")

        return None


# ==============================================================================
# CLASS AGENTIC CRAWLER
# ==============================================================================

class AgenticCrawler(BaseCrawler):
    def __init__(self):
        super().__init__(source_name="Deep Research")
        # Khởi tạo OpenAI Client cho các hàm nội bộ dùng
        self.ai_client = AsyncOpenAI(
            base_url="http://localhost:1234/v1",
            api_key="lm-studio"
        )

    # --- CÁC PHƯƠNG THỨC HỖ TRỢ LOGIC TỪ MAIN.PY ---

    async def _scrape_url_corrected(self, url: str) -> Optional[RawTripInfo]:
        """Logic scrape từ main.py"""
        print(f"Cào ở trang web sau: {url}")
        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=True)
            context = await browser.new_context(
                user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
            )
            page = await context.new_page()
            try:
                await page.goto(url, wait_until="domcontentloaded", timeout=60000)
                await page.evaluate("window.scrollTo(0, document.body.scrollHeight / 2)")
                await page.wait_for_timeout(2000)
                full_page_html = await page.content()

                title, raw_text_html = ContentProcessor.extract_main_content(full_page_html)
                published_at = ContentProcessor.extract_published_date(full_page_html)
                raw_image_bytes = ContentProcessor.extract_images(raw_text_html)
                print(f"Title: {title}")
                print(f"Published: {published_at}")

                trip_info = RawTripInfo(
                    ID=str(uuid.uuid4()),
                    title=title,
                    summary="",
                    raw_text=raw_text_html,
                    doc_type="html",
                    sourceUrl=url,
                    crawled_at=datetime.now(),
                    source_published_at=published_at,
                    metadata={}
                )

                # --- GỌI HÀM CỦA CLASS RawTripInfo ---
                for img_bytes in raw_image_bytes:
                    trip_info.add_images(img_bytes)

                return trip_info
            except Exception as e:
                print(f"Lỗi scrape: {e}")
                return None
            finally:
                await browser.close()

    async def _analyze_with_ai(self, raw_data: RawTripInfo) -> dict:
        """Logic phân tích AI từ main.py"""
        if not raw_data: return {}
        print(f"\nĐANG GỌI AI PHÂN TÍCH: {raw_data.title}...")

        prompt = """
        Bạn là một chuyên gia về du lịch. Hãy phân tích văn bản và trả về JSON:
        {
            "summary": "Tóm tắt ngắn gọn, gồm khoảng 4 câu, tóm lược toàn bộ nội dung chính, điểm nổi bật và trải nghiệm đặc sắc nhất trong bài viết.",
            "metadata": {
                "location": "Địa điểm",
                "price": "Trích xuất TẤT CẢ thông tin liên quan đến chi phí. Hãy tìm kỹ các con số như giá vé tham quan, giá phòng, chi phí ăn uống hoặc tổng chi phí chuyến đi. Nếu có nhiều loại giá, hãy tóm tắt lại (Ví dụ: 'Vé vào cửa: 950k, Ăn uống: 500k')."
            }
        }
        """
        try:
            input_text = raw_data.raw_text[:8000]
            response = await self.ai_client.chat.completions.create(
                model="local-model",
                messages=[
                    {"role": "system", "content": prompt},
                    {"role": "user", "content": f"Bài viết:\n{input_text}"}
                ],
                temperature=0.3
            )

            content = response.choices[0].message.content.strip()
            if "```" in content:
                match = re.search(r"```(?:json)?(.*?)```", content, re.DOTALL)
                content = match.group(1).strip() if match else content.replace("```json", "").replace("```", "").strip()

            ai_result = json.loads(content)

            # Gộp dữ liệu
            combined_data = raw_data.model_dump(by_alias=True)

            new_summary = ai_result.get("summary", "")
            if new_summary:
                print(f"Đã cập nhật Summary mới từ AI.")
                combined_data["summary"] = new_summary

            if "metadata" in ai_result:
                current_meta = combined_data.get("metadata", {})
                current_meta.update(ai_result["metadata"])
                combined_data["metadata"] = current_meta

            # In kết quả
            print("\n" + "=" * 40)
            print("KẾT QUẢ AI PHÂN TÍCH")
            print("=" * 40)
            print(f"Summary  : {ai_result.get('summary', 'Không có')}")
            print(f"Chi phí  : {ai_result.get('metadata', {}).get('price', 'Không rõ')}")
            print("=" * 40)

            return combined_data

        except Exception as e:
            print(f"Lỗi AI: {e}")
            return raw_data.model_dump(by_alias=True)

    def _save_to_file(self, data: List[RawTripInfo], filename: str = None):
        """Hàm lưu file vào folder data(json) với tên động"""
        try:
            if not data:
                return

            # --- 1. CẤU HÌNH ĐƯỜNG DẪN FOLDER ---
            output_folder = os.path.join("data(json)")
            # Tạo folder nếu chưa tồn tại (quan trọng để không bị lỗi)
            os.makedirs(output_folder, exist_ok=True)

            # --- 2. TẠO TÊN FILE TỪ TITLE ---
            original_title = data[0].title if data and data[0].title else "unknown_title"
            safe_title = re.sub(r'[\\/*?:"<>|]', "", original_title)  # Loại bỏ ký tự cấm
            safe_title = safe_title.strip().replace(" ", "_")[:50]  # Làm gọn tên

            filename = f"ket_qua_{safe_title}.json"

            # --- 3. GHÉP ĐƯỜNG DẪN HOÀN CHỈNH ---
            # Kết quả sẽ là: data/json/ket_qua_title.json
            full_path = os.path.join(output_folder, filename)
            # Lưu file
            json_data = [item.model_dump(mode='json', by_alias=True) for item in data]

            with open(full_path, 'w', encoding='utf-8') as f:
                json.dump(json_data, f, ensure_ascii=False, indent=4)
            abs_path = os.path.abspath(full_path)
            print(f"\nĐã lưu thành công vào: {abs_path}")

        except Exception as e:
            print(f"Lỗi khi lưu file: {e}")

    async def _process_workflow(self, targets: List[str]):
        """Hàm điều phối luồng chạy"""
        for url in targets:
            # 1. Cào dữ liệu
            result = await self._scrape_url_corrected(url)

            if result:
                # 2. Phân tích & Gộp dữ liệu
                merged_dict = await self._analyze_with_ai(result)

                # 3. Parse (Gọi hàm parse của class này)
                final_objects = self.parse(merged_dict)

                # 4. Lưu file
                self._save_to_file(final_objects)

    # PUBLIC METHODS

    def crawl(self, targets: List[str] | str) -> None:
        if isinstance(targets, str):
            targets = [targets]

        print(f"Bắt đầu Crawl cho {len(targets)} URL...")
        # Chạy luồng async trong hàm sync
        asyncio.run(self._process_workflow(targets))

    def parse(self, agent_output: dict) -> List[RawTripInfo]:
        results: List[RawTripInfo] = []
        try:
            if agent_output:
                # 1. Chuyển đổi Dict -> Object (Pydantic tự map các trường)
                trip_obj = RawTripInfo(**agent_output)
                results = [trip_obj]

                # 2. In Log chi tiết
                print("\n" + "=" * 40)
                print("KẾT QUẢ CÀO DỮ LIỆU")
                print("=" * 40)
                print(f"1. ID (UUID)      : {trip_obj.id}")

                # Lưu ý: Trong Raws.py, field là 'source_url' (alias='sourceUrl')
                print(f"2. URL            : {trip_obj.source_url}")
                print(f"3. Title          : {trip_obj.title}")
                print(f"4. Published Date : {trip_obj.source_published_at}")
                print(f"5. Summary        : {trip_obj.summary}")
                print(f"6. Crawled At     : {trip_obj.crawled_at}")
                print(f"7. Ảnh thu thập   : {len(trip_obj.images)} ảnh")
                print(f"8. Raw Text       : {trip_obj.raw_text}")
                print("=" * 40 + "\n")

            else:
                print("Nhận dữ liệu rỗng.")
                results = []
        except Exception as e:
            # In lỗi chi tiết để debug nếu Pydantic validate sai
            print(f"Lỗi khi chuyển đổi dữ liệu: {e}")
            results = []

        return results


if __name__ == "__main__":
    crawler = AgenticCrawler()

    print("=" * 50)
    print("Nhập đường link để bắt đầu xử lý.")
    print("Nhập 'stop' để kết thúc chương trình.")
    print("=" * 50)

    while True:
        # 1. Nhập liệu từ Admin
        url = input("\nNhập URL (hoặc 'stop'): ").strip()

        # 2. Kiểm tra điều kiện dừng
        if url.lower() == "stop":
            print("\n Đã dừng ")
            break  # Vòng lặp chính, break là hợp lý ở đây

        # 3. Kiểm tra input rỗng
        if not url:
            # Không làm gì nếu url rỗng
            pass
        else:
            # 4. Gọi hàm crawl xử lý URL vừa nhập
            try:
                crawler.crawl(url)
            except Exception as e:
                print(f"Có lỗi xảy ra khi xử lý URL này: {e}")
import json
import uuid
import re
import asyncio

from utils.Content_Processor import ContentProcessor
from db.repositories.Repositories import FireStoreRepository
from pipelines.crawling.base.PipelineBase import BaseCrawler

from loguru import logger
from datetime import datetime
from copy import deepcopy
from typing import List, Optional

from db.models.Raws import RawTripInfo

from openai import AsyncOpenAI
from playwright.async_api import async_playwright

class AgenticCrawler(BaseCrawler):
    def __init__(self):
        super().__init__(source_name="Deep Research")
        # Khởi tạo OpenAI Client cho các hàm nội bộ dùng
        self.ai_client = AsyncOpenAI(
            base_url="http://localhost:1234/v1",
            api_key="lm-studio"
        )
        self.firestore_repo = FireStoreRepository[RawTripInfo]("RawData", RawTripInfo)
        logger.info("Firestore Repository initialized for collection: RawData")

    # --- CÁC PHƯƠNG THỨC HỖ TRỢ LOGIC TỪ MAIN.PY ---

    async def _scrape_url_corrected(self, url: str) -> Optional[RawTripInfo]:
        """Logic scrape từ main.py"""
        logger.info(f"Is Scraping at: {url}")
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
                processor = ContentProcessor(full_page_html)

                title, raw_text_html = processor.extract_main_content()
                published_at = processor.extract_published_date()
                raw_image_urls = processor.extract_images()
                logger.info(f"Title: {title}")
                logger.info(f"Published: {published_at}")

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
                for url in raw_image_urls:
                    trip_info.add_images_url(url)

                return trip_info
            except Exception as e:
                logger.error(f"An error occurs when scraping: {e}")
                return None
            finally:
                await browser.close()

    async def _analyze_with_ai(self, raw_data: RawTripInfo) -> dict:
        """Logic phân tích AI từ main.py"""
        if not raw_data: return {}
        logger.info(f"\AI Agent is calling for Analyzing the data: {raw_data.title}...")

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

            content = response.choices[0].message.content
            if content:
                content = content.strip()

                if "```" in content:
                    match = re.search(r"```(?:json)?(.*?)```", content, re.DOTALL)
                    content = match.group(1).strip() if match else content.replace("```json", "").replace("```", "").strip()

                ai_result = json.loads(content)
            else:
                raise Exception("Message has no content")

            # Gộp dữ liệu
            combined_data = raw_data.model_dump(by_alias=True)

            new_summary = ai_result.get("summary", "")
            if new_summary:
                logger.info(f"Update summary received from the agent.")
                combined_data["summary"] = new_summary

            if "metadata" in ai_result:
                current_meta = combined_data.get("metadata", {})
                current_meta.update(ai_result["metadata"])
                combined_data["metadata"] = current_meta

            # In kết quả
            report = f"""{"="*40}
            THE RESULT
            {"=" * 40}
            Summary  : {ai_result.get('summary', 'Không có')}
            Chi phí  : {ai_result.get('metadata', {}).get('price', 'Không rõ')}
            {"=" * 40}
            """

            logger.info(report)

            return combined_data

        except Exception as e:
            print(f"Lỗi AI: {e}")
            return raw_data.model_dump(by_alias=True)
        
    async def _save_to_database(self, data: List[RawTripInfo]):
        if not data:
            logger.info("Data is emtpy.")
            return
        
        for item in data:
            try:
                saved_item = await self.firestore_repo.add(item)
                logger.info(f"Succesfully saved item: \nID:{item.id}\nTitle:{item.title}")
            except Exception as e:
                logger.error(f"An error occurs when save the item: {e}")


    async def _process_workflow(self, targets: List[str]):
        """Hàm điều phối luồng chạy"""
        for url in targets:
            result = await self._scrape_url_corrected(url)
            if result:
                merged_dict = await self._analyze_with_ai(result)
                final_objects = self.parse(merged_dict)
                await self._save_to_database(final_objects)

    # PUBLIC METHODS

    def crawl(self, targets: List[str] | str) -> None:
        if isinstance(targets, str):
            targets = [targets]

        logger.info(f"Starting data crawling for {len(targets)} URL...")
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
                logger.info("\n" + "=" * 40)
                logger.info("KẾT QUẢ CÀO DỮ LIỆU")
                logger.info("=" * 40)
                logger.info(f"1. ID (UUID)      : {trip_obj.id}")
                
                # Lưu ý: Trong Raws.py, field là 'source_url' (alias='sourceUrl')
                
                logger.info(f"2. URL            : {trip_obj.source_url}")
                logger.info(f"3. Title          : {trip_obj.title}")
                logger.info(f"4. Published Date : {trip_obj.source_published_at}")
                logger.info(f"5. Summary        : {trip_obj.summary}")
                logger.info(f"6. Crawled At     : {trip_obj.crawled_at}")
                logger.info(f"7. Ảnh thu thập   : {len(trip_obj.images)} ảnh")
                logger.info(f"8. Raw Text       : {trip_obj.raw_text}")
                logger.info("=" * 40 + "\n")

            else:
                logger.info("Empty data.")
                results = []
        except Exception as e:
            # In lỗi chi tiết để debug nếu Pydantic validate sai
            logger.error(f"An error occurs when transform the data: {e}")
            results = []

        return results

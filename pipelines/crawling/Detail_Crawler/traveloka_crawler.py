from typing import Callable, List, Optional, Callable, Tuple

from crawl4ai import DefaultMarkdownGenerator

from playwright.async_api import Page, BrowserContext

from config.settings import LoadPipelineSetting
from config.exceptions import IntentedNotImplementedException
from pipelines.crawling.base.detail_crawler import BaseDetailCrawler
from utils.LoadExtraction import LoadExtractionScript

class TravelokaCrawler(BaseDetailCrawler):
    def __init__(self, cfg: LoadPipelineSetting,
                 markdown_creator: Optional[DefaultMarkdownGenerator] = None):
    
        super().__init__(cfg, markdown_creator=markdown_creator)
        extract_cfg = cfg.extractor_cfg
        extract_cfg.set_domain(self.get_domain_name())
        
        
    def get_domain_name(self) -> str: return "traveloka"

    @staticmethod
    async def _goto_home(page: Page, context:BrowserContext, url:str, **kwagrs):
        print("[HOOK] Go to home page to load session cookie.")
        await page.goto("https://www.traveloka.com/vi-vn", wait_until="networkidle")
        print("[HOOK] Successfully to home page.")
        return page

    def get_hook(self) -> Tuple[Callable, str]:
        # 2. ĐỌC trạng thái từ self. Nếu chưa có (chạy độc lập), mặc định là "explore"
        current_type = getattr(self, "current_crawl_type", "explore")
        
        if current_type == "explore":
            return self.on_page_context_created, "on_page_context_created"
        
        return self._goto_home, "before_goto"
    
    @staticmethod
    async def on_page_context_created(page: Page, context: BrowserContext, **kwargs):
        print("[HOOK] on_page_context_created - Setting up STRICT anti-redirect rules.")
        # # TẦNG 1: XỬ LÝ HỘP THOẠI TRÌNH DUYỆT
        # Tự động bấm "Hủy" (Cancel) ở tốc độ ánh sáng nếu trình duyệt hỏi "Bạn có muốn rời trang không?"
        async def handle_dialog(dialog):
            if dialog.type == 'beforeunload':
                print("[BLOCKED] Auto-dismissed redirect dialog. Page HTML is frozen and safe.")
                await dialog.dismiss()
            else:
                await dialog.accept() # Chấp nhận các loại popup thông thường khác
        
        page.on("dialog", handle_dialog)

        # TẦNG 2: TIÊM JS KÍCH HOẠT HỘP THOẠI
        # Bất cứ khi nào Traveloka gọi lệnh đổi URL, sự kiện 'beforeunload' sẽ bị kích hoạt.
        # Trình duyệt sẽ DỪNG VIỆC XÓA DOM để bật popup -> Playwright ở Tầng 1 lập tức bấm Hủy -> DOM được bảo toàn.
        js_anti_redirect = """
            window.history.pushState = function() {};
            window.history.replaceState = function() {};
            
            window.addEventListener('beforeunload', (e) => {
                e.preventDefault();
                e.returnValue = 'Blocked by Crawler';
            });
        """
        await page.add_init_script(js_anti_redirect)

        """Tạm comment code xử lý chèn ERROR 204 để tránh sau này gặp khó thì dùng hard constraint"""
        # TẦNG 3: BỨC TƯỜNG NETWORK VỚI HTTP 204
        # async def block_flight_redirect(route):
        #     request_url = route.request.url.lower()
            
        #     if "flight" in request_url or "ve-may-bay" in request_url:
        #         if route.request.resource_type == 'document':
        #             # Nếu request là dạng tải trang (document), tuyệt đối KHÔNG abort (vì abort sẽ gây màn hình xám).
        #             # Ta trả về mã 204 (No Content). Theo chuẩn Web, nhận được 204 trình duyệt sẽ KHÔNG LÀM GÌ CẢ và ở yên trang cũ.
        #             print(f"[BLOCKED] Intercepted document redirect. Sending HTTP 204.")
        #             await route.fulfill(status=204, body="")
        #         else:
        #             # Chặn sạch các API/Tracking ngầm
        #             print(f"[BLOCKED] Prevented background request: {request_url}")
        #             await route.abort() 
        #     else:
        #         await route.continue_()

        # await page.route("**/*", block_flight_redirect)
        return page
    def _load_extractor(self, crawl_type:str):
        # TODO: Implement extractor for Hotel and Blog
        extractor = None

        if crawl_type == "hotel":
            raise IntentedNotImplementedException("Hotel extractor hasn't been implemented yet.")
        
        extractor = LoadExtractionScript(self.cfg.extractor_cfg, name=crawl_type)

        if extractor:
            self.schemas = extractor.load_schema()
            self.cfg.crawler_cfg.run_cfg.js_code = extractor.load_js()
            if self.schemas or self.cfg.crawler_cfg.run_cfg.js_code:
                self.logger.info("Successfully load extractor.")
                return
            self.logger.warning("No schema nor js has found")
            return

        self.logger.info("No valid extractor has found. Run without extractor...")

    async def crawl_with_schema(self, url: str | List[str], verbose: bool = True, crawl_type="activities"):
        self.current_crawl_type = crawl_type
        self._load_extractor(crawl_type=crawl_type)
        results = await super().crawl_with_schema(url, verbose)
        return results

if __name__ == "__main__":
    import asyncio
    import json
    from pathlib import Path
    from config.settings import *
    from crawl4ai import CrawlResult

    from pipelines.preprocessing.preprocessing import TravelokaPreprocessor

    def get_dummy_setting():
        setting = LoadPipelineSetting(
            crawler_cfg=CrawlerSetting(),
            extractor_cfg=ExtractorSettings(),
            discover_cfg=DiscoverSettings()
        )
        return setting
    
    def get_dummy_extract_setting():
        return ExtractPipelineSetting(
            pipeline_cfg=IngestionSettings()
        )
    
    async def test():
        crawler = TravelokaCrawler(get_dummy_setting())

        preprocessor = TravelokaPreprocessor(
            config=get_dummy_extract_setting(), 
            lsh=None
        )
        crawl_type = "activities"
        results = await crawler.crawl_with_schema(url="https://www.traveloka.com/vi-vn/activities/vietnam/product/hcmc-only-dmaris-seafood-buffet-chain-vouchers-by-giftpop-3585196162595", crawl_type=crawl_type)
        #print(results.extracted_content)
        #return results
        if results and results.success:
            print("[*] Cào thành công! Đang tiến hành parse làm sạch dữ liệu...")
            
            # 4. Parse dữ liệu thô qua Preprocessor
            parsed_result = preprocessor.parse(
                content=results.extracted_content,
                crawl_type=crawl_type
            )
            
            # 5. Lưu vào file JSON
            data_dir = Path("data")
            data_dir.mkdir(parents=True, exist_ok=True) # Tự động tạo folder data nếu chưa có
            
            file_name = "Explore_Extractor.json"
            out_file = data_dir / file_name
            
            # Viết dữ liệu ra file với chuẩn UTF-8 và indent đẹp mắt
            out_file.write_text(
                json.dumps(parsed_result, indent=4, ensure_ascii=False), 
                encoding="utf-8"
            )
            print(f"[+] HOÀN TẤT! Dữ liệu đã được lưu gọn gàng tại: {out_file}")
        else:
            print("[-] Cào dữ liệu thất bại hoặc không có nội dung.")
    
    print(asyncio.run(test()))
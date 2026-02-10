import logging
from typing import List, Optional, Dict, Any
from urllib.parse import urlparse, parse_qs, urlencode, urlunparse

from pipelines.crawling.base.PipelineBase import BasePipelineCrawler
from utils.crawling_utils import load_js

logger = logging.getLogger("VNTravelCrawler")

# Số trang phân trang tối đa sẽ crawl (trang 2, 3, ...) — tránh sinh quá nhiều URL
MAX_PAGINATION_PAGES = 15


class VNTravelCrawler(BasePipelineCrawler):
    def __init__(self, place_name: str, city_data: Dict = {}, **kwargs):
        self.place_name = place_name
        super().__init__(**kwargs)

        self.city_data = city_data or {}
        self.webpage_name = "vntravel"
        self.lang_code = "vi"

        self.browser_cfg.enable_stealth = True


    def get_domain_name(self) -> str:
        return self.webpage_name

    def get_css_selectors(self) -> List[str]:
        # Selector cho nội dung bài viết trên vntravel.org.vn
        return [
            '.detail-content',
            '.content_detail',
            'h1.title-detail',
            '.sapo_detail',
            '#main-content'
        ]

    def get_place_patterns(self) -> List[str]:
        if "place_patterns" in self.city_data:
            return self.city_data["place_patterns"]
        slug = self.place_name.lower().replace(" ", "-")
        return [f"*{slug}*", "*vntravel*"]

    def get_js_actions(self) -> Optional[str]:
        return load_js()

    def get_pagination_patterns(self) -> List[str]:
        """Pattern dùng để nhận diện URL trang phân trang (cho filter/skip)."""
        return ["*p=*", "*page=*"]

    def build_pagination_urls(self, seed_url: str, max_pages: int) -> List[str]:
        """
        Sinh danh sách URL phân trang từ seed (trang 1 = seed, trang 2, 3, ... thêm tham số page).
        vntravel.org.vn thường dùng: tim-kiem.html?keyword=xxx hoặc ?keyword=xxx&page=2
        """
        if not seed_url or not seed_url.startswith(("http://", "https://")):
            return [seed_url] if seed_url else []

        parsed = urlparse(seed_url)
        query = parse_qs(parsed.query, keep_blank_values=True)

        # Tên tham số phân trang (một số site dùng 'page', một số dùng 'p')
        page_param = "page" if "page" in query else "p"
        max_pages = min(max(1, max_pages), MAX_PAGINATION_PAGES)

        out = [seed_url]
        for p in range(2, max_pages + 1):
            q = dict(query)
            q[page_param] = [str(p)]
            new_query = urlencode(q, doseq=True)
            new_url = urlunparse((
                parsed.scheme, parsed.netloc, parsed.path,
                parsed.params, new_query, parsed.fragment
            ))
            out.append(new_url)
        return out

    def use_semantic_filter(self) -> bool:
        return True

    def get_embedding_query(self) -> str:
        return f"Bài viết du lịch, kinh nghiệm, địa điểm tham quan tại {self.place_name}"

    def get_specific_keywords(self) -> List[str]:
        return [self.place_name, "du lịch", "khám phá", "ẩm thực", "kinh nghiệm", "trải nghiệm"]

    def get_excluded_selectors(self) -> List[str]:
        return [
            "header", "footer", "nav", "aside",
            "script", "style", "iframe", "svg",
            ".header", ".sidebar", ".related-news",
            ".comment-box", ".banner", ".menu-mobile",
            ".promoBanner", ".newsletter",
            # Chỉ loại bỏ ảnh trong các container quảng cáo/sponsor rõ ràng
            ".ad img", ".advertisement img", ".sponsor img", ".promo img",
            # Loại bỏ SVG và ảnh icon/logo rõ ràng trong path
            "img[src*='/icon/']", "img[src*='/icons/']", "img[src*='/logo/']", 
            "img[src*='/logos/']", "img[src*='/badge/']", "img[src*='/sprite/']",
            "img[src*='imageresource']", "img[src*='.svg']",
            # Loại bỏ ảnh trong các phần tử có class/id rõ ràng là quảng cáo
            "[class*='ad-'] img", "[id*='ad-'] img", "[class*='sponsor-'] img",
            "[class*='promo-'] img", "[id*='sponsor'] img", "[id*='promo'] img",
        ]

    def get_url_filter_patterns(self) -> List[str]:
        return self.get_place_patterns() + self.get_pagination_patterns()

    def process_item(self, result):
        processed = super().process_item(result)
        if not processed:
            return None
        content = processed.get("content", "")
        if content:
            lines, filtered = content.split("\n"), []
            for line in lines:
                if "![" in line and "](" in line:
                    img_url = line.split("](")[1].split(")")[0] if "](" in line else ""
                    if not img_url:
                        filtered.append(line)
                        continue
                    
                    img_url_lower = img_url.lower()
                    
                    # Chỉ loại bỏ khi chắc chắn là ảnh rác (icon/logo/quảng cáo)
                    # Kiểm tra pattern trong path hoặc tên file, không phải substring chung chung
                    should_filter = False
                    
                    # 1. Loại bỏ SVG và các format vector
                    if img_url_lower.endswith(('.svg', '.svgz')) or '/svg' in img_url_lower:
                        should_filter = True
                    
                    # 2. Loại bỏ khi có path cụ thể chứa từ khóa rác
                    # Ví dụ: /icon/, /logo/, /badge/, /sprite/, /ad/, /sponsor/, /promo/
                    path_patterns = [
                        '/icon/', '/icons/', '/logo/', '/logos/', '/badge/', '/badges/',
                        '/sprite/', '/sprites/', '/imageresource/',
                        '/ad/', '/ads/', '/advertisement/', '/advertisements/',
                        '/sponsor/', '/sponsors/', '/promo/', '/promos/',
                        '/button/', '/buttons/', '/arrow/', '/arrows/', '/chevron/'
                    ]
                    if any(pattern in img_url_lower for pattern in path_patterns):
                        should_filter = True
                    
                    # 3. Loại bỏ khi tên file chứa từ khóa rác (ví dụ: icon.png, logo.jpg)
                    # Chỉ kiểm tra phần tên file, không kiểm tra toàn bộ URL
                    from urllib.parse import urlparse
                    parsed = urlparse(img_url)
                    filename = parsed.path.split('/')[-1].lower() if parsed.path else ""
                    if filename:
                        # Tên file chứa từ khóa rác và có extension ảnh
                        if any(kw in filename for kw in ['icon', 'logo', 'badge', 'sprite', 'button', 'arrow', 'chevron']) and \
                           filename.endswith(('.jpg', '.jpeg', '.png', '.gif', '.webp', '.svg')):
                            # Nhưng giữ lại nếu là ảnh tour hợp lệ (ví dụ: tour-icon.jpg có thể là ảnh tour)
                            # Chỉ filter nếu tên file BẮT ĐẦU bằng từ khóa rác
                            if filename.startswith(('icon', 'logo', 'badge', 'sprite', 'button', 'arrow', 'chevron')):
                                should_filter = True
                    
                    # 4. Loại bỏ ảnh rất nhỏ (thường là icon) - kiểm tra trong query string hoặc path
                    # Ví dụ: ?w=16&h=16 hoặc /16x16/
                    if any(size_pattern in img_url_lower for size_pattern in ['w=16', 'h=16', '/16x16/', '/32x32/', '/48x48/', '/64x64/']):
                        should_filter = True
                    
                    if should_filter:
                        logger.debug(f"VNTravelCrawler: Filtered out image: {img_url[:80]}...")
                        continue
                
                filtered.append(line)
            processed["content"] = "\n".join(filtered)
        return processed

    async def execute(self, urls: List[str], output_folder: str ="./data"):
        urls = [u for u in urls if isinstance(u, str) and u.startswith("http")]
        if not urls:
            self.logger.warning("VNTravelCrawler: no valid URLs")
            return

        # Mở rộng seed thành nhiều trang phân trang (trang 1 = seed, trang 2, 3, ...)
        max_pagination = getattr(self.cfg, "max_pages", 50)
        expanded = self.build_pagination_urls(urls[0], max_pagination)
        if len(expanded) > 1:
            self.logger.info(
                f"VNTravelCrawler: pagination enabled, {len(expanded)} pages (seed + page 2..{len(expanded)})"
            )
        urls = expanded

        self.logger.info(f"VNTravelCrawler: crawling {len(urls)} URLs (including pagination)")
        return await super().execute(urls, output_folder)
import logging
from typing import List, Optional, Dict, Any
from pipelines.crawling.base.PipelineBase import BasePipelineCrawler
from pipelines.crawling.utils import load_js

logger = logging.getLogger("VietnamTravelCrawler")


class VietnamTravelCrawler(BasePipelineCrawler):
    def __init__(self, place_name: str, city_data: Dict = None, **kwargs):
        super().__init__(**kwargs)
        self.place_name = place_name
        self.city_data = city_data or {}
        self.webpage_name = "vietnam_travel"
        self.lang_code = "en"
        self.browser_cfg.enable_stealth = True
        self.results_data = []

    def get_domain_name(self) -> str:
        return self.webpage_name

    def get_place_patterns(self) -> List[str]:
        if "place_patterns" in self.city_data:
            return self.city_data["place_patterns"]

        slug = self.place_name.lower().replace(" ", "-")
        return [f"*/places-to-go/*{slug}*", "*/things-to-do/*"]

    def get_js_actions(self) -> Optional[str]:
        return load_js()

    def get_specific_keywords(self) -> List[str]:
        return [self.place_name, "travel", "culture", "experience", "food", "destination"]

    def get_css_selectors(self) -> List[str]:
        # vietnam.travel sử dụng các class rất trực quan cho nội dung bài viết
        return [
            "article p",
            ".node-article p",
            "h1", "h2", "h3",
            '.node-article__content',
            '.node-destination__content',
            '.field-items',
            '.article-content',
            '.pane-content',
            # Thêm selectors cho ảnh trong bài viết
            'article img',
            '.node-article img',
            '.node-article__content img',
            '.field-items img',
            '.article-content img',
            'figure img',
            '.field-image img',
            '.media img'
        ]

    def get_excluded_selectors(self) -> List[str]:
        return [
            "header", "footer", "nav", "aside",
            "script", "style", "iframe", "svg",
            ".main-menu", ".social-share", ".related-articles",
            ".breadcrumb", ".language-switcher",
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
                    
                    # 3. Loại bỏ khi tên file chứa từ khóa rác và bắt đầu bằng từ khóa đó
                    from urllib.parse import urlparse
                    parsed = urlparse(img_url)
                    filename = parsed.path.split('/')[-1].lower() if parsed.path else ""
                    if filename:
                        if filename.startswith(('icon', 'logo', 'badge', 'sprite', 'button', 'arrow', 'chevron')) and \
                           filename.endswith(('.jpg', '.jpeg', '.png', '.gif', '.webp', '.svg')):
                            should_filter = True
                    
                    # 4. Loại bỏ ảnh rất nhỏ (thường là icon)
                    if any(size_pattern in img_url_lower for size_pattern in ['w=16', 'h=16', '/16x16/', '/32x32/', '/48x48/', '/64x64/']):
                        should_filter = True
                    
                    # 5. Giữ lại ảnh từ vietnam.travel (media, panorama, field-image)
                    # Đặc biệt giữ lại ảnh từ /sites/default/files/ (ảnh nội dung chính)
                    if 'vietnam.travel' in img_url_lower or '/sites/default/files/' in img_url_lower:
                        # Chỉ filter nếu chắc chắn là rác (đã check ở trên)
                        pass
                    
                    if should_filter:
                        logger.debug(f"VietnamTravelCrawler: Filtered out image: {img_url[:80]}...")
                        continue
                
                filtered.append(line)
            processed["content"] = "\n".join(filtered)
        return processed

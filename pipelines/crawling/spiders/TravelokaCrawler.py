import logging
from typing import List, Optional, Dict, Any
from pipelines.crawling.utils import load_js
from pipelines.crawling.base.PipelineBase import BasePipelineCrawler

logger = logging.getLogger("TravelokaCrawler")


class TravelokaCrawler(BasePipelineCrawler):
    def __init__(
        self,
        place_name: str,
        city_data: Dict = None,
        topic_keyword: str = "general_scan",
        lang_code: str = "vi",
        **kwargs
    ):
        super().__init__(**kwargs)
        self.place_name = place_name
        self.city_data = city_data or {}
        self.topic_keyword = topic_keyword
        self.lang_code = lang_code
        self.webpage_name = "traveloka"
        self.browser_cfg.enable_stealth = True

    def get_domain_name(self) -> str:
        return self.webpage_name

    def use_semantic_filter(self) -> bool:
        return True

    def get_embedding_query(self) -> str:
        return f"Thông tin du lịch, tour, khách sạn, vé máy bay tại {self.place_name}"

    def get_specific_keywords(self) -> List[str]:
        return [
            self.place_name,
            "khách sạn",
            "tour",
            "vé máy bay",
            "trải nghiệm",
            "du lịch",
            "địa điểm",
            "vui chơi",
            "ăn uống"
        ]

    def get_js_actions(self) -> Optional[str]:
        return load_js()

    def get_css_selectors(self) -> List[str]:
        return [
            '[data-testid="view_articleWrapper"]',
            '[data-testid="ctr_tourItinerary"]',
            '#itinerary-section',
            '#ticketSummaryItinerary',
            '[data-testid="view_articleTableContent"]',
        ]

    def get_excluded_selectors(self) -> List[str]:
        return [
            "header",
            "footer",
            "nav",
            "aside",
            '[data-testid="header-container"]',
            '[data-testid="desktop-header"]',
            '[data-testid="mobile-header"]',
            '[role="banner"]',
            '.tv-header',
            '[data-testid="footer-container"]',
            '.tv-footer',
            '.footer-content',
            '.partner-payment-section',
            '.download-app-section',
            '[data-testid="login-register-button"]',
            '[data-testid="currency-language-popover"]',
            '[data-testid="user-profile-menu"]',
            '[data-testid="search-filter-container"]',
            '.search-filter-wrapper',
            '.css-1dbjc4n[style*="position: sticky"]',
            "svg",
            ".promoBanner",
            ".newsletter",
            ".breadcrumbs",
            "script", "style", "iframe",
            # Ảnh icon/logo/quảng cáo (cha header/footer/... đã exclude ở trên)
            "img[src*='icon']",
            "img[src*='logo']",
            "img[src*='badge']",
            "img[src*='sprite']",
            "img[src*='imageresource']",
            "img[src*='.svg']",
            ".ad img",
            ".advertisement img",
            ".sponsor img",
            ".promo img",
            "[class*='ad'] img",
            "[class*='sponsor'] img",
            "[class*='promo'] img",
            "[id*='ad'] img",
            "[class*='icon'] img",
            "[class*='logo'] img",
            "[class*='badge'] img",
            "[class*='button'] img",
            "[class*='arrow'] img",
            "[class*='chevron'] img"
        ]

    def get_place_patterns(self) -> List[str]:
        if "place_patterns" in self.city_data:
            return self.city_data["place_patterns"]
        slug = self.place_name.lower().replace(" ", "-")
        return [
            f"*{slug}*",
        ]

    def process_item(self, result):
        if "/vi-vn/" not in result.url:
            logger.warning(f"Skipped non-Vietnamese URL: {result.url}")
            return None

        processed = super().process_item(result)
        if not processed:
            return None
        
        # Filter ảnh không mong muốn trong markdown content
        content = processed.get('content', '')
        if content:
            # Loại bỏ các dòng markdown chứa ảnh icon/logo/quảng cáo
            lines = content.split('\n')
            filtered_lines = []
            for line in lines:
                # Bỏ qua các dòng chứa ảnh không mong muốn
                if '![' in line and '](' in line:
                    img_url = line.split('](')[1].split(')')[0] if '](' in line else ''
                    img_url_lower = img_url.lower()
                    # Giữ lại ảnh tour, loại bỏ icon/logo/quảng cáo
                    if any(keyword in img_url_lower for keyword in [
                        'icon', 'logo', 'badge', 'sprite', 'imageresource', 
                        '.svg', 'ad', 'sponsor', 'promo', 'button', 'arrow'
                    ]):
                        logger.debug(f"Filtered out image: {img_url[:50]}...")
                        continue
                filtered_lines.append(line)
            processed['content'] = '\n'.join(filtered_lines)
        
        return processed
import os
import json
from typing import List, Optional, Dict, Any
from pipelines.crawling.base.PipelineBase import BasePipelineCrawler


class VietnamCoracleCrawler(BasePipelineCrawler):
    def __init__(self, place_name: str, city_data: Dict = None, **kwargs):
        super().__init__(**kwargs)
        self.place_name = place_name
        self.city_data = city_data or {}
        self.webpage_name = "vietnamcoracle"
        self.results_data = []

    def get_domain_name(self) -> str:
        return self.webpage_name

    def get_css_selectors(self) -> List[str]:
        # Vietnam Coracle thường dùng các class bài viết chuẩn WordPress
        return [
            '.entry-content',
            '.post-content',
            'article.post',
            '.entry-inner',
            '#content'
        ]

    def get_place_patterns(self) -> List[str]:
        # Khóa link theo địa danh để không cào lan sang các vùng khác
        if "place_patterns" in self.city_data:
            return self.city_data["place_patterns"]

        slug = self.place_name.lower().replace(" ", "-")
        # Trang này thường dùng slug tên địa danh trực tiếp trong URL
        return [f"*{slug}*", "*/category/vietnam/*"]

    def get_embedding_query(self) -> str:
        # AI tập trung lấy nội dung bài review, hướng dẫn du lịch
        return f"Các bài viết review du lịch, hướng dẫn đường đi và trải nghiệm tại {self.place_name}"

    def get_specific_keywords(self) -> List[str]:
        return [self.place_name, "guide", "review", "travel", "motorcycle", "stay"]

    def get_excluded_selectors(self) -> List[str]:
        # Loại bỏ sidebar, comment và footer để lấy Markdown sạch
        return [
            ".sidebar",
            "#comments",
            ".author-bio",
            ".sharedaddy",
            ".jp-relatedposts",
            ".footer-widgets",
            "header.entry-header"
        ]

    def get_js_action(self) -> Optional[str]:
        # Vietnam Coracle tải khá nhanh, chủ yếu cần cuộn để load ảnh lười (lazy-load)
        return """
        async () => {
            window.scrollBy(0, 1000);
            await new Promise(r => setTimeout(r, 500));
            window.scrollBy(0, 2000);
            await new Promise(r => setTimeout(r, 500));
        };
        """

    def _generate_filename(self, stt: Any, ext: str) -> str:
        topic = getattr(self, 'topic_keyword', 'general_scan')
        return f"{self.place_name}_{topic}_{self.webpage_name}_en_{stt}.{ext}"

    def save_item_to_disk(self, data: Dict, folder: str):
        # Lưu file theo cấu trúc dự án Travel-Lung-Tung
        path = os.path.join(folder, self.get_domain_name(), self.place_name)
        os.makedirs(path, exist_ok=True)

        stt = len(self.results_data) + 1
        filename_md = self._generate_filename(stt, "md")

        with open(os.path.join(path, filename_md), "w", encoding="utf-8") as f:
            f.write(data['content'])

        json_meta = {
            "stt": stt,
            "filename": filename_md,
            "url": data.get("url"),
            "source": data.get("source")
        }
        self.results_data.append(json_meta)
        print(f"Saved content: {filename_md}")

        data['stt'] = stt
        data['filename'] = filename_md
        self.results_data.append(data)

    async def execute(self, start_url: str, output_folder: str = "../data"):
        await super().execute(start_url, output_folder)
        if self.results_data:
            summary_path = os.path.join(output_folder, "crawled_data", self.get_domain_name(), self.place_name)
            os.makedirs(summary_path, exist_ok=True)

            filename_list = self._generate_filename("List", "json")
            with open(os.path.join(summary_path, filename_list), "w", encoding="utf-8") as f:
                json.dump(self.results_data, f, indent=4, ensure_ascii=False)
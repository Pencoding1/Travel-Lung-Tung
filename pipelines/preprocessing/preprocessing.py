import re

from pipelines.preprocessing.base.PipelineBase import BasePreprocessor
import json
from markdownify import markdownify as md
from config.exceptions import IntentedNotImplementedException

class VietnamTravelPreprocessor(BasePreprocessor):...

class VietravelPreprocessor(BasePreprocessor):...

class VNTravelPreprocessor(BasePreprocessor):...

class TravelokaPreprocessor(BasePreprocessor):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

    def filter(self, text: str) -> str:
        return ""
    
    def parse(self, content, crawl_type: str):

        # 1. Hàm tiện ích làm sạch HTML thừa thành Markdown
        def clean_markdown(html_data):
            if not html_data: return html_data
            
            # Xử lý nếu data là một mảng (ví dụ: mảng các đoạn HTML)
            if isinstance(html_data, list):
                return [clean_markdown(i) for i in html_data]
            
            # Xử lý nếu data là một dict
            if isinstance(html_data, dict):
                return {k: clean_markdown(v) for k, v in html_data.items()}

            # Tiến hành parse nếu chắc chắn nó là chuỗi (string)
            if isinstance(html_data, str):
                markdown_text = md(html_data, heading_style="ATX")
                lines = [line.strip() for line in markdown_text.splitlines() if line.strip() != ""]
                text = "\n".join(lines)
                text = re.sub(r'(?m)^(#+\s.*)$', r'\n\n\1\n\n', text)
                text = re.sub(r'(?m)^(!\[.*\]\(.*\))$', r'\n\n\1\n\n', text)
                text = re.sub(r'\n{3,}', '\n\n', text)
                return text.strip()
            
            return html_data

        # 2. Thuật toán Đệ quy: Tự động tìm và chuyển đổi Markdown ở mọi ngóc ngách
        def convert_html_to_md_recursive(data):
            if isinstance(data, dict):
                for k, v in data.items():
                    if k in ["modal_contents", "modal_content", "review_block", "reviews_block", "things_to_know", "content", "seo_article", "clean_html"]: 
                        data[k] = clean_markdown(v)
                    else:
                        data[k] = convert_html_to_md_recursive(v)
            elif isinstance(data, list):
                return [convert_html_to_md_recursive(i) for i in data]
            return data

        # Đảm bảo dữ liệu đầu vào là JSON object
        if not content:
            return {"error": "Nội dung trống."}
        
        data = content
        if isinstance(content, str):
            try:
                data = json.loads(content)
            except json.JSONDecodeError:
                return {"error": "Lỗi định dạng JSON."}

        # Nếu là danh sách, xử lý từng item
        items = data if isinstance(data, list) else [data]
        parsed_items = []

        for item in items:
            if not isinstance(item, dict): continue
            
            # BƯỚC A: Giải nén tất cả các chuỗi JSON lồng nhau từ CẢ 3 NHÁNH (Activities, Explore, Destinations)
            json_fields = [
                "Product_schema", 
                "FAQ_json", 
                "all_ticket_details", 
                "parsed_blog_data", 
                "parsed_destination_data"
            ]
            for field in json_fields:
                if field in item and isinstance(item[field], str):
                    try: 
                        item[field] = json.loads(item[field])
                    except Exception as e:
                        # Thêm log để biết chính xác trường nào đang bị kẹt JSON
                        print(f"[CẢNH BÁO] Không thể giải nén JSON cho trường '{field}': {e}")
            
            # BƯỚC B: Kích hoạt chổi quét đệ quy để dọn dẹp HTML sang Markdown
            item = convert_html_to_md_recursive(item)
                
            parsed_items.append(item)

        # Trả về dict nếu chỉ có 1 item, trả list nếu có nhiều
        return parsed_items[0] if len(parsed_items) == 1 else parsed_items

    def clean(self, text: str) -> str:
        return ""

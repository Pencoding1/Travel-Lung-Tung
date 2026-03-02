from pipelines.crawling.interfaces.IExtractor import IExtractorStrategy
from config.crawling_cofig import ExtractorConfig
from config.exceptions import IntentedNotImplementedException

from typing import Optional, Tuple, Dict, List
from pathlib import Path

import json
import logging


class TourExtractor(IExtractorStrategy):
    def __init__(self, config: Optional[ExtractorConfig]=None):
        self.cfg = config if config else ExtractorConfig()
        self.root_dir = Path(__file__).parent.parent.parent.parent / "secrets"
        self.logger = logging.getLogger(self.__class__.__name__)

    def load_schema(self) -> Optional[Tuple[Optional[Dict], Optional[Dict]]]:
        css_schema_path = self.root_dir / "schemas" / "css" / self.cfg.domain.value/ "tour" / "tour_ticket_schema.json"
        xpath_schema_path = self.root_dir / "schemas" / "xpath" / self.cfg.domain.value / "tour" / "tour_ticket_schema.json"
        if not (css_schema_path.is_file() or xpath_schema_path.is_file()):
            self.logger.warning(f"No schema has found at.\nCSS Schema: {css_schema_path}\nXpath Schema:{xpath_schema_path}")
            return None

        try:
            xpath_json = None
            css_json = None

            if xpath_schema_path.is_file():
                xpath_content = xpath_schema_path.read_text(encoding="utf-8")
                xpath_json = json.loads(xpath_content)
                
            if css_schema_path.is_file():
                css_content = css_schema_path.read_text(encoding="utf-8")
                css_json = json.loads(css_content)
            
            return (xpath_json, css_json)
            
        except json.JSONDecodeError as e:
            print(f"Lỗi định dạng JSON tại domain {self.cfg.domain.value}: {e}")
            return None
        
    def load_js(self, files: List[str]) -> List[str]:
        scripts = []
        
        for file_name in files:
            script_path = self.root_dir / "js_codes" / self.cfg.domain.value / "tour" / file_name
            if not script_path.is_file():
                print(f"Cảnh báo: Bỏ qua file JS không tồn tại - '{file_name}' (Domain: {self.cfg.domain})")
                print(f"{script_path}")
                continue
            try:
                script_content = script_path.read_text(encoding="utf-8")
                scripts.append(script_content)
            except Exception as e:
                print(f"Lỗi khi đọc file JS '{file_name}': {e}")
        return scripts
    
    def parse_clean(self, raw_data):
        raise IntentedNotImplementedException()
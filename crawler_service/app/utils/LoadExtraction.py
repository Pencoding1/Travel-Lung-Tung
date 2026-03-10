import json
import logging

from app.core.config.settings import ExtractorSettings
from typing import Optional, Dict, List

class LoadExtractionScript:
    def __init__(self, config: ExtractorSettings, name:str) -> None:
        self.cfg = config
        self.logger = logging.getLogger(self.__class__.__name__)
        self.name = name

    def load_schema(self) -> Optional[Dict]:
        css_schema_path = self.cfg.root_dir / "crawl_schemas" / "css" / self.cfg.domain.value/ self.name
        xpath_schema_path = self.cfg.root_dir / "crawl_schemas" / "xpath" / self.cfg.domain.value / self.name
        
        results = dict()

        json_schema_path = next(css_schema_path.glob("*.json"), None)
        if not json_schema_path:
            json_schema_path = next(xpath_schema_path.glob("*.json"), None)
            results['type'] = "xpath"
        else:
            results['type'] = "css"

        if not json_schema_path:
            self.logger.warning(f"No schema has found at.\nCSS Schema: {css_schema_path}\nXpath Schema:{xpath_schema_path}")
            return None

        try:
            # Only one json schema per page.
            json_schema = json.loads(json_schema_path.read_text(encoding="utf-8"))
            results["schema"] = json_schema
            return results
        
        except json.JSONDecodeError as e:
            self.logger.error(f"Lỗi định dạng JSON tại domain {self.cfg.domain.value}: {e}")
            return None
        
    def load_js(self) -> List[str]:
        scripts = []
        script_dir = self.cfg.root_dir / "js_codes" / self.cfg.domain.value / self.name
        for path in script_dir.glob("*.js"):
            try:
                script_content = path.read_text(encoding="utf-8")
                scripts.append(script_content)
            except Exception as e:
                self.logger.error(f"Lỗi khi đọc file JS '{path}': {e}")
        return scripts
    
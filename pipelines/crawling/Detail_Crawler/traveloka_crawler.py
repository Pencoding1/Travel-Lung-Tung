from typing import Any, Dict, List, Optional

from crawl4ai import CrawlerRunConfig, DefaultMarkdownGenerator, BrowserConfig

from config.crawling_cofig import CrawlerGlobalConfig
from utils.crawling_utils import traveloka_vehicle_extractor, remover
from pipelines.crawling.base.detail_crawler import baseDetailCrawler



class Traveloka(baseDetailCrawler):
    def __init__(self, cfg: Optional[CrawlerGlobalConfig] = None,
                 crawler_config: Optional[CrawlerRunConfig]= None,
                 markdown_creator: Optional[DefaultMarkdownGenerator] = None, 
                 browser_config: Optional[BrowserConfig] = None):
        super().__init__(cfg, crawler_config, markdown_creator, browser_config)
    
    def get_css_selectors(self) -> List[str]:...
    def get_domain_name(self) -> str:...
    def get_place_patterns(self) -> List[str]:...
    def get_specific_keywords(self) -> List[str]:...

    def init_js(self, 
                scripts: Optional[List[str] | str]=None,
                use_default_script: bool = True, 
                excluded_xpath: str | List[str] | None = None, 
                dynamic_extraction_params: Dict[str, Any] | None = None) -> Optional[List[str] | str]:
                
        js_scripts = []
        if use_default_script:
            if excluded_xpath:
                cleanup_target_script = remover(xpath=excluded_xpath)
            else:
                cleanup_target_script = remover()

            if dynamic_extraction_params:
                dynamic_extraction_script = traveloka_vehicle_extractor(xpaths=dynamic_extraction_params)
            else:
                dynamic_extraction_script = traveloka_vehicle_extractor()

            js_scripts.extend([cleanup_target_script, dynamic_extraction_script])
            
            if scripts: 
                if isinstance(scripts, str):
                    js_scripts.append(scripts)
                else:
                    js_scripts.extend(scripts)
    
            return js_scripts    
        else:
            return scripts
        

async def test():
    import json
    from crawl4ai import CrawlResult
    START_URL = "https://www.traveloka.com/vi-vn/destination/area/ho-chi-minh-city-10009794"
    crawler = Traveloka() # type: ignore
    
    # 1. Run the crawler 
    # (init_js is called internally by your base class logic, or explicitly if you override run)
    results:CrawlResult = await crawler.crawl(START_URL)  # type: ignore

    if results.success:
        # Save Markdown
        if results.markdown:
            with open("test.md", mode='w', encoding='utf-8') as f:
                f.write(results.markdown.raw_markdown)
        else:
            print("No result has found")
            return
        
        # 2. Extract Data from JS Execution
        js_data = results.js_execution_result or {}
        final_json_data = {}

        # We expect a list of results because we sent a list of scripts [Cleanup, Extractor]
        if "results" in js_data and isinstance(js_data["results"], list):
            # We want the result of the SECOND script (Index 1)
            if len(js_data["results"]) > 1:
                extraction_output = js_data["results"][1]
                
                if extraction_output.get("success"):
                    final_json_data = extraction_output.get("data", {})
                else:
                    print(f"Extraction Script Error: {extraction_output.get('error')}")
            else:
                # Fallback: If only 1 script ran or structure is unexpected
                final_json_data = js_data["results"][0]
        else:
            final_json_data = js_data

        # Save JSON
        with open("extracted_buttons.json", mode='w', encoding='utf-8') as f:
            json.dump(final_json_data, f, indent=4, ensure_ascii=False)
            
        print(f"Saved {len(final_json_data)} items to extracted_buttons.json")


if __name__ == "__main__":
    import asyncio
    asyncio.run(test())
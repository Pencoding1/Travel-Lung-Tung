import json

from loguru import logger
from datetime import datetime
from copy import deepcopy
from typing import List, Optional, Tuple

from dateutil import parser
from bs4 import BeautifulSoup
from readability import Document

class ContentProcessor:
    def __init__(self, html_content:str, parser:str="lxml") -> None:
        self.soup = BeautifulSoup(html_content, parser)
        self.html_content = html_content

    def extract_main_content(self) -> Tuple[str, str]:
        main_tag = None
        final_node = None
        content_candidates = [
            'article', 'main',
            {
                'class_': 'post-content'
            }, 
            {
                'class_': 'entry-content'
            },
            {
                'id': 'content'
            },
            {
                'id': 'main'
            }
        ]
        script_tags = ["script", "style", "iframe", "noscript", "aside", "nav", "footer", "header"]
        title = self.soup.title.string if self.soup.title and self.soup.title.string else None
        
        if title is None:
            h1_tag = self.soup.find("h1")
            title = h1_tag.get_text() if h1_tag else "No Title"

        try:
            doc = Document(self.html_content)
            readability_content = doc.summary()
            if len(readability_content) > 200:
                return title, readability_content
        except Exception as e:
            logger.error(f"Extracting error: {e}")

        for selector in content_candidates:
            if isinstance(selector, str):
                main_tag = self.soup.find(selector)
            else:
                main_tag = self.soup.find('div', **selector)
            if main_tag: break
        
        if main_tag:
            final_node = deepcopy(main_tag)
        elif self.soup.body:
            final_node = deepcopy(self.soup.body)
        else:
            return title, self.html_content 
        
        for tag_type in script_tags:
            for element in final_node.find_all(tag_type):
                element.decompose()
        
        return title, str(final_node)

    def extract_images(self, limit: int = 10) -> List[str]:
        logger.info("Extracting Image...")
        img_tags = self.soup.find_all('img')
        valid_images = [img for i, img in enumerate(img_tags) if i < limit]        
        final_links = []

        for img in valid_images:
            src = img.get('data-src') or img.get('src')
            if src:
                src = src[0] if isinstance(src, list) else src
                if src.startswith('//'):
                    final_links.append("https:" + src)
        logger.info("Extracting Image Completed.")
        return final_links                
                

    def extract_published_date(self) -> Optional[datetime]:
        scripts = self.soup.find_all('script', type='application/ld+json')
        
        META_SELECTORS = "meta[property='article:published_time'], meta[property='og:published_time'], meta[itemprop='datePublished']"
        meta_tag = self.soup.select_one(META_SELECTORS)
        time_tag = self.soup.find("time")
        class_tag = self.soup.select_one(".date, .post-date, .published")

        for script in scripts:
            if script.string:
                try:
                    data = json.loads(script.string)
                    candidates = data if isinstance(data, list) else [data]
                    for item in candidates:
                        date_str = item.get('datePublished') or item.get('dateCreated') or item.get('uploadDate')
                        if date_str: return parser.parse(str(date_str).strip())
                except Exception as e:
                    logger.error(f"Parsing date JSON-LD Error: {e}")


        if meta_tag and meta_tag.get("content"):
            try:
                return parser.parse(str(meta_tag["content"]).strip())
            except Exception as e:
                logger.error(f"Parsing date Meta tag error: {e}")

        if time_tag:
            val = time_tag.get("datetime") or time_tag.get_text()
            try:
                return parser.parse(str(val).strip())
            except Exception as e:
                logger.error(f"Parsing date Time tag: {e}")

        if class_tag:
            try:
                return parser.parse(class_tag.get_text().strip(), fuzzy=True)
            except Exception as e:
                logger.error(f"Parsing date Class tag: {e}")

        return None
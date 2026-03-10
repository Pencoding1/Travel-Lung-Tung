import traceback

from fastapi import FastAPI, Depends, APIRouter, HTTPException
from pydantic import HttpUrl, TypeAdapter, ValidationError

from app.core.config.settings import (
    LoadPipelineSetting,
    ExtractorSettings,
    DiscoverSettings,
    CrawlerSetting,
    ExtractPipelineSetting,
    ParserSettings,
    AppSettings,
    PARENT
)

from app.core.security import verify_service_token
from app.models.CrawlRecord import CrawlPayload
from app.pipelines.crawling.crawling import Crawler
from travel_shared.schemas import CACHE_MODE
from travel_shared.utils.logging_setup import setup_logging

logger = setup_logging(service_name="crawler", log_dir=PARENT / "logs")

url_adapter = TypeAdapter(HttpUrl)
app = FastAPI(
    title="Data Producer - Crawler Service",
    description="Agentic skill and bulk extraction service for travel data.",
)

async def crawl(url: str):
    load = LoadPipelineSetting(
        crawler_cfg=CrawlerSetting(),
        extractor_cfg=ExtractorSettings(),
        discover_cfg=DiscoverSettings()
    )
    extract = ExtractPipelineSetting(
        pipeline_cfg=ParserSettings()
    )
    app_settings = AppSettings(
        load_settings=[load],
        extract_settings=[extract],
    )
    try:
        validated_url = url_adapter.validate_python(url)
    except ValidationError:
        logger.error("Invalid url.")
        return None
        
    crawler = Crawler(app_settings, seed_url=url)
    crawler.cfg.load_settings[0].cache_mode=CACHE_MODE.WRITE
    return await crawler.pipeline()

@app.get("/")
async def health_check():
    return {"status": "Crawler Service is successfully running!"}

protected_router = APIRouter(
    prefix="/api/v1",
    dependencies=[Depends(verify_service_token)]
)

@protected_router.post("/crawl")
async def execute_crawl(payload: CrawlPayload):
    try:
        # Await the crawl helper
        result = await crawl(payload.target_url)
        if result:
            return {"status": "success", "result": result}
        return {"status": "failed", "result": {}}
    except Exception as e:
        logger.error(f"Crawl failed: {str(e)}")
        print(traceback.format_exc()) 
        raise HTTPException(status_code=500, detail=str(e))

app.include_router(protected_router)
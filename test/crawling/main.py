import json

from unittest.mock import MagicMock, AsyncMock, patch, mock_open
from datetime import datetime

from pipelines.crawling.Crawling import AgenticCrawler
from db.models.Raws import RawTripInfo

import pytest
import json
from unittest.mock import MagicMock, AsyncMock, patch, mock_open
from datetime import datetime

@pytest.fixture
def mock_firestore():
    """Mocks the Firestore Repository."""
    return MagicMock()

@pytest.fixture
def mock_openai():
    """Mocks the OpenAI Async Client."""
    client = MagicMock()
    client.chat.completions.create = AsyncMock()
    return client

@pytest.fixture
def crawler(mock_firestore, mock_openai):
    """
    Initializes the crawler with mocked dependencies.
    We patch the repository and client inside __init__.
    """
    with patch('pipelines.crawling.Crawling.FireStoreRepository', return_value=mock_firestore), \
         patch('pipelines.crawling.Crawling.AsyncOpenAI', return_value=mock_openai):
        
        crawler_instance = AgenticCrawler()
        return crawler_instance

# --- TESTS ---

@pytest.mark.asyncio
async def test_scrape_url_corrected_success(crawler):
    """Test successful scraping flow using Playwright mock."""
    test_url = "https://example.com/travel"
    html_content = "<html><body><h1>Trip to Paris</h1></body></html>"
    
    # 1. Mock Playwright Context Manager
    with patch('pipelines.crawling.Crawling.async_playwright') as mock_playwright:
        # Setup the chain: async_playwright() -> p -> browser -> context -> page
        mock_p = AsyncMock()
        mock_browser = AsyncMock()
        mock_context = AsyncMock()
        mock_page = AsyncMock()
        
        # Determine what happens when we enter the 'async with' block
        mock_playwright.return_value.__aenter__.return_value = mock_p
        mock_p.chromium.launch.return_value = mock_browser
        mock_browser.new_context.return_value = mock_context
        mock_context.new_page.return_value = mock_page
        
        # Mock page content
        mock_page.content.return_value = html_content
        
        # 2. Mock ContentProcessor (so we don't need real HTML parsing logic)
        with patch('pipelines.crawling.Crawling.ContentProcessor') as MockProcessor:
            processor_instance = MockProcessor.return_value
            processor_instance.extract_main_content.return_value = ("Trip to Paris", "<div>Raw HTML</div>")
            processor_instance.extract_published_date.return_value = datetime(2023, 1, 1)
            processor_instance.extract_images.return_value = ["img1.jpg", "img2.jpg"]

            # 3. Run Logic
            result = await crawler._scrape_url_corrected(test_url)

            # 4. Assertions
            assert result is not None
            assert isinstance(result, RawTripInfo)
            assert result.title == "Trip to Paris"
            assert result.source_url == test_url
            assert len(result.images) == 2
            
            # Verify Playwright calls
            mock_page.goto.assert_awaited_with(test_url, wait_until="domcontentloaded", timeout=60000)
            mock_browser.close.assert_awaited_once()

@pytest.mark.asyncio
async def test_scrape_url_failure(crawler):
    """Test scraping when Playwright throws an error."""
    with patch('pipelines.crawling.Crawling.async_playwright') as mock_playwright:
        mock_p = AsyncMock()
        mock_playwright.return_value.__aenter__.return_value = mock_p
        # Simulate browser launch failure
        mock_p.chromium.launch.side_effect = Exception("Browser crashed")

        result = await crawler._scrape_url_corrected("http://fail.com")
        
        # Should return None and log error (not crash)
        assert result is None

@pytest.mark.asyncio
async def test_analyze_with_ai_success(crawler):
    """Test AI analysis with mocked file read and OpenAI response."""
    # Setup Input Data
    raw_info = RawTripInfo(
        ID="123", title="Test", summary="", raw_text="content", 
        doc_type="html", sourceUrl="http://url", crawled_at=datetime.now()
    )

    # Mock JSON response from AI
    ai_response_content = json.dumps({
        "summary": "This is a generated summary",
        "metadata": {"price": "100$"}
    })
    
    # Mock OpenAI return structure
    mock_message = MagicMock()
    mock_message.content = ai_response_content
    mock_choice = MagicMock()
    mock_choice.message = mock_message
    mock_response = MagicMock()
    mock_response.choices = [mock_choice]
    
    crawler.ai_client.chat.completions.create.return_value = mock_response

    # Mock File Open (reading prompt.json)
    mock_prompt_file = json.dumps({
        "0.1.0": {"prompt": {"role": "system", "instruction": "analyze this"}}
    })

    with patch("builtins.open", mock_open(read_data=mock_prompt_file)):
        with patch("json.load", return_value=json.loads(mock_prompt_file)): # Explicitly mock json.load for safety
            
            # Run Logic
            result_dict = await crawler._analyze_with_ai(raw_info)

            # Assertions
            assert result_dict["summary"] == "This is a generated summary"
            assert result_dict["metadata"]["price"] == "100$"
            crawler.ai_client.chat.completions.create.assert_awaited_once()

@pytest.mark.asyncio
async def test_analyze_with_ai_file_not_found(crawler):
    """Test behavior when prompt file is missing."""
    raw_info = RawTripInfo(
        ID="123", title="Test", summary="", raw_text="content", 
        doc_type="html", sourceUrl="http://url", crawled_at=datetime.now()
    )

    # Simulate FileNotFoundError
    with patch("builtins.open", side_effect=FileNotFoundError):
        # The code catches the error, likely fails to load prompt, 
        # and eventually hits the exception block returning original data
        result = await crawler._analyze_with_ai(raw_info)
        
        # Should return original data (dumped as dict)
        assert result["ID"] == "123"
        # Ensure it didn't crash
        assert isinstance(result, dict)

@pytest.mark.asyncio
async def test_save_to_database(crawler):
    """Test saving list of items to Firestore."""
    items = [
        RawTripInfo(ID="1", title="A", summary="", raw_text="", doc_type="html", sourceUrl="", crawled_at=datetime.now()),
        RawTripInfo(ID="2", title="B", summary="", raw_text="", doc_type="html", sourceUrl="", crawled_at=datetime.now())
    ]
    
    await crawler._save_to_database(items)
    
    # Assert repository add was called twice
    assert crawler.firestore_repo.add.call_count == 2
    # Verify the argument passed was one of the items
    crawler.firestore_repo.add.assert_any_call(items[0])

@pytest.mark.asyncio
async def test_process_workflow_integration(crawler):
    """
    Test the full flow: Scrape -> Analyze -> Parse -> Save.
    We mock the internal methods to test the orchestration.
    """
    target_url = "http://test.com"
    
    # Mock return values for internal steps
    mock_trip_info = RawTripInfo(ID="1", title="T", summary="", raw_text="", doc_type="html", sourceUrl="", crawled_at=datetime.now())
    mock_analyzed_dict = mock_trip_info.model_dump(by_alias=True)
    mock_analyzed_dict['summary'] = "AI Summary"

    # Patch internal methods of the *instance*
    with patch.object(crawler, '_scrape_url_corrected', return_value=mock_trip_info) as mock_scrape, \
         patch.object(crawler, '_analyze_with_ai', return_value=mock_analyzed_dict) as mock_analyze, \
         patch.object(crawler, '_save_to_database', new_callable=AsyncMock) as mock_save:

        # Run Workflow
        await crawler._process_workflow([target_url])

        # Assertions
        mock_scrape.assert_awaited_with(target_url)
        mock_analyze.assert_awaited_with(mock_trip_info)
        
        # Parse is synchronous, so it runs implicitly. 
        # Verify save was called with a list containing the parsed object
        assert mock_save.called
        args, _ = mock_save.call_args
        saved_list = args[0]
        assert saved_list[0].summary == "AI Summary"
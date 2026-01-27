from pipelines.crawling.Crawling import AgenticCrawler
from unittest.mock import MagicMock, AsyncMock, patch, mock_open
import pytest

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
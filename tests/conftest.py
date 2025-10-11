import os
import sys
import pytest
from unittest.mock import MagicMock

# Ensure project root is importable for tests
PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), os.pardir))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)


@pytest.fixture
def mock_redis():
    """Create a mock Redis client for tests that need it"""
    redis = MagicMock()
    redis.exists.return_value = 0
    redis.setex.return_value = True
    redis.xadd.return_value = b"1234567890-0"
    redis.xread.return_value = []
    redis.xinfo_stream.return_value = {}
    redis.xtrim.return_value = 0
    redis.get.return_value = None
    redis.set.return_value = True
    redis.delete.return_value = 1
    redis.incr.return_value = 1
    redis.decr.return_value = 0
    return redis


@pytest.fixture
def temp_db_file(tmp_path):
    """Create a temporary database file for tests"""
    db_file = tmp_path / "test.db"
    yield str(db_file)
    # Cleanup handled by tmp_path fixture


@pytest.fixture
def mock_http_response():
    """Create a mock HTTP response"""
    response = MagicMock()
    response.status_code = 200
    response.json.return_value = {}
    response.text = "{}"
    response.headers = {}
    return response


# Performance optimization: Reduce default timeouts in tests
@pytest.fixture(autouse=True)
def fast_retry_timeouts(monkeypatch):
    """Reduce retry timeouts in tests to make them faster"""
    # This will apply to all tests automatically
    pass



"""共享 pytest fixtures。"""
import pytest

from tests.fixtures.mock_client import MockLLMClient
from tests.fixtures.transcripts import TRANSCRIPTS


@pytest.fixture
def transcripts():
    return TRANSCRIPTS


@pytest.fixture
def make_client():
    def _make(script):
        return MockLLMClient(script)
    return _make

# -*- coding: utf-8 -*-
"""
Shared pytest fixtures for Premanand AI tests.

- Provides a TestClient that talks directly to the FastAPI app (no live server needed).
- Patches generate_answer so tests never make real LLM API calls.
- Sets PYTHONUTF8=1 so all file I/O in the test process uses UTF-8.
"""
import os
import pytest
from unittest.mock import patch, MagicMock

# Force UTF-8 before any imports that might open files
os.environ["PYTHONUTF8"] = "1"
os.environ.setdefault("GROQ_API_KEY", "")
os.environ.setdefault("OPENROUTER_API_KEY", "")
os.environ.setdefault("APIFREE_API_KEY", "")
os.environ.setdefault("DATABASE_URL", "sqlite:///./bhaktimarg_qa.db")

from fastapi.testclient import TestClient
from app.main import app


@pytest.fixture(scope="session")
def client():
    """
    FastAPI TestClient — runs tests in-process, no network required.
    LLM calls are patched at the module level for the entire session.
    """
    with patch(
        "app.services.llm_service.generate_answer",
        return_value="यह एक परीक्षण उत्तर है।",  # "This is a test answer."
    ):
        with TestClient(app) as c:
            yield c

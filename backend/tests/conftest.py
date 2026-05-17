from collections.abc import Generator
import os

import pytest
from fastapi.testclient import TestClient

os.environ.setdefault("APP_AUTONOMOUS_LIFE_ENABLED", "false")

from app.main import app


@pytest.fixture()
def client() -> Generator[TestClient, None, None]:
    with TestClient(app) as test_client:
        yield test_client

import os
import tempfile
from pathlib import Path

import pytest

_tmp = Path(tempfile.mkdtemp(prefix="ea-test-"))
# TEST_DATABASE_URL runs the suite against Postgres (an empty database); otherwise a fresh SQLite file.
os.environ["DATABASE_URL"] = os.environ.get("TEST_DATABASE_URL") or f"sqlite+aiosqlite:///{(_tmp / 'test.db').as_posix()}"
os.environ["UPLOAD_DIR"] = str(_tmp / "uploads")
os.environ["ESCALATION_INTERVAL_S"] = "0"
os.environ["ENV"] = "development"

from fastapi.testclient import TestClient  # noqa: E402

from app.main import app  # noqa: E402


@pytest.fixture(scope="session")
def client():
    with TestClient(app) as c:
        yield c


class As:
    """Call the API as a given employee number."""

    def __init__(self, client, employee_no):
        self.c = client
        self.h = {"X-EA-User": employee_no}

    def get(self, url, **kw):
        return self.c.get(url, headers=self.h, **kw)

    def post(self, url, json=None, **kw):
        return self.c.post(url, json=json, headers=self.h, **kw)

    def patch(self, url, json=None):
        return self.c.patch(url, json=json, headers=self.h)

    def put(self, url, json=None):
        return self.c.put(url, json=json, headers=self.h)

    def delete(self, url):
        return self.c.delete(url, headers=self.h)


@pytest.fixture(scope="session")
def users(client):
    names = {
        "admin": "EA-0001", "assistant": "EA-0002", "carlo": "EA-0101", "dana": "EA-0102",
        "eli": "EA-0103", "fe": "EA-0104", "naresh": "EA-0201", "coo": "EA-0202",
        "jasmine": "EA-0203", "mira": "EA-0204", "malhou": "EA-0205", "gio": "EA-0301", "hana": "EA-0302",
    }
    return {k: As(client, v) for k, v in names.items()}

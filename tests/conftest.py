import sys
from pathlib import Path

from dotenv import load_dotenv


def pytest_configure() -> None:
    project_root = Path(__file__).resolve().parents[1]
    if str(project_root) not in sys.path:
        sys.path.insert(0, str(project_root))
    load_dotenv()

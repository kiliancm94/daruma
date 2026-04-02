import os
from pathlib import Path

DATA_DIR = Path(
    os.environ.get("DARUMA_DATA_DIR", Path(__file__).parent.parent / "data")
)
DB_PATH = DATA_DIR / "automations.db"
PORT = int(os.environ.get("DARUMA_PORT", "8080"))

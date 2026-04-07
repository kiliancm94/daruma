import os
from pathlib import Path

DATA_DIR = Path(
    os.environ.get("DARUMA_DATA_DIR", Path(__file__).parent.parent / "data")
)
DB_PATH = DATA_DIR / "automations.db"
PORT = int(os.environ.get("DARUMA_PORT", "9090"))
HOST = os.environ.get("DARUMA_HOST", "127.0.0.1")
HOSTNAME = "daruma.localhost"

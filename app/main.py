# app/main.py
import uvicorn
import logging
import sys
from .config import settings

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)],
)

logger = logging.getLogger("local_search.main")


def run():
    uvicorn.run("app.api:app", host=settings.API_HOST, port=settings.API_PORT, log_level="info", reload=False)


if __name__ == "__main__":
    run()

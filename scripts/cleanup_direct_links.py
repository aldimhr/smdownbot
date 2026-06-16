#!/usr/bin/env python3
import asyncio
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from database.models import init_db
from config import config
from services.direct_links import cleanup_direct_link_artifacts


async def main():
    os.makedirs(os.path.dirname(config.DB_PATH), exist_ok=True)
    os.makedirs(config.DIRECT_LINK_DIR, exist_ok=True)
    await init_db(config.DB_PATH)
    result = await cleanup_direct_link_artifacts()
    print(result)


if __name__ == "__main__":
    asyncio.run(main())

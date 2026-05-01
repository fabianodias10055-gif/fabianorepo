"""
Standalone LocoDev link shortener + admin dashboard.
Run: python server.py
Admin: http://localhost:8080/adminlocoILco
"""
import asyncio
import logging
import os

from dotenv import load_dotenv

load_dotenv()

ADMIN_SECRET = os.getenv("ADMIN_SECRET", "")
PORT = int(os.getenv("PORT", "8080"))

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-8s  %(name)s: %(message)s",
)
logger = logging.getLogger("server")


async def main():
    from aiohttp import web
    from shortener import setup_routes
    from admin_panel import setup_admin_routes

    if not ADMIN_SECRET:
        logger.warning("ADMIN_SECRET not set in .env — admin panel will be disabled!")

    app = web.Application()
    setup_admin_routes(app, ADMIN_SECRET)   # must be before shortener catch-all
    setup_routes(app)

    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, "0.0.0.0", PORT)
    await site.start()

    logger.info("Server running at http://localhost:%d", PORT)
    logger.info("Admin panel:    http://localhost:%d/adminlocoILco", PORT)

    await asyncio.Event().wait()


if __name__ == "__main__":
    asyncio.run(main())

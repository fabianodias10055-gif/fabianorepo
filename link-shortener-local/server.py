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
# Bind to localhost by default so the admin panel isn't exposed to the whole LAN.
# Set HOST=0.0.0.0 in .env only if you deliberately want network access.
HOST = os.getenv("HOST", "127.0.0.1")

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
    site = web.TCPSite(runner, HOST, PORT)
    await site.start()

    logger.info("Server running at http://localhost:%d (bound to %s)", PORT, HOST)
    logger.info("Admin panel:    http://localhost:%d/adminlocoILco", PORT)

    await asyncio.Event().wait()


if __name__ == "__main__":
    asyncio.run(main())

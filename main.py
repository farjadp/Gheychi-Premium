"""
Railway entrypoint — runs both the Telegram bot and Flask admin panel
as separate processes so they share the same SQLite database on disk.
"""
import multiprocessing
import sys
import logging

logging.basicConfig(
    format="%(asctime)s [%(processName)s] %(levelname)s %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger(__name__)


def run_bot():
    from bot import main
    main()


def run_admin():
    from admin_panel import main
    main()


if __name__ == "__main__":
    bot_proc = multiprocessing.Process(target=run_bot, name="bot", daemon=False)
    admin_proc = multiprocessing.Process(target=run_admin, name="admin", daemon=False)

    bot_proc.start()
    logger.info("Bot process started (pid=%s)", bot_proc.pid)

    admin_proc.start()
    logger.info("Admin panel process started (pid=%s)", admin_proc.pid)

    # If either process dies, shut down both
    try:
        while True:
            bot_proc.join(timeout=5)
            admin_proc.join(timeout=5)

            if not bot_proc.is_alive():
                logger.error("Bot process exited with code %s — shutting down.", bot_proc.exitcode)
                admin_proc.terminate()
                sys.exit(1)

            if not admin_proc.is_alive():
                logger.error("Admin panel process exited with code %s — shutting down.", admin_proc.exitcode)
                bot_proc.terminate()
                sys.exit(1)

    except KeyboardInterrupt:
        logger.info("Shutting down...")
        bot_proc.terminate()
        admin_proc.terminate()
        bot_proc.join()
        admin_proc.join()

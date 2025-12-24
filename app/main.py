"""SECCAMP - Main entry point for the batch system."""
import argparse
import logging
import sys
from datetime import date

from config import Config
from database import DatabaseManager


def setup_logging(config: Config) -> logging.Logger:
    """Configure logging with file and console handlers."""
    logger = logging.getLogger("seccamp")
    logger.setLevel(getattr(logging, config.log_level.upper()))

    # Clear existing handlers
    logger.handlers.clear()

    # Console handler
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setLevel(logging.INFO)
    console_format = logging.Formatter(
        "%(asctime)s - %(name)s - %(levelname)s - %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )
    console_handler.setFormatter(console_format)
    logger.addHandler(console_handler)

    # File handler
    log_file = config.log_dir / f"seccamp-{date.today().strftime('%Y-%m-%d')}.log"
    file_handler = logging.FileHandler(log_file, encoding="utf-8")
    file_handler.setLevel(logging.DEBUG)
    file_format = logging.Formatter(
        "%(asctime)s - %(name)s - %(levelname)s - %(funcName)s:%(lineno)d - %(message)s"
    )
    file_handler.setFormatter(file_format)
    logger.addHandler(file_handler)

    return logger


def run_scrape(config: Config, db_manager: DatabaseManager, logger: logging.Logger) -> int:
    """Run the scraping mode."""
    logger.info("Starting scrape mode")

    session = db_manager.get_session()
    batch_date = date.today().isoformat()

    # TODO: Implement actual scraping for each site
    # This is a minimal placeholder for testing the build

    # For now, just create a scraping log entry
    log_id = db_manager.create_scraping_log(session, batch_date, "test")
    db_manager.update_scraping_log(
        session,
        log_id,
        status="success",
        properties_found=0,
        cache_hits=0,
        cache_misses=0,
    )

    logger.info("Scrape mode completed - placeholder (no actual scraping yet)")
    return 0


def run_full(config: Config, db_manager: DatabaseManager, logger: logging.Logger) -> int:
    """Run the full batch: scrape → analyze → generate → build → push."""
    logger.info("Starting full batch mode")

    session = db_manager.get_session()
    batch_date = date.today().isoformat()

    # Step 1: Scrape
    logger.info("Step 1: Scraping properties...")
    scrape_result = run_scrape(config, db_manager, logger)
    if scrape_result != 0:
        return scrape_result

    # Step 2: Analyze & Score
    logger.info("Step 2: Analyzing and scoring properties...")
    # TODO: Implement AI scoring

    # Step 3: Generate Markdown
    logger.info("Step 3: Generating daily blog post...")
    # TODO: Implement Markdown generation

    # Step 4: Hugo Build
    logger.info("Step 4: Building Hugo site...")
    # TODO: Implement Hugo build

    # Step 5: Git Push
    logger.info("Step 5: Pushing to GitHub...")
    # TODO: Implement Git push

    # Cleanup expired cache
    logger.info("Cleaning up expired cache...")
    cleanup_result = db_manager.cleanup_expired_cache()
    logger.info(f"Cache cleanup: invalidated={cleanup_result['invalidated']}, deleted={cleanup_result['deleted']}")

    logger.info("Full batch mode completed")
    return 0


def main() -> int:
    """Main entry point."""
    parser = argparse.ArgumentParser(
        description="SECCAMP - Private Campsite Search AI Agent"
    )
    parser.add_argument(
        "--mode",
        choices=["scrape", "full"],
        default="full",
        help="Execution mode: scrape (scraping only) or full (complete batch)",
    )

    args = parser.parse_args()

    # Load configuration
    config = Config.from_env()
    config.ensure_directories()

    # Setup logging
    logger = setup_logging(config)
    logger.info(f"SECCAMP starting in mode: {args.mode}")
    logger.info(f"Database path: {config.db_path}")

    # Initialize database manager
    db_manager = DatabaseManager(config.db_path)

    # Health check
    health = db_manager.health_check()
    logger.info(f"Database health: {health}")

    # Run based on mode
    if args.mode == "scrape":
        return run_scrape(config, db_manager, logger)
    else:
        return run_full(config, db_manager, logger)


if __name__ == "__main__":
    sys.exit(main())

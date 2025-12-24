"""SECCAMP - Main entry point for the batch system."""
import argparse
import logging
import sys
from datetime import date
from pathlib import Path

from config import Config
from database import DatabaseManager
from scrapers import AthomeScraper


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

    # Create scraping log entry
    log_id = db_manager.create_scraping_log(session, batch_date, "athome")

    try:
        # Initialize AthomeScraper
        scraper = AthomeScraper(
            db_path=config.db_path,
            max_detail_pages=config.max_detail_pages,
        )

        # Run scraper (returns dict with raw HTML for inspection)
        logger.info(f"[*] Running AthomeScraper (max_detail_pages={config.max_detail_pages})")
        result = scraper.scrape()

        # Log results
        list_html_size = len(result.get("list_html", "") or "")
        num_urls = len(result.get("property_urls", []))
        num_details = len(result.get("detail_pages", {}))

        logger.info(f"[*] List page HTML: {list_html_size} bytes")
        logger.info(f"[*] Property URLs found: {num_urls}")
        logger.info(f"[*] Detail pages scraped: {num_details}")

        # Save scraped HTML for inspection (debug output directory)
        debug_dir = config.data_dir / "debug" / batch_date
        debug_dir.mkdir(parents=True, exist_ok=True)

        if result.get("list_html"):
            list_file = debug_dir / "athome_list.html"
            list_file.write_text(result["list_html"], encoding="utf-8")
            logger.info(f"[*] Saved list HTML: {list_file}")

        for url, html in result.get("detail_pages", {}).items():
            # Extract property ID from URL for filename
            import re
            match = re.search(r"/kodate/(\d+)/", url)
            prop_id = match.group(1) if match else "unknown"
            detail_file = debug_dir / f"athome_detail_{prop_id}.html"
            detail_file.write_text(html, encoding="utf-8")
            logger.info(f"[*] Saved detail HTML: {detail_file}")

        # Update scraping log
        db_manager.update_scraping_log(
            session,
            log_id,
            status="success",
            properties_found=num_urls,
            cache_hits=scraper.cache_manager.get_stats().get("today_hits", 0),
            cache_misses=scraper.cache_manager.get_stats().get("today_misses", 0),
        )

        logger.info("Scrape mode completed successfully")
        logger.info(f"[*] Inspect saved HTML in: {debug_dir}")
        return 0

    except Exception as e:
        logger.error(f"Scraping failed: {e}", exc_info=True)
        db_manager.update_scraping_log(
            session,
            log_id,
            status="failed",
            error_messages=str(e),
        )
        return 1


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

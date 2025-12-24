"""Configuration management for SECCAMP."""
import os
from pathlib import Path
from dataclasses import dataclass
from typing import Optional


@dataclass
class Config:
    """Application configuration."""

    # Paths
    data_dir: Path = Path("/data")
    db_path: Path = Path("/data/seccamp.db")
    log_dir: Path = Path("/data/logs")
    hugo_site_dir: Path = Path("/data/hugo_site")

    # Logging
    log_level: str = "INFO"

    # GitHub
    github_token: Optional[str] = None
    github_repo: Optional[str] = None
    github_user: Optional[str] = None
    github_email: Optional[str] = None

    # Hugo
    hugo_base_url: str = "https://username.github.io/seccamp/"

    # Scraping
    headless: bool = True
    page_timeout: int = 30
    element_timeout: int = 10
    max_detail_pages: int = 1  # Debug: limit detail pages to scrape

    @classmethod
    def from_env(cls) -> "Config":
        """Load configuration from environment variables."""
        return cls(
            log_level=os.getenv("LOG_LEVEL", "INFO"),
            github_token=os.getenv("GITHUB_TOKEN"),
            github_repo=os.getenv("GITHUB_REPO"),
            github_user=os.getenv("GITHUB_USER"),
            github_email=os.getenv("GITHUB_EMAIL"),
            hugo_base_url=os.getenv("HUGO_BASE_URL", "https://username.github.io/seccamp/"),
            max_detail_pages=int(os.getenv("MAX_DETAIL_PAGES", "1")),
        )

    def ensure_directories(self) -> None:
        """Ensure all required directories exist."""
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self.log_dir.mkdir(parents=True, exist_ok=True)
        self.hugo_site_dir.mkdir(parents=True, exist_ok=True)
        (self.hugo_site_dir / "content/posts").mkdir(parents=True, exist_ok=True)

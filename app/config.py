"""Configuration management for SECCAMP."""
import os
from dataclasses import dataclass
from typing import Optional
from pathlib import Path


@dataclass
class Config:
    """Application configuration."""

    # Neon PostgreSQL Database
    database_url: Optional[str] = None

    # Paths
    data_dir: Path = Path("/data")
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
            database_url=os.getenv("DATABASE_URL"),
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
        self.log_dir.mkdir(parents=True, exist_ok=True)
        self.hugo_site_dir.mkdir(parents=True, exist_ok=True)
        (self.hugo_site_dir / "content/posts").mkdir(parents=True, exist_ok=True)

    def validate(self) -> None:
        """Validate required configuration."""
        if not self.database_url:
            raise ValueError(
                "DATABASE_URL environment variable is required. "
                "Set it to your Neon PostgreSQL connection string."
            )

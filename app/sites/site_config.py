"""Site configuration loader for SECCAMP scrapers."""
import json
from pathlib import Path
from typing import Dict, List, Optional, Any


class SiteConfig:
    """Load and access site configuration from sites.json."""

    def __init__(self, config_path: str | Path = "sites/sites.json"):
        self.config_path = Path(config_path)
        self.sites: Dict[str, Dict[str, Any]] = self._load_config()

    def _load_config(self) -> Dict[str, Dict[str, Any]]:
        """Load sites configuration from JSON file."""
        if not self.config_path.exists():
            raise FileNotFoundError(f"Site config not found: {self.config_path}")

        with open(self.config_path, "r", encoding="utf-8") as f:
            data = json.load(f)

        # Index by site_name for easy lookup
        return {site["site_name"]: site for site in data.get("sites", [])}

    def get_site(self, site_name: str) -> Optional[Dict[str, Any]]:
        """Get configuration for a specific site."""
        return self.sites.get(site_name)

    def get_enabled_sites(self) -> List[str]:
        """Get list of enabled site names."""
        return [
            name
            for name, cfg in self.sites.items()
            if cfg.get("enabled", True)
        ]

    def get_entry_urls(self, site_name: str) -> Dict[str, str]:
        """Get entry URLs for a site's prefectures."""
        site = self.get_site(site_name)
        return site.get("entry_urls", {}) if site else {}

    def get_selectors(self, site_name: str, page_type: str) -> Dict[str, Any]:
        """Get CSS selectors for a page type."""
        site = self.get_site(site_name)
        if not site:
            return {}
        return site.get("selectors", {}).get(page_type, {})

    def get_rate_limit(self, site_name: str) -> Dict[str, int]:
        """Get rate limit settings for a site."""
        site = self.get_site(site_name)
        if not site:
            return {"max_requests": 30, "period_seconds": 300}
        return site.get("rate_limit", {"max_requests": 30, "period_seconds": 300})

    def get_pagination(self, site_name: str) -> Dict[str, Any]:
        """Get pagination settings for a site."""
        site = self.get_site(site_name)
        if not site:
            return {"type": "page_param", "param_name": "page", "max_pages": 100}
        return site.get("pagination", {"type": "page_param", "param_name": "page", "max_pages": 100})

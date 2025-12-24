"""URL normalization for cache keys."""
import hashlib
from typing import Dict
from urllib.parse import urlparse, urlunparse, parse_qs, urlencode


class URLNormalizer:
    """Normalize URLs for consistent caching."""

    # Keep only important query params per site
    KEEP_PARAMS = {
        "athome": ["bukkenNo", "id"],
        "suumo": ["bc", "id"],
        "ieichiba": ["id"],
        "zero_estate": ["id"],
        "jmty": ["id"],
        "homes": ["id"],
        "rakuten": ["id"],
        "default": ["id", "page"],
    }

    @staticmethod
    def normalize(url: str, site_name: str = "default") -> Dict[str, str]:
        """
        Normalize a URL for caching.

        Args:
            url: The original URL
            site_name: The site name for param filtering

        Returns:
            Dict with original_url, normalized_url, url_hash
        """
        parsed = urlparse(url)

        # Lowercase domain and path
        scheme = parsed.scheme.lower()
        netloc = parsed.netloc.lower()
        path = parsed.path.rstrip("/")

        # Filter query params
        keep = URLNormalizer.KEEP_PARAMS.get(site_name, URLNormalizer.KEEP_PARAMS["default"])
        query_dict = parse_qs(parsed.query, keep_blank_values=True)
        filtered = {k: v for k, v in query_dict.items() if k in keep}
        sorted_query = urlencode(sorted(filtered.items()), doseq=True)

        # Reconstruct
        normalized_url = urlunparse((scheme, netloc, path, "", sorted_query, ""))

        # Generate hash
        url_hash = hashlib.sha256(normalized_url.encode("utf-8")).hexdigest()

        return {
            "original_url": url,
            "normalized_url": normalized_url,
            "url_hash": url_hash,
        }

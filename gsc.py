"""
Google Search Console API client.
Identifies underperforming pages (page-2 rankings) for the refresh workflow.

Setup:
1. Create a service account in Google Cloud Console
2. Enable the Search Console API
3. Download the JSON key file
4. Add the service account email to your GSC property as an owner
5. Set GSC_SERVICE_ACCOUNT_FILE and GSC_SITE_URL in .env
"""

import os
from datetime import datetime, timedelta

from google.oauth2 import service_account
from googleapiclient.discovery import build


SCOPES = ["https://www.googleapis.com/auth/webmasters.readonly"]


def _get_service():
    key_file = os.environ.get("GSC_SERVICE_ACCOUNT_FILE")
    if not key_file:
        raise EnvironmentError("GSC_SERVICE_ACCOUNT_FILE env var not set")

    creds = service_account.Credentials.from_service_account_file(key_file, scopes=SCOPES)
    return build("searchconsole", "v1", credentials=creds, cache_discovery=False)


def _date_range(days: int) -> tuple[str, str]:
    end = datetime.utcnow().date() - timedelta(days=3)  # GSC has ~3 day lag
    start = end - timedelta(days=days)
    return str(start), str(end)


def _slug_from_url(url: str, site_url: str) -> str:
    site = site_url.rstrip("/")
    return url.replace(site, "").lstrip("/")


class SearchConsoleClient:

    def __init__(self):
        self.service = _get_service()
        self.site_url = os.environ.get("GSC_SITE_URL", "").rstrip("/")
        if not self.site_url:
            raise EnvironmentError("GSC_SITE_URL env var not set")

    def get_page_performance(self, days: int = 90, min_impressions: int = 100) -> list:
        """
        Fetch aggregated performance per page over the last `days` days.
        Returns list of dicts: {url, slug, clicks, impressions, ctr, position}
        """
        start_date, end_date = _date_range(days)

        response = self.service.searchanalytics().query(
            siteUrl=self.site_url,
            body={
                "startDate": start_date,
                "endDate": end_date,
                "dimensions": ["page"],
                "rowLimit": 1000,
            },
        ).execute()

        results = []
        for row in response.get("rows", []):
            url = row["keys"][0]
            impressions = row.get("impressions", 0)
            if impressions < min_impressions:
                continue
            results.append({
                "url": url,
                "slug": _slug_from_url(url, self.site_url),
                "clicks": row.get("clicks", 0),
                "impressions": impressions,
                "ctr": round(row.get("ctr", 0) * 100, 2),
                "position": round(row.get("position", 0), 1),
            })

        return sorted(results, key=lambda x: x["position"])

    def get_underperforming_pages(
        self,
        min_position: float = 11.0,
        max_position: float = 20.0,
        min_impressions: int = 50,
        days: int = 90,
    ) -> list:
        """
        Return pages ranking in position range [min_position, max_position].
        These are page-2 results — highest ROI targets for content refresh.
        Sorted by impressions descending (most visible first).
        """
        all_pages = self.get_page_performance(days=days, min_impressions=min_impressions)
        targets = [
            p for p in all_pages
            if min_position <= p["position"] <= max_position
        ]
        return sorted(targets, key=lambda x: x["impressions"], reverse=True)

    def get_keyword_performance(self, page_url: str, days: int = 90) -> list:
        """
        Return keywords a specific page ranks for, sorted by impressions.
        Returns list of dicts: {keyword, clicks, impressions, ctr, position}
        """
        start_date, end_date = _date_range(days)

        response = self.service.searchanalytics().query(
            siteUrl=self.site_url,
            body={
                "startDate": start_date,
                "endDate": end_date,
                "dimensions": ["query"],
                "dimensionFilterGroups": [{
                    "filters": [{
                        "dimension": "page",
                        "operator": "equals",
                        "expression": page_url,
                    }]
                }],
                "rowLimit": 100,
            },
        ).execute()

        results = []
        for row in response.get("rows", []):
            results.append({
                "keyword": row["keys"][0],
                "clicks": row.get("clicks", 0),
                "impressions": row.get("impressions", 0),
                "ctr": round(row.get("ctr", 0) * 100, 2),
                "position": round(row.get("position", 0), 1),
            })

        return sorted(results, key=lambda x: x["impressions"], reverse=True)

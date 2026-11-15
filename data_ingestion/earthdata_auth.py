"""Environment-only bearer authentication for NASA Earthdata HTTPS requests."""

import os
from urllib.parse import urlsplit

import requests


class EarthdataError(RuntimeError):
    """A safe, user-facing Earthdata error without remote response contents."""


class EarthdataAuthenticationError(EarthdataError):
    """Earthdata credentials are missing, rejected, expired, or unauthorized."""


class EarthdataRequestError(EarthdataError):
    """Earthdata could not complete the requested operation."""


def earthdata_get(url: str, *, params=None, timeout: float = 30) -> requests.Response:
    """GET an Earthdata resource without persisting credentials or following redirects.

    EARTHDATA_TOKEN is read for each call so rotation does not require rebuilding
    a client. HTTP 401 is authoritative for expired, invalid, or revoked tokens;
    JWT contents are not treated as verified identity or authorization evidence.
    Callers should catch EarthdataError and display its credential-free message.
    """
    token = os.environ.get("EARTHDATA_TOKEN", "").strip()
    if not token:
        raise EarthdataAuthenticationError(
            "EARTHDATA_TOKEN is not configured. Set a NASA Earthdata bearer token "
            "in the process environment or your private .env file."
        )

    parsed = urlsplit(url)
    hostname = (parsed.hostname or "").lower()
    trusted_domains = ("earthdata.nasa.gov", "earthdatacloud.nasa.gov", "asf.alaska.edu")
    trusted = any(
        hostname == domain or hostname.endswith("." + domain)
        for domain in trusted_domains
    )
    if parsed.scheme != "https" or parsed.username or parsed.password or not trusted:
        raise EarthdataRequestError(
            "Earthdata bearer authentication requires an HTTPS Earthdata or ASF URL."
        )

    try:
        response = requests.get(
            url,
            params=params,
            headers={
                "Authorization": f"Bearer {token}",
                "User-Agent": "GreenLens/1.0 (climate-risk-research)",
            },
            timeout=timeout,
            allow_redirects=False,
        )
    except requests.RequestException:
        raise EarthdataRequestError(
            "Earthdata could not be reached. Check the connection and retry."
        ) from None

    if response.status_code == 401:
        response.close()
        raise EarthdataAuthenticationError(
            "Earthdata rejected EARTHDATA_TOKEN (HTTP 401). The token may be "
            "expired, invalid, or revoked. Generate a replacement in NASA "
            "Earthdata Login and update your private environment."
        )
    if response.status_code == 403:
        response.close()
        raise EarthdataAuthenticationError(
            "Earthdata denied access (HTTP 403). Check token permissions and "
            "accept any required dataset access agreements in Earthdata Login."
        )
    if 300 <= response.status_code < 400:
        response.close()
        raise EarthdataRequestError(
            "Earthdata returned a redirect. It was not followed to avoid "
            "forwarding credentials; use the dataset's direct HTTPS API endpoint."
        )
    try:
        response.raise_for_status()
    except requests.RequestException:
        status_code = response.status_code
        response.close()
        raise EarthdataRequestError(
            f"Earthdata request failed (HTTP {status_code}). Retry later or check "
            "the dataset endpoint."
        ) from None
    return response
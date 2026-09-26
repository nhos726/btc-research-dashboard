from __future__ import annotations

import requests

from config import SETTINGS


class DataSourceError(RuntimeError):
    pass


def get_json(url: str, params: dict | None = None) -> dict | list:
    try:
        response = requests.get(
            url,
            params=params,
            timeout=SETTINGS.request_timeout,
            headers={"User-Agent": "BTC-Research-Dashboard/0.1"},
        )
        response.raise_for_status()
        return response.json()
    except (requests.RequestException, ValueError) as exc:
        raise DataSourceError(f"API request failed: {type(exc).__name__}") from exc


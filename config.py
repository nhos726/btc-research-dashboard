"""Application configuration and endpoint constants."""

from dataclasses import dataclass


@dataclass(frozen=True)
class Settings:
    request_timeout: int = 15
    cache_ttl_seconds: int = 300
    spot_symbol: str = "BTCUSDT"
    futures_pair: str = "BTCUSDT"
    coingecko_base: str = "https://api.coingecko.com/api/v3"
    binance_spot_base: str = "https://api.binance.com"
    binance_futures_base: str = "https://fapi.binance.com"
    deribit_base: str = "https://www.deribit.com/api/v2"


SETTINGS = Settings()


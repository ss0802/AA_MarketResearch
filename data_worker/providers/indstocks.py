import csv
import io

import requests


class INDstocksProvider:
    name = "indstocks"
    base_url = "https://api.indstocks.com"

    def __init__(self, access_token, timeout=30):
        if not access_token:
            raise ValueError("INDSTOCKS_ACCESS_TOKEN is not configured.")
        self.timeout = timeout
        self.headers = {"Authorization": access_token}

    def equity_instruments(self):
        response = requests.get(
            f"{self.base_url}/market/instruments",
            params={"source": "equity"}, headers=self.headers, timeout=self.timeout,
        )
        response.raise_for_status()
        return list(csv.DictReader(io.StringIO(response.text)))

    def full_quotes(self, scrip_codes):
        response = requests.get(
            f"{self.base_url}/market/quotes/full",
            params={"scrip-codes": ",".join(scrip_codes)},
            headers=self.headers, timeout=self.timeout,
        )
        response.raise_for_status()
        payload = response.json()
        if payload.get("status") != "success":
            raise RuntimeError(str(payload)[:1000])
        return payload.get("data", {})

from __future__ import annotations

import csv
import io
from datetime import datetime, timezone

from .base import BaseSourceAdapter, CollectedEvent
from .normalizer import COUNTRIES, country_from_text


class JhuCsseAdapter(BaseSourceAdapter):
    source_id = "jhu-csse"
    source_name = "JHU CSSE"
    content_type = "text/csv"
    url = "https://raw.githubusercontent.com/CSSEGISandData/COVID-19/master/csse_covid_19_data/csse_covid_19_time_series/time_series_covid19_confirmed_global.csv"

    def parse(self, content: bytes) -> list[CollectedEvent]:
        rows = csv.DictReader(io.StringIO(content.decode("utf-8-sig")))
        output: list[CollectedEvent] = []
        for row in rows:
            country_raw = (row.get("Country/Region") or "").strip()
            if not country_raw:
                continue
            match = COUNTRIES.get(country_raw.lower())
            if match:
                code, country_name = match
            else:
                code, country_name = country_from_text(country_raw, fallback_code="UNK", fallback_name=country_raw)
            date_keys = [key for key in row if key not in {"Province/State", "Country/Region", "Lat", "Long"}]
            cases = int(float(row.get(date_keys[-1], "0") or 0)) if date_keys else 0
            output.append(
                CollectedEvent(
                    title=f"{country_name} COVID-19 累计病例更新", disease="新型冠状病毒感染",
                    country=country_name, country_code=code, source=self.source_name, source_url=self.url,
                    event_type="time_series", cases=cases, deaths=0, confidence=0.98,
                    published_at=datetime.now(timezone.utc), latitude=float(row.get("Lat") or 0), longitude=float(row.get("Long") or 0),
                )
            )
        return output


class OwidAdapter(BaseSourceAdapter):
    source_id = "owid"
    source_name = "Our World in Data"
    content_type = "text/csv"
    url = "https://raw.githubusercontent.com/owid/covid-19-data/master/public/data/owid-covid-data.csv"

    def parse(self, content: bytes) -> list[CollectedEvent]:
        latest: dict[str, dict[str, str]] = {}
        for row in csv.DictReader(io.StringIO(content.decode("utf-8-sig"))):
            code = row.get("iso_code", "")
            if len(code) == 3 and (code not in latest or row.get("date", "") > latest[code].get("date", "")):
                latest[code] = row
        output: list[CollectedEvent] = []
        for code, row in latest.items():
            country = row.get("location", code)
            output.append(
                CollectedEvent(
                    title=f"{country} COVID-19 卫生指标更新", disease="新型冠状病毒感染",
                    country=country, country_code=code, source=self.source_name, source_url=self.url,
                    event_type="indicator", cases=int(float(row.get("total_cases") or 0)),
                    deaths=int(float(row.get("total_deaths") or 0)), confidence=0.98,
                    published_at=datetime.fromisoformat(row["date"]).replace(tzinfo=timezone.utc),
                )
            )
        return output

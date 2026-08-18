from __future__ import annotations

import re


COUNTRIES: dict[str, tuple[str, str]] = {
    "democratic republic of the congo": ("COD", "刚果民主共和国"), "dr congo": ("COD", "刚果民主共和国"),
    "congo": ("COD", "刚果民主共和国"), "brazil": ("BRA", "巴西"), "india": ("IND", "印度"),
    "indonesia": ("IDN", "印度尼西亚"), "thailand": ("THA", "泰国"), "vietnam": ("VNM", "越南"),
    "united states": ("USA", "美国"), "usa": ("USA", "美国"), "france": ("FRA", "法国"),
    "united kingdom": ("GBR", "英国"), "mexico": ("MEX", "墨西哥"), "egypt": ("EGY", "埃及"),
    "china": ("CHN", "中国"), "中国": ("CHN", "中国"), "巴西": ("BRA", "巴西"),
    "印度": ("IND", "印度"), "泰国": ("THA", "泰国"), "刚果": ("COD", "刚果民主共和国"),
}

DISEASES: dict[str, str] = {
    "mpox": "猴痘", "monkeypox": "猴痘", "dengue": "登革热", "cholera": "霍乱",
    "measles": "麻疹", "nipah": "尼帕病毒病", "ebola": "埃博拉", "influenza": "流感",
    "covid": "新型冠状病毒感染", "coronavirus": "新型冠状病毒感染", "yellow fever": "黄热病",
    "polio": "脊髓灰质炎", "h5n1": "H5N1禽流感", "猴痘": "猴痘", "登革热": "登革热",
}


def country_from_text(text: str, fallback_code: str = "UNK", fallback_name: str = "待识别地区") -> tuple[str, str]:
    lowered = text.lower()
    for name in sorted(COUNTRIES, key=len, reverse=True):
        if name in lowered:
            return COUNTRIES[name]
    return fallback_code, fallback_name


def disease_from_text(text: str) -> str:
    lowered = text.lower()
    for keyword in sorted(DISEASES, key=len, reverse=True):
        if keyword in lowered:
            return DISEASES[keyword]
    return "其他传染病"


def numbers_from_text(text: str) -> tuple[int, int]:
    cases = re.search(r"([\d,]+)\s*(?:confirmed\s+)?cases?", text, re.I)
    deaths = re.search(r"([\d,]+)\s*deaths?", text, re.I)
    return (
        int(cases.group(1).replace(",", "")) if cases else 0,
        int(deaths.group(1).replace(",", "")) if deaths else 0,
    )

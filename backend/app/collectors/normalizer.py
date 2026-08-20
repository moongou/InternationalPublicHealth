from __future__ import annotations

import re


COUNTRIES: dict[str, tuple[str, str]] = {
    # 非洲
    "democratic republic of the congo": ("COD", "刚果民主共和国"), "dr congo": ("COD", "刚果民主共和国"),
    "congo": ("COD", "刚果民主共和国"), "congo (kinshasa)": ("COD", "刚果民主共和国"),
    "congo (brazzaville)": ("COG", "刚果共和国"), "republic of the congo": ("COG", "刚果共和国"),
    "nigeria": ("NGA", "尼日利亚"), "south africa": ("ZAF", "南非"), "somalia": ("SOM", "索马里"),
    "kenya": ("KEN", "肯尼亚"), "ethiopia": ("ETH", "埃塞俄比亚"), "sudan": ("SDN", "苏丹"),
    "south sudan": ("SSD", "南苏丹"), "uganda": ("UGA", "乌干达"), "tanzania": ("TZA", "坦桑尼亚"),
    "rwanda": ("RWA", "卢旺达"), "burundi": ("BDI", "布隆迪"), "angola": ("AGO", "安哥拉"),
    "zambia": ("ZMB", "赞比亚"), "zimbabwe": ("ZWE", "津巴布韦"), "mozambique": ("MOZ", "莫桑比克"),
    "malawi": ("MWI", "马拉维"), "madagascar": ("MDG", "马达加斯加"), "cameroon": ("CMR", "喀麦隆"),
    "ghana": ("GHA", "加纳"), "cote d'ivoire": ("CIV", "科特迪瓦"), "côte d'ivoire": ("CIV", "科特迪瓦"),
    "ivory coast": ("CIV", "科特迪瓦"), "senegal": ("SEN", "塞内加尔"), "mali": ("MLI", "马里"),
    "niger": ("NER", "尼日尔"), "chad": ("TCD", "乍得"), "burkina faso": ("BFA", "布基纳法索"),
    "guinea": ("GIN", "几内亚"), "guinea-bissau": ("GNB", "几内亚比绍"), "sierra leone": ("SLE", "塞拉利昂"),
    "liberia": ("LBR", "利比里亚"), "benin": ("BEN", "贝宁"), "togo": ("TGO", "多哥"),
    "gabon": ("GAB", "加蓬"), "central african republic": ("CAF", "中非共和国"), "libya": ("LBY", "利比亚"),
    "algeria": ("DZA", "阿尔及利亚"), "morocco": ("MAR", "摩洛哥"), "tunisia": ("TUN", "突尼斯"),
    "mauritania": ("MRT", "毛里塔尼亚"), "namibia": ("NAM", "纳米比亚"), "botswana": ("BWA", "博茨瓦纳"),
    "eritrea": ("ERI", "厄立特里亚"), "djibouti": ("DJI", "吉布提"), "equatorial guinea": ("GNQ", "赤道几内亚"),
    "gambia": ("GMB", "冈比亚"), "lesotho": ("LSO", "莱索托"), "eswatini": ("SWZ", "斯威士兰"),
    "swaziland": ("SWZ", "斯威士兰"), "western sahara": ("ESH", "西撒哈拉"), "egypt": ("EGY", "埃及"),
    # 美洲
    "brazil": ("BRA", "巴西"), "mexico": ("MEX", "墨西哥"), "canada": ("CAN", "加拿大"),
    "united states": ("USA", "美国"), "usa": ("USA", "美国"), "argentina": ("ARG", "阿根廷"),
    "colombia": ("COL", "哥伦比亚"), "peru": ("PER", "秘鲁"), "chile": ("CHL", "智利"),
    "venezuela": ("VEN", "委内瑞拉"), "ecuador": ("ECU", "厄瓜多尔"), "bolivia": ("BOL", "玻利维亚"),
    "paraguay": ("PRY", "巴拉圭"), "uruguay": ("URY", "乌拉圭"), "guyana": ("GUY", "圭亚那"),
    "suriname": ("SUR", "苏里南"), "panama": ("PAN", "巴拿马"), "costa rica": ("CRI", "哥斯达黎加"),
    "nicaragua": ("NIC", "尼加拉瓜"), "honduras": ("HND", "洪都拉斯"), "el salvador": ("SLV", "萨尔瓦多"),
    "guatemala": ("GTM", "危地马拉"), "belize": ("BLZ", "伯利兹"), "cuba": ("CUB", "古巴"),
    "haiti": ("HTI", "海地"), "dominican republic": ("DOM", "多米尼加共和国"), "jamaica": ("JAM", "牙买加"),
    "trinidad and tobago": ("TTO", "特立尼达和多巴哥"), "bahamas": ("BHS", "巴哈马"), "barbados": ("BRB", "巴巴多斯"),
    # 亚洲
    "china": ("CHN", "中国"), "india": ("IND", "印度"), "indonesia": ("IDN", "印度尼西亚"),
    "thailand": ("THA", "泰国"), "vietnam": ("VNM", "越南"), "philippines": ("PHL", "菲律宾"),
    "malaysia": ("MYS", "马来西亚"), "singapore": ("SGP", "新加坡"), "myanmar": ("MMR", "缅甸"),
    "burma": ("MMR", "缅甸"), "laos": ("LAO", "老挝"), "cambodia": ("KHM", "柬埔寨"),
    "japan": ("JPN", "日本"), "south korea": ("KOR", "韩国"), "korea, south": ("KOR", "韩国"),
    "republic of korea": ("KOR", "韩国"), "north korea": ("PRK", "朝鲜"), "korea, north": ("PRK", "朝鲜"),
    "mongolia": ("MNG", "蒙古"), "bangladesh": ("BGD", "孟加拉国"), "pakistan": ("PAK", "巴基斯坦"),
    "afghanistan": ("AFG", "阿富汗"), "nepal": ("NPL", "尼泊尔"), "bhutan": ("BTN", "不丹"),
    "sri lanka": ("LKA", "斯里兰卡"), "maldives": ("MDV", "马尔代夫"), "iran": ("IRN", "伊朗"),
    "iraq": ("IRQ", "伊拉克"), "saudi arabia": ("SAU", "沙特阿拉伯"), "yemen": ("YEM", "也门"),
    "oman": ("OMN", "阿曼"), "united arab emirates": ("ARE", "阿联酋"), "uae": ("ARE", "阿联酋"),
    "qatar": ("QAT", "卡塔尔"), "kuwait": ("KWT", "科威特"), "bahrain": ("BHR", "巴林"),
    "jordan": ("JOR", "约旦"), "lebanon": ("LBN", "黎巴嫩"), "syria": ("SYR", "叙利亚"),
    "israel": ("ISR", "以色列"), "palestine": ("PSE", "巴勒斯坦"), "west bank and gaza": ("PSE", "巴勒斯坦"),
    "turkey": ("TUR", "土耳其"), "türkiye": ("TUR", "土耳其"), "kazakhstan": ("KAZ", "哈萨克斯坦"),
    "uzbekistan": ("UZB", "乌兹别克斯坦"), "kyrgyzstan": ("KGZ", "吉尔吉斯斯坦"), "tajikistan": ("TJK", "塔吉克斯坦"),
    "turkmenistan": ("TKM", "土库曼斯坦"), "azerbaijan": ("AZE", "阿塞拜疆"), "georgia": ("GEO", "格鲁吉亚"),
    "armenia": ("ARM", "亚美尼亚"), "taiwan": ("TWN", "中国台湾"), "hong kong": ("HKG", "中国香港"),
    "macau": ("MAC", "中国澳门"), "brunei": ("BRN", "文莱"), "timor-leste": ("TLS", "东帝汶"),
    "east timor": ("TLS", "东帝汶"), "papua new guinea": ("PNG", "巴布亚新几内亚"),
    # 欧洲
    "united kingdom": ("GBR", "英国"), "uk": ("GBR", "英国"), "france": ("FRA", "法国"),
    "germany": ("DEU", "德国"), "italy": ("ITA", "意大利"), "spain": ("ESP", "西班牙"),
    "portugal": ("PRT", "葡萄牙"), "netherlands": ("NLD", "荷兰"), "belgium": ("BEL", "比利时"),
    "luxembourg": ("LUX", "卢森堡"), "switzerland": ("CHE", "瑞士"), "austria": ("AUT", "奥地利"),
    "poland": ("POL", "波兰"), "czechia": ("CZE", "捷克"), "czech republic": ("CZE", "捷克"),
    "slovakia": ("SVK", "斯洛伐克"), "hungary": ("HUN", "匈牙利"), "romania": ("ROU", "罗马尼亚"),
    "bulgaria": ("BGR", "保加利亚"), "greece": ("GRC", "希腊"), "cyprus": ("CYP", "塞浦路斯"),
    "croatia": ("HRV", "克罗地亚"), "slovenia": ("SVN", "斯洛文尼亚"), "serbia": ("SRB", "塞尔维亚"),
    "bosnia and herzegovina": ("BIH", "波黑"), "montenegro": ("MNE", "黑山"), "north macedonia": ("MKD", "北马其顿"),
    "albania": ("ALB", "阿尔巴尼亚"), "kosovo": ("XKX", "科索沃"), "moldova": ("MDA", "摩尔多瓦"),
    "ukraine": ("UKR", "乌克兰"), "belarus": ("BLR", "白俄罗斯"), "russia": ("RUS", "俄罗斯"),
    "latvia": ("LVA", "拉脱维亚"), "lithuania": ("LTU", "立陶宛"), "estonia": ("EST", "爱沙尼亚"),
    "finland": ("FIN", "芬兰"), "sweden": ("SWE", "瑞典"), "norway": ("NOR", "挪威"),
    "denmark": ("DNK", "丹麦"), "iceland": ("ISL", "冰岛"), "ireland": ("IRL", "爱尔兰"),
    "malta": ("MLT", "马耳他"), "andorra": ("AND", "安道尔"), "monaco": ("MCO", "摩纳哥"),
    "san marino": ("SMR", "圣马力诺"), "liechtenstein": ("LIE", "列支敦士登"),
    # 大洋洲
    "australia": ("AUS", "澳大利亚"), "new zealand": ("NZL", "新西兰"), "fiji": ("FJI", "斐济"),
    "solomon islands": ("SLB", "所罗门群岛"), "vanuatu": ("VUT", "瓦努阿图"), "samoa": ("WSM", "萨摩亚"),
    "tonga": ("TON", "汤加"), "kiribati": ("KIR", "基里巴斯"), "marshall islands": ("MHL", "马绍尔群岛"),
    "micronesia": ("FSM", "密克罗尼西亚"), "nauru": ("NRU", "瑙鲁"),
    # 中文别名（中文来源兜底）
    "中国": ("CHN", "中国"), "美国": ("USA", "美国"), "巴西": ("BRA", "巴西"), "印度": ("IND", "印度"),
    "印度尼西亚": ("IDN", "印度尼西亚"), "泰国": ("THA", "泰国"), "越南": ("VNM", "越南"), "日本": ("JPN", "日本"),
    "韩国": ("KOR", "韩国"), "德国": ("DEU", "德国"), "法国": ("FRA", "法国"), "英国": ("GBR", "英国"),
    "俄罗斯": ("RUS", "俄罗斯"), "澳大利亚": ("AUS", "澳大利亚"), "加拿大": ("CAN", "加拿大"),
    "墨西哥": ("MEX", "墨西哥"), "菲律宾": ("PHL", "菲律宾"), "马来西亚": ("MYS", "马来西亚"),
    "新加坡": ("SGP", "新加坡"), "南非": ("ZAF", "南非"), "尼日利亚": ("NGA", "尼日利亚"),
    "肯尼亚": ("KEN", "肯尼亚"), "埃塞俄比亚": ("ETH", "埃塞俄比亚"), "刚果": ("COD", "刚果民主共和国"),
    "埃及": ("EGY", "埃及"), "土耳其": ("TUR", "土耳其"), "伊朗": ("IRN", "伊朗"),
    "巴基斯坦": ("PAK", "巴基斯坦"), "孟加拉国": ("BGD", "孟加拉国"), "沙特阿拉伯": ("SAU", "沙特阿拉伯"),
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

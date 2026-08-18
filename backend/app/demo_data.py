from __future__ import annotations

from datetime import datetime, timezone

from .risk_engine import calculate_risk


NOW = "2026-08-18T13:30:00+08:00"


COUNTRY_SEEDS = [
    ("COD", "刚果民主共和国", "非洲", [23.66, -2.88], [91, 86, 78, 48, 55, 24], 18420, 628, 18.6),
    ("BRA", "巴西", "南美洲", [-51.93, -14.24], [72, 77, 83, 70, 61, 58], 32840, 312, 9.8),
    ("IND", "印度", "亚洲", [78.96, 20.59], [66, 74, 71, 87, 72, 52], 24365, 195, 14.2),
    ("USA", "美国", "北美洲", [-95.71, 37.09], [52, 64, 69, 89, 56, 82], 12730, 87, -2.1),
    ("IDN", "印度尼西亚", "亚洲", [113.92, -0.79], [64, 69, 58, 78, 76, 49], 9860, 116, 11.4),
    ("THA", "泰国", "亚洲", [100.99, 15.87], [46, 61, 55, 92, 81, 67], 6820, 31, 6.5),
    ("VNM", "越南", "亚洲", [108.28, 14.06], [48, 54, 47, 88, 70, 61], 5140, 28, 4.2),
    ("PHL", "菲律宾", "亚洲", [121.77, 12.88], [57, 63, 52, 74, 68, 46], 7470, 64, 8.1),
    ("SGP", "新加坡", "亚洲", [103.82, 1.35], [35, 44, 39, 96, 90, 94], 2310, 4, -5.6),
    ("AUS", "澳大利亚", "大洋洲", [133.78, -25.27], [32, 40, 36, 71, 44, 88], 1870, 9, -1.8),
    ("FRA", "法国", "欧洲", [2.21, 46.23], [38, 52, 43, 62, 48, 85], 3380, 17, 2.3),
    ("GBR", "英国", "欧洲", [-3.44, 55.38], [42, 57, 46, 68, 53, 86], 4020, 25, 3.8),
    ("EGY", "埃及", "非洲", [30.80, 26.82], [55, 62, 49, 51, 64, 45], 5290, 73, 7.4),
    ("MEX", "墨西哥", "北美洲", [-102.55, 23.63], [59, 67, 61, 59, 55, 50], 8140, 98, 10.7),
    ("CHN", "中国", "亚洲", [104.20, 35.86], [24, 27, 32, 0, 0, 83], 1260, 5, -12.4),
]


def _country(code: str, name: str, region: str, center: list[float], factors: list[float], cases: int, deaths: int, trend: float):
    factor_map = dict(zip(("severity", "transmission", "scale", "travel", "transit", "capacity"), factors))
    score, level = calculate_risk(factor_map)
    return {
        "code": code,
        "name": name,
        "region": region,
        "center": center,
        "risk_score": score,
        "level": level,
        "active_cases": cases,
        "deaths": deaths,
        "trend_7d": trend,
        "factors": factor_map,
        "updated_at": NOW,
    }


COUNTRIES = [_country(*seed) for seed in COUNTRY_SEEDS]


EVENTS = [
    {"id": "EVT-260818-01", "title": "刚果（金）东部猴痘病例持续增加", "country_code": "COD", "country": "刚果民主共和国", "disease": "猴痘", "event_type": "病例增长", "cases": 1247, "deaths": 37, "level": "red", "source": "WHO DONS", "published_at": "2026-08-18T10:20:00+08:00", "confidence": 0.96, "coordinates": [29.22, -1.68]},
    {"id": "EVT-260818-02", "title": "巴西北部登革热传播强度上升", "country_code": "BRA", "country": "巴西", "disease": "登革热", "event_type": "趋势突变", "cases": 8530, "deaths": 42, "level": "orange", "source": "ProMED-mail", "published_at": "2026-08-18T09:42:00+08:00", "confidence": 0.84, "coordinates": [-60.02, -3.12]},
    {"id": "EVT-260818-03", "title": "印度报告新一轮尼帕病毒聚集性病例", "country_code": "IND", "country": "印度", "disease": "尼帕病毒病", "event_type": "突发疫情", "cases": 18, "deaths": 4, "level": "orange", "source": "WHO DONS", "published_at": "2026-08-18T08:16:00+08:00", "confidence": 0.93, "coordinates": [76.27, 10.85]},
    {"id": "EVT-260817-04", "title": "印度尼西亚人感染禽流感风险通报", "country_code": "IDN", "country": "印度尼西亚", "disease": "H5N1禽流感", "event_type": "新发病例", "cases": 6, "deaths": 1, "level": "orange", "source": "ECDC CDTR", "published_at": "2026-08-17T22:05:00+08:00", "confidence": 0.91, "coordinates": [106.85, -6.21]},
    {"id": "EVT-260817-05", "title": "泰国南部基孔肯雅热活动增强", "country_code": "THA", "country": "泰国", "disease": "基孔肯雅热", "event_type": "病例增长", "cases": 632, "deaths": 0, "level": "yellow", "source": "HealthMap", "published_at": "2026-08-17T18:30:00+08:00", "confidence": 0.78, "coordinates": [100.50, 7.01]},
    {"id": "EVT-260817-06", "title": "墨西哥多州报告西尼罗热病例", "country_code": "MEX", "country": "墨西哥", "disease": "西尼罗热", "event_type": "地域扩散", "cases": 94, "deaths": 3, "level": "yellow", "source": "US CDC", "published_at": "2026-08-17T16:12:00+08:00", "confidence": 0.88, "coordinates": [-102.55, 23.63]},
    {"id": "EVT-260817-07", "title": "欧洲西部新冠病毒变异株监测更新", "country_code": "FRA", "country": "法国", "disease": "新型冠状病毒感染", "event_type": "变异株监测", "cases": 2130, "deaths": 8, "level": "yellow", "source": "ECDC CDTR", "published_at": "2026-08-17T14:55:00+08:00", "confidence": 0.95, "coordinates": [2.35, 48.86]},
    {"id": "EVT-260816-08", "title": "菲律宾中部麻疹免疫空白人群增加", "country_code": "PHL", "country": "菲律宾", "disease": "麻疹", "event_type": "风险提示", "cases": 286, "deaths": 2, "level": "yellow", "source": "WHO GHO", "published_at": "2026-08-16T20:11:00+08:00", "confidence": 0.89, "coordinates": [123.89, 10.32]},
]


ALERTS = [
    {"id": "ALT-20260818-001", "title": "猴痘跨境输入风险预警", "level": "red", "country": "刚果民主共和国", "disease": "猴痘", "score": 83.1, "status": "active", "issued_at": "2026-08-18T10:30:00+08:00", "advice": "对14天内有刚果（金）旅居史人员实施重点检疫与症状筛查"},
    {"id": "ALT-20260818-002", "title": "登革热病例快速增长预警", "level": "orange", "country": "巴西", "disease": "登革热", "score": 73.6, "status": "active", "issued_at": "2026-08-18T09:50:00+08:00", "advice": "加强来自重点州旅客健康申报核验与媒介生物监测"},
    {"id": "ALT-20260818-003", "title": "尼帕病毒聚集性疫情关注", "level": "orange", "country": "印度", "disease": "尼帕病毒病", "score": 70.2, "status": "active", "issued_at": "2026-08-18T08:25:00+08:00", "advice": "关注发热及神经系统症状，异常人员转交指定医疗机构"},
    {"id": "ALT-20260817-004", "title": "禽流感人感染事件关注", "level": "orange", "country": "印度尼西亚", "disease": "H5N1禽流感", "score": 66.4, "status": "active", "issued_at": "2026-08-17T22:20:00+08:00", "advice": "询问活禽接触史并加强异常健康申报核验"},
]


RISK_HISTORY = [
    {"date": f"2026-08-{day:02d}", "global": global_score, "asia": asia, "africa": africa, "americas": americas}
    for day, global_score, asia, africa, americas in [
        (5, 47, 45, 51, 46), (6, 48, 46, 52, 47), (7, 48, 47, 53, 47), (8, 50, 49, 55, 49),
        (9, 51, 50, 57, 50), (10, 52, 52, 59, 51), (11, 54, 53, 62, 53), (12, 53, 52, 63, 52),
        (13, 55, 54, 66, 54), (14, 57, 56, 70, 56), (15, 59, 58, 74, 58), (16, 61, 61, 78, 60),
        (17, 63, 64, 81, 62), (18, 65, 66, 84, 64),
    ]
]


TRANSFER_LINKS = [
    {"id": "L1", "origin": "刚果民主共和国", "destination": "中国", "source": [23.66, -2.88], "target": [116.4, 39.9], "risk": 83, "volume": 26, "via": "埃塞俄比亚"},
    {"id": "L2", "origin": "巴西", "destination": "中国", "source": [-51.93, -14.24], "target": [121.47, 31.23], "risk": 74, "volume": 71, "via": "阿联酋"},
    {"id": "L3", "origin": "印度", "destination": "中国", "source": [78.96, 20.59], "target": [113.26, 23.13], "risk": 70, "volume": 87, "via": "新加坡"},
    {"id": "L4", "origin": "印度尼西亚", "destination": "中国", "source": [113.92, -0.79], "target": [113.26, 23.13], "risk": 66, "volume": 76, "via": "新加坡"},
    {"id": "L5", "origin": "美国", "destination": "中国", "source": [-95.71, 37.09], "target": [116.4, 39.9], "risk": 55, "volume": 89, "via": "日本"},
]


PASSENGER_FLOWS = [
    {"country": item["name"], "country_code": item["code"], "coordinates": item["center"], "index": item["factors"]["travel"], "daily_estimate": int(item["factors"]["travel"] * 18.7)}
    for item in COUNTRIES if item["code"] != "CHN"
]


RULES = [
    {"rule_id": "RISK-001", "name": "全球国家风险加权评分", "type": "risk_score", "description": "按严重性、传播速度、规模、人员往来、中转及当地能力计算风险分", "condition_json": {"all": True}, "action_json": {"weights": {"severity": 0.25, "transmission": 0.25, "scale": 0.15, "travel": 0.15, "transit": 0.10, "capacity": 0.10}}, "version": 8, "status": "published", "priority": 10, "updated_at": NOW},
    {"rule_id": "ALERT-001", "name": "红色预警阈值", "type": "alert_level", "description": "国家综合风险分达到80分触发红色预警", "condition_json": {"risk_score": {"gte": 80}}, "action_json": {"level": "red"}, "version": 3, "status": "published", "priority": 20, "updated_at": NOW},
    {"rule_id": "TREND-001", "name": "7日病例突增", "type": "trend_change", "description": "七日病例增长率超过200%时自动升级预警", "condition_json": {"growth_7d": {"gt": 200}}, "action_json": {"upgrade_level": 1, "notify": True}, "version": 5, "status": "published", "priority": 30, "updated_at": NOW},
    {"rule_id": "PAX-001", "name": "红色国家旅居史匹配", "type": "passenger_match", "description": "14天内到访红色风险国家的旅客进入重点布控", "condition_json": {"travel_days": {"lte": 14}, "country_level": "red"}, "action_json": {"passenger_level": "red", "control": "priority"}, "version": 6, "status": "published", "priority": 5, "updated_at": NOW},
    {"rule_id": "PORT-001", "name": "机场橙色预警布控", "type": "port_advice", "description": "机场口岸对橙色来源地旅客加强申报核验并抽检", "condition_json": {"port_type": "airport", "level": "orange"}, "action_json": {"measures": ["健康申报核验", "体温复测", "核酸抽检"]}, "version": 2, "status": "draft", "priority": 50, "updated_at": NOW},
]


LOGS = [
    {"id": 1, "type": "transfer", "level": "info", "user": "system", "ip": "10.20.0.12", "action": "增量数据包接收", "detail": "PKG-20260818-009 验签通过，写入 248 条", "result": "success", "timestamp": "2026-08-18T13:22:16+08:00"},
    {"id": 2, "type": "collection", "level": "info", "user": "scheduler", "ip": "127.0.0.1", "action": "WHO DONS 数据采集", "detail": "新增2条，更新7条，去重14条", "result": "success", "timestamp": "2026-08-18T12:06:31+08:00"},
    {"id": 3, "type": "audit", "level": "warning", "user": "analyst01", "ip": "10.20.8.32", "action": "规则在线测试", "detail": "测试规则 TREND-001 v5", "result": "success", "timestamp": "2026-08-18T11:48:04+08:00"},
    {"id": 4, "type": "security", "level": "warning", "user": "unknown", "ip": "10.20.9.77", "action": "用户登录", "detail": "连续第3次密码错误", "result": "failed", "timestamp": "2026-08-18T10:37:52+08:00"},
]


# Intentionally coarse local boundaries; the frontend merges these risk properties into its
# bundled Natural Earth atlas so the intranet build has no runtime internet dependency.
COUNTRY_BOUNDS = {
    "COD": [[12, -13], [31, -13], [31, 5], [12, 5], [12, -13]],
    "BRA": [[-74, -34], [-34, -34], [-34, 5], [-74, 5], [-74, -34]],
    "IND": [[68, 7], [89, 7], [89, 35], [68, 35], [68, 7]],
    "USA": [[-125, 25], [-67, 25], [-67, 49], [-125, 49], [-125, 25]],
    "IDN": [[95, -11], [141, -11], [141, 6], [95, 6], [95, -11]],
    "THA": [[97, 5], [106, 5], [106, 21], [97, 21], [97, 5]],
    "VNM": [[102, 8], [110, 8], [110, 24], [102, 24], [102, 8]],
    "PHL": [[116, 5], [127, 5], [127, 20], [116, 20], [116, 5]],
    "SGP": [[103.5, 1.1], [104.1, 1.1], [104.1, 1.6], [103.5, 1.6], [103.5, 1.1]],
    "AUS": [[113, -44], [154, -44], [154, -10], [113, -10], [113, -44]],
    "FRA": [[-5, 42], [8, 42], [8, 51], [-5, 51], [-5, 42]],
    "GBR": [[-8, 50], [2, 50], [2, 59], [-8, 59], [-8, 50]],
    "EGY": [[25, 22], [36, 22], [36, 32], [25, 32], [25, 22]],
    "MEX": [[-118, 14], [-86, 14], [-86, 33], [-118, 33], [-118, 14]],
    "CHN": [[73, 18], [135, 18], [135, 54], [73, 54], [73, 18]],
}


def geojson() -> dict:
    return {
        "type": "FeatureCollection",
        "features": [
            {
                "type": "Feature",
                "id": country["code"],
                "properties": {key: country[key] for key in ("code", "name", "region", "risk_score", "level", "active_cases", "trend_7d")},
                "geometry": {"type": "Polygon", "coordinates": [COUNTRY_BOUNDS[country["code"]]]},
            }
            for country in COUNTRIES
        ],
        "generated_at": datetime.now(timezone.utc).isoformat(),
    }

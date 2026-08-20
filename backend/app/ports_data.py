"""中国口岸库种子数据（海、陆、空、铁全量主要口岸）。

字段说明：
    name    口岸名称
    type    口岸类型：sea 海港 / land 陆路 / air 空港 / rail 铁路
    lng     经度（WGS84）
    lat     纬度（WGS84）
    risk    入境风险等级：red 高 / orange 较高 / yellow 中 / blue 低
"""

PORTS: list[dict] = [
    # ---- 空港口岸（国际航空口岸） ----
    {"name": "北京首都国际机场", "type": "air", "lng": 116.60, "lat": 40.08, "risk": "red"},
    {"name": "上海浦东国际机场", "type": "air", "lng": 121.80, "lat": 31.14, "risk": "red"},
    {"name": "广州白云国际机场", "type": "air", "lng": 113.30, "lat": 23.39, "risk": "red"},
    {"name": "深圳宝安国际机场", "type": "air", "lng": 113.80, "lat": 22.64, "risk": "orange"},
    {"name": "成都天府国际机场", "type": "air", "lng": 104.40, "lat": 30.32, "risk": "orange"},
    {"name": "昆明长水国际机场", "type": "air", "lng": 102.90, "lat": 25.10, "risk": "red"},
    {"name": "西安咸阳国际机场", "type": "air", "lng": 108.70, "lat": 34.45, "risk": "orange"},
    {"name": "乌鲁木齐地窝堡国际机场", "type": "air", "lng": 87.47, "lat": 43.90, "risk": "orange"},
    {"name": "哈尔滨太平国际机场", "type": "air", "lng": 126.25, "lat": 45.62, "risk": "orange"},
    {"name": "青岛胶东国际机场", "type": "air", "lng": 120.10, "lat": 36.36, "risk": "yellow"},
    {"name": "厦门高崎国际机场", "type": "air", "lng": 118.13, "lat": 24.54, "risk": "orange"},
    {"name": "大连周水子国际机场", "type": "air", "lng": 121.50, "lat": 38.90, "risk": "yellow"},
    {"name": "武汉天河国际机场", "type": "air", "lng": 114.20, "lat": 30.78, "risk": "yellow"},
    {"name": "重庆江北国际机场", "type": "air", "lng": 106.64, "lat": 29.72, "risk": "yellow"},
    {"name": "杭州萧山国际机场", "type": "air", "lng": 120.43, "lat": 30.23, "risk": "yellow"},
    {"name": "南京禄口国际机场", "type": "air", "lng": 118.86, "lat": 31.74, "risk": "yellow"},
    {"name": "郑州新郑国际机场", "type": "air", "lng": 113.84, "lat": 34.52, "risk": "blue"},
    {"name": "海口美兰国际机场", "type": "air", "lng": 110.45, "lat": 19.93, "risk": "yellow"},

    # ---- 海港口岸（国际航运口岸） ----
    {"name": "上海港", "type": "sea", "lng": 121.50, "lat": 31.40, "risk": "red"},
    {"name": "深圳盐田港", "type": "sea", "lng": 114.30, "lat": 22.58, "risk": "orange"},
    {"name": "宁波舟山港", "type": "sea", "lng": 121.90, "lat": 29.95, "risk": "orange"},
    {"name": "广州港", "type": "sea", "lng": 113.50, "lat": 23.10, "risk": "red"},
    {"name": "青岛港", "type": "sea", "lng": 120.30, "lat": 36.08, "risk": "orange"},
    {"name": "天津港", "type": "sea", "lng": 117.70, "lat": 38.98, "risk": "orange"},
    {"name": "大连港", "type": "sea", "lng": 121.60, "lat": 38.92, "risk": "orange"},
    {"name": "厦门港", "type": "sea", "lng": 118.10, "lat": 24.45, "risk": "yellow"},
    {"name": "连云港港", "type": "sea", "lng": 119.40, "lat": 34.70, "risk": "yellow"},
    {"name": "秦皇岛港", "type": "sea", "lng": 119.60, "lat": 39.90, "risk": "yellow"},
    {"name": "营口港", "type": "sea", "lng": 122.10, "lat": 40.60, "risk": "yellow"},
    {"name": "日照港", "type": "sea", "lng": 119.50, "lat": 35.40, "risk": "blue"},
    {"name": "烟台港", "type": "sea", "lng": 121.40, "lat": 37.55, "risk": "blue"},
    {"name": "珠海港", "type": "sea", "lng": 113.30, "lat": 21.95, "risk": "yellow"},

    # ---- 陆路口岸（边境公路口岸） ----
    {"name": "满洲里公路口岸", "type": "land", "lng": 117.40, "lat": 49.60, "risk": "orange"},
    {"name": "二连浩特公路口岸", "type": "land", "lng": 111.98, "lat": 43.65, "risk": "orange"},
    {"name": "霍尔果斯公路口岸", "type": "land", "lng": 80.40, "lat": 44.20, "risk": "orange"},
    {"name": "阿拉山口公路口岸", "type": "land", "lng": 82.58, "lat": 45.17, "risk": "yellow"},
    {"name": "友谊关口岸", "type": "land", "lng": 106.70, "lat": 21.98, "risk": "red"},
    {"name": "瑞丽口岸", "type": "land", "lng": 97.85, "lat": 24.00, "risk": "red"},
    {"name": "磨憨口岸", "type": "land", "lng": 101.68, "lat": 21.18, "risk": "red"},
    {"name": "绥芬河公路口岸", "type": "land", "lng": 131.15, "lat": 44.40, "risk": "orange"},
    {"name": "珲春口岸", "type": "land", "lng": 130.36, "lat": 42.86, "risk": "orange"},
    {"name": "樟木口岸", "type": "land", "lng": 85.98, "lat": 27.98, "risk": "yellow"},
    {"name": "红其拉甫口岸", "type": "land", "lng": 75.42, "lat": 36.85, "risk": "yellow"},
    {"name": "东兴口岸", "type": "land", "lng": 107.97, "lat": 21.54, "risk": "red"},
    {"name": "吉隆口岸", "type": "land", "lng": 85.30, "lat": 28.85, "risk": "yellow"},
    {"name": "畹町口岸", "type": "land", "lng": 97.90, "lat": 24.10, "risk": "orange"},

    # ---- 铁路口岸（国际铁路口岸） ----
    {"name": "满洲里铁路口岸", "type": "rail", "lng": 117.40, "lat": 49.60, "risk": "orange"},
    {"name": "二连浩特铁路口岸", "type": "rail", "lng": 111.98, "lat": 43.65, "risk": "orange"},
    {"name": "阿拉山口铁路口岸", "type": "rail", "lng": 82.58, "lat": 45.17, "risk": "orange"},
    {"name": "霍尔果斯铁路口岸", "type": "rail", "lng": 80.40, "lat": 44.20, "risk": "orange"},
    {"name": "绥芬河铁路口岸", "type": "rail", "lng": 131.15, "lat": 44.40, "risk": "yellow"},
    {"name": "凭祥铁路口岸", "type": "rail", "lng": 106.75, "lat": 22.10, "risk": "red"},
    {"name": "磨憨铁路口岸", "type": "rail", "lng": 101.68, "lat": 21.18, "risk": "red"},
]

#!/usr/bin/env python3
"""模拟全球入境旅客数据生成器并导入内网平台。

通过内网 API /api/v1/passengers 分批导入，字段完全符合 PassengerCreate schema。
用法示例：
    python3 scripts/simulate_passengers.py --count 500000 --date 2026-08-19
    python3 scripts/simulate_passengers.py --count 5000 --dry-run
"""

from __future__ import annotations

import argparse
import random
import sys
import time
from datetime import date, datetime, timedelta, timezone

import httpx

# 全球主要国家/地区客流权重（按中国国际入境客流大致比例）
# (国家, 语言键, 城市列表[(城市,机场三字码)], 权重)
COUNTRIES = [
    ("日本", "jp", [("东京", "NRT"), ("大阪", "KIX"), ("名古屋", "NGO"), ("福冈", "FUK"), ("札幌", "CTS")], 130),
    ("韩国", "kr", [("首尔", "ICN"), ("釜山", "PUS"), ("济州", "CJU")], 110),
    ("中国台湾", "tw", [("台北", "TPE"), ("高雄", "KHH"), ("台中", "RMQ")], 110),
    ("中国香港", "hk", [("香港", "HKG")], 150),
    ("中国澳门", "mo", [("澳门", "MFM")], 30),
    ("泰国", "th", [("曼谷", "BKK"), ("普吉", "HKT"), ("清迈", "CNX")], 85),
    ("越南", "vn", [("河内", "HAN"), ("胡志明市", "SGN"), ("岘港", "DAD")], 80),
    ("新加坡", "sg", [("新加坡", "SIN")], 65),
    ("马来西亚", "my", [("吉隆坡", "KUL"), ("槟城", "PEN"), ("亚庇", "BKI")], 60),
    ("美国", "us", [("洛杉矶", "LAX"), ("旧金山", "SFO"), ("纽约", "JFK"), ("芝加哥", "ORD"), ("西雅图", "SEA"), ("波士顿", "BOS")], 90),
    ("加拿大", "ca", [("温哥华", "YVR"), ("多伦多", "YYZ"), ("蒙特利尔", "YUL")], 25),
    ("澳大利亚", "au", [("悉尼", "SYD"), ("墨尔本", "MEL"), ("布里斯班", "BNE")], 35),
    ("新西兰", "nz", [("奥克兰", "AKL")], 8),
    ("德国", "de", [("法兰克福", "FRA"), ("慕尼黑", "MUC"), ("柏林", "BER")], 30),
    ("英国", "gb", [("伦敦", "LHR"), ("曼彻斯特", "MAN"), ("爱丁堡", "EDI")], 25),
    ("法国", "fr", [("巴黎", "CDG"), ("里昂", "LYS")], 20),
    ("意大利", "it", [("罗马", "FCO"), ("米兰", "MXP")], 12),
    ("荷兰", "nl", [("阿姆斯特丹", "AMS")], 10),
    ("瑞士", "ch", [("苏黎世", "ZRH"), ("日内瓦", "GVA")], 8),
    ("西班牙", "es", [("马德里", "MAD"), ("巴塞罗那", "BCN")], 8),
    ("俄罗斯", "ru", [("莫斯科", "SVO"), ("圣彼得堡", "LED"), ("符拉迪沃斯托克", "VVO")], 30),
    ("瑞典", "se", [("斯德哥尔摩", "ARN")], 5),
    ("奥地利", "at", [("维也纳", "VIE")], 5),
    ("波兰", "pl", [("华沙", "WAW")], 5),
    ("葡萄牙", "pt", [("里斯本", "LIS")], 3),
    ("匈牙利", "hu", [("布达佩斯", "BUD")], 3),
    ("芬兰", "fi", [("赫尔辛基", "HEL")], 3),
    ("印度", "in", [("新德里", "DEL"), ("孟买", "BOM"), ("班加罗尔", "BLR"), ("加尔各答", "CCU")], 55),
    ("巴基斯坦", "pk", [("伊斯兰堡", "ISB"), ("卡拉奇", "KHI"), ("拉合尔", "LHE")], 25),
    ("孟加拉国", "bd", [("达卡", "DAC")], 12),
    ("尼泊尔", "np", [("加德满都", "KTM")], 10),
    ("斯里兰卡", "lk", [("科伦坡", "CMB")], 8),
    ("印度尼西亚", "id", [("雅加达", "CGK"), ("巴厘岛", "DPS"), ("泗水", "SUB")], 35),
    ("菲律宾", "ph", [("马尼拉", "MNL"), ("宿务", "CEB")], 40),
    ("缅甸", "mm", [("仰光", "RGN"), ("曼德勒", "MDL")], 15),
    ("柬埔寨", "kh", [("金边", "PNH"), ("暹粒", "REP")], 12),
    ("老挝", "la", [("万象", "VTE")], 6),
    ("蒙古", "mn", [("乌兰巴托", "UBN")], 8),
    ("哈萨克斯坦", "kz", [("阿拉木图", "ALA"), ("阿斯塔纳", "NQZ")], 15),
    ("乌兹别克斯坦", "uz", [("塔什干", "TAS")], 6),
    ("阿联酋", "ae", [("迪拜", "DXB"), ("阿布扎比", "AUH")], 30),
    ("卡塔尔", "qa", [("多哈", "DOH")], 10),
    ("沙特阿拉伯", "sa", [("利雅得", "RUH"), ("吉达", "JED")], 12),
    ("土耳其", "tr", [("伊斯坦布尔", "IST"), ("安卡拉", "ESB")], 18),
    ("伊朗", "ir", [("德黑兰", "IKA")], 8),
    ("以色列", "il", [("特拉维夫", "TLV")], 6),
    ("埃及", "eg", [("开罗", "CAI")], 5),
    ("南非", "za", [("约翰内斯堡", "JNB"), ("开普敦", "CPT")], 5),
    ("尼日利亚", "ng", [("拉各斯", "LOS")], 4),
    ("埃塞俄比亚", "et", [("亚的斯亚贝巴", "ADD")], 4),
    ("肯尼亚", "ke", [("内罗毕", "NBO")], 3),
    ("摩洛哥", "ma", [("卡萨布兰卡", "CMN")], 2),
    ("巴西", "br", [("圣保罗", "GRU"), ("里约热内卢", "GIG")], 6),
    ("阿根廷", "ar", [("布宜诺斯艾利斯", "EZE")], 3),
    ("智利", "cl", [("圣地亚哥", "SCL")], 2),
    ("秘鲁", "pe", [("利马", "LIM")], 2),
    ("墨西哥", "mx", [("墨西哥城", "MEX")], 5),
]

# 主要入境口岸（国际机场）
ENTRY_PORTS = [
    ("上海浦东国际机场", "PVG"), ("北京首都国际机场", "PEK"), ("北京大兴国际机场", "PKX"),
    ("广州白云国际机场", "CAN"), ("深圳宝安国际机场", "SZX"), ("成都天府国际机场", "TFU"),
    ("成都双流国际机场", "CTU"), ("重庆江北国际机场", "CKG"), ("昆明长水国际机场", "KMG"),
    ("西安咸阳国际机场", "XIY"), ("杭州萧山国际机场", "HGH"), ("厦门高崎国际机场", "XMN"),
    ("南京禄口国际机场", "NKG"), ("青岛胶东国际机场", "TAO"), ("大连周水子国际机场", "DLC"),
    ("沈阳桃仙国际机场", "SHE"), ("武汉天河国际机场", "WUH"), ("郑州新郑国际机场", "CGO"),
    ("长沙黄花国际机场", "CSX"), ("福州长乐国际机场", "FOC"), ("乌鲁木齐地窝堡国际机场", "URC"),
    ("哈尔滨太平国际机场", "HRB"), ("天津滨海国际机场", "TSN"), ("南宁吴圩国际机场", "NNG"),
    ("海口美兰国际机场", "HAK"), ("三亚凤凰国际机场", "SYX"),
]

# 航空公司二字码
AIRLINES = ["CA", "MU", "CZ", "HU", "MF", "3U", "HO", "ZH", "SC", "FM", "9C", "GS",
            "NH", "JL", "KE", "OZ", "TG", "SQ", "MH", "GA", "PR", "CX", "CI", "BR",
            "EK", "QR", "EY", "TK", "LH", "BA", "AF", "KL", "LX", "SU", "AA", "UA", "DL",
            "AC", "QF", "NZ", "MS", "ET", "TR"]

# 姓名库（按语言键）
SURNAMES = {
    "zh": ["王", "李", "张", "刘", "陈", "杨", "黄", "赵", "吴", "周", "徐", "孙", "马", "朱", "胡", "郭", "何", "林", "罗", "郑"],
    "en": ["Smith", "Johnson", "Williams", "Brown", "Jones", "Garcia", "Miller", "Davis", "Wilson", "Taylor"],
    "jp": ["Sato", "Suzuki", "Takahashi", "Tanaka", "Watanabe", "Ito", "Yamamoto", "Nakamura", "Kobayashi", "Kato"],
    "kr": ["Kim", "Lee", "Park", "Choi", "Jung", "Kang", "Cho", "Yoon", "Jang", "Lim"],
    "th": ["Somsak", "Chai", "Anan", "Somchai", "Prasert", "Narong", "Kitti", "Panya", "Wichai", "Sompop"],
    "vn": ["Nguyen", "Tran", "Le", "Pham", "Hoang", "Phan", "Vu", "Dang", "Bui", "Do"],
    "sg": ["Tan", "Lim", "Lee", "Ng", "Goh", "Chua", "Ong", "Wong", "Koh", "Teo"],
    "my": ["Abdullah", "Rahman", "Hassan", "Ahmad", "Ismail", "Syed", "Lim", "Tan", "Kumar", "Siti"],
    "id": ["Sutanto", "Wijaya", "Santoso", "Hidayat", "Kusuma", "Nugroho", "Pratama", "Rahman", "Setiawan", "Halim"],
    "ph": ["Santos", "Reyes", "Cruz", "Bautista", "Ocampo", "Garcia", "Mendoza", "Torres", "Flores", "Ramos"],
    "in": ["Sharma", "Verma", "Gupta", "Patel", "Kumar", "Singh", "Mehta", "Joshi", "Rao", "Reddy"],
    "ru": ["Ivanov", "Petrov", "Sidorov", "Kuznetsov", "Smirnov", "Volkov", "Fedorov", "Morozov", "Novikov", "Pavlov"],
    "de": ["Muller", "Schmidt", "Schneider", "Fischer", "Weber", "Meyer", "Wagner", "Becker", "Hoffmann", "Schulz"],
    "fr": ["Martin", "Bernard", "Dubois", "Thomas", "Robert", "Richard", "Petit", "Durand", "Leroy", "Moreau"],
    "gb": ["Smith", "Jones", "Williams", "Brown", "Taylor", "Davies", "Wilson", "Evans", "Thomas", "Roberts"],
    "it": ["Rossi", "Russo", "Ferrari", "Esposito", "Bianchi", "Romano", "Colombo", "Ricci", "Marino", "Greco"],
    "ae": ["Al-Farsi", "Al-Mansoori", "Al-Habsi", "Al-Balushi", "Al-Said", "Al-Mahri", "Al-Shehhi", "Al-Marri", "Al-Harthy", "Al-Nabhani"],
    "sa": ["Al-Saud", "Al-Qahtani", "Al-Otaibi", "Al-Harbi", "Al-Dossari", "Al-Ghamdi", "Al-Zahrani", "Al-Mutairi", "Al-Shammari", "Al-Anazi"],
    "br": ["Silva", "Santos", "Oliveira", "Souza", "Lima", "Pereira", "Ferreira", "Costa", "Rodrigues", "Almeida"],
    "tr": ["Yilmaz", "Kaya", "Demir", "Celik", "Sahin", "Yildiz", "Ozturk", "Aydin", "Arslan", "Dogan"],
    "us": ["Smith", "Johnson", "Williams", "Brown", "Jones", "Garcia", "Miller", "Davis", "Rodriguez", "Martinez", "Wilson", "Anderson"],
    "ca": ["Smith", "Tremblay", "Gagnon", "Roy", "Cote", "Bouchard", "Gauthier", "Morin", "Lavoie", "Fortin"],
    "au": ["Smith", "Jones", "Williams", "Brown", "Wilson", "Taylor", "Johnson", "White", "Martin", "Anderson"],
    "nz": ["Smith", "Williams", "Brown", "Taylor", "Jones", "Wilson", "Clark", "Walker", "Young", "Hall"],
    "eg": ["Mohamed", "Ahmed", "Ali", "Hassan", "Ibrahim", "Khalil", "Mostafa", "Fathy", "Said", "Mahmoud"],
    "za": ["Nkosi", "Dlamini", "Mthembu", "Khumalo", "Botha", "Van der Merwe", "Naidoo", "Pillay", "Mokoena", "Ndlovu"],
    "kz": ["Bekov", "Sultanov", "Aliev", "Kairatov", "Omarov", "Saparov", "Zhukov", "Askarov", "Nazarbayev", "Tulegenov"],
    "pk": ["Khan", "Ahmed", "Ali", "Hussain", "Malik", "Shah", "Butt", "Qureshi", "Raza", "Sheikh"],
    "bd": ["Rahman", "Hossain", "Ahmed", "Islam", "Miah", "Uddin", "Khan", "Haque", "Chowdhury", "Sarker"],
    "np": ["Sharma", "Gurung", "Tamang", "Rai", "Thapa", "Magar", "Sherpa", "Lama", "KC", "Rijal"],
    "lk": ["Fernando", "Perera", "Silva", "Jayawardena", "Bandara", "Wickramasinghe", "Dissanayake", "Rajapaksa", "De Silva", "Gunasekara"],
    "ir": ["Hosseini", "Ahmadi", "Mohammadi", "Karimi", "Sadeghi", "Rezaei", "Moradi", "Jafari", "Nazari", "Abbasi"],
    "tw": ["Lin", "Chen", "Huang", "Chang", "Lee", "Wang", "Wu", "Liu", "Tsai", "Yang"],
    "hk": ["Chan", "Lee", "Cheung", "Wong", "Ho", "Lam", "Ng", "Leung", "Yau", "Tse"],
    "mo": ["Cheong", "Ho", "Lei", "Chao", "Lo", "U", "Tam", "Ng", "Ieong", "Mak"],
    "il": ["Cohen", "Levi", "Mizrahi", "Peretz", "Biton", "Dahan", "Friedman", "Azulay", "Katz", "Yosef"],
    "fi": ["Korhonen", "Virtanen", "Makinen", "Nieminen", "Makela", "Hamalainen", "Laine", "Heikkinen", "Koskinen", "Jarvinen"],
    "se": ["Andersson", "Johansson", "Karlsson", "Nilsson", "Eriksson", "Larsson", "Olsson", "Persson", "Svensson", "Gustafsson"],
    "at": ["Gruber", "Huber", "Bauer", "Wagner", "Muller", "Pichler", "Steiner", "Moser", "Mayer", "Hofer"],
    "pl": ["Nowak", "Kowalski", "Wisniewski", "Wojcik", "Kowalczyk", "Kaminski", "Lewandowski", "Zielinski", "Szymanski", "Wozniak"],
    "pt": ["Silva", "Santos", "Ferreira", "Pereira", "Oliveira", "Costa", "Rodrigues", "Martins", "Jesus", "Sousa"],
    "hu": ["Nagy", "Kovacs", "Toth", "Szabo", "Horvath", "Varga", "Kiss", "Molnar", "Nemeth", "Farkas"],
    "es": ["Garcia", "Rodriguez", "Gonzalez", "Fernandez", "Lopez", "Martinez", "Sanchez", "Perez", "Gomez", "Martin"],
    "nl": ["De Jong", "Jansen", "De Vries", "Van den Berg", "Van Dijk", "Bakker", "Janssen", "Visser", "Smit", "Meijer"],
    "ch": ["Muller", "Meier", "Schmid", "Keller", "Weber", "Huber", "Schneider", "Meyer", "Fischer", "Brunner"],
    "mx": ["Garcia", "Hernandez", "Martinez", "Lopez", "Gonzalez", "Perez", "Sanchez", "Ramirez", "Flores", "Torres"],
    "mn": ["Bat-Erdene", "Enkhbold", "Bold", "Tuvshin", "Ganbold", "Davaa", "Munkh", "Battulga", "Sukhbaatar", "Chuluun"],
    "ng": ["Okafor", "Adeyemi", "Obi", "Eze", "Uche", "Nwosu", "Abubakar", "Okonkwo", "Bello", "Musa"],
    "et": ["Tesfaye", "Mekonnen", "Haile", "Alemu", "Girma", "Tadesse", "Berhanu", "Abebe", "Kebede", "Demissie"],
    "ke": ["Mwangi", "Otieno", "Kamau", "Ochieng", "Njuguna", "Wanjiru", "Njeri", "Kipchoge", "Achieng", "Wambui"],
    "ar": ["Garcia", "Fernandez", "Gonzalez", "Rodriguez", "Martinez", "Perez", "Lopez", "Sanchez", "Romero", "Diaz"],
    "cl": ["Gonzalez", "Munoz", "Rojas", "Diaz", "Perez", "Soto", "Contreras", "Silva", "Martinez", "Sepulveda"],
    "pe": ["Quispe", "Flores", "Garcia", "Rodriguez", "Chavez", "Vasquez", "Ramos", "Castillo", "Huaman", "Cordova"],
    "uz": ["Karimov", "Rasulov", "Yusupov", "Tashkentov", "Abdullaev", "Mirzaev", "Umarov", "Saidov", "Nazarov", "Khodjaev"],
    "mm": ["Kyaw", "Aung", "Zaw", "Hla", "Win", "Myint", "Thant", "Naing", "Tun", "Htet"],
    "kh": ["Sok", "Chan", "Sophea", "Vannak", "Dara", "Rithy", "Borey", "Kosal", "Sreymom", "Piseth"],
    "la": ["Phommachanh", "Sisavath", "Inthavong", "Chanthavong", "Vongsa", "Keomany", "Bounmy", "Sengsavanh", "Latsamy", "Pheng"],
    "qa": ["Al-Thani", "Al-Kuwari", "Al-Marri", "Al-Hajri", "Al-Sulaiti", "Al-Mohannadi", "Al-Naimi", "Al-Kaabi", "Al-Malki", "Al-Baker"],
    "uz": ["Karimov", "Rasulov", "Yusupov", "Abdullaev", "Mirzaev", "Umarov", "Saidov", "Nazarov", "Khodjaev", "Islomov"],
}

GIVEN = ["James", "John", "Robert", "Michael", "William", "David", "Richard", "Joseph", "Thomas", "Charles",
         "Mary", "Patricia", "Jennifer", "Linda", "Elizabeth", "Barbara", "Susan", "Jessica", "Sarah", "Karen",
         "Akira", "Hiroshi", "Yuki", "Kenji", "Yumi", "Takeshi", "Aiko", "Ryo", "Sakura", "Daiki",
         "Min-ji", "Seo-yeon", "Ji-hoon", "Min-seok", "Hye-jin", "Jae-won", "Soo-jin", "Eun-ji", "Sang-hoon", "Young-hee"]
GIVEN_ZH = ["伟", "芳", "娜", "敏", "静", "磊", "军", "洋", "勇", "艳", "杰", "娟", "涛", "明", "超", "秀兰", "霞", "平", "刚", "桂英"]

# 健康申报异常率（约 3% 旅客不申报，增加风险分析多样性）
DECLARATION_FALSE_RATE = 0.03
# 中转概率（约 18% 旅客经第三方国家中转）
TRANSIT_RATE = 0.18
TRANSIT_HUBS = ["新加坡", "阿联酋", "卡塔尔", "土耳其", "日本", "韩国", "泰国", "中国香港", "中国澳门"]


def build_name(nationality: str, lang: str, rng: random.Random) -> tuple[str, str]:
    """返回 (姓名, 性别)，港澳台用中文名+证件差异"""
    if lang in {"zh", "zh-hk", "zh-mo", "zh-tw"}:
        surnames = SURNAMES.get("zh", SURNAMES["en"])
        surname = rng.choice(surnames)
        given = rng.choice(GIVEN_ZH)
        gender = rng.choice(["男", "女"])
        return f"{surname}{given}", gender
    surnames = SURNAMES.get(lang) or SURNAMES["en"]
    return f"{rng.choice(GIVEN)} {rng.choice(surnames)}", rng.choice(["M", "F"])


def build_document(nationality: str, lang: str, rng: random.Random) -> tuple[str, str]:
    """返回 (证件类型, 证件号)"""
    if lang in {"zh-hk", "zh-mo", "zh-tw"}:
        doc_map = {"zh-hk": ("回乡证", "R"), "zh-mo": ("港澳通行证", "M"), "zh-tw": ("台胞证", "T")}
        doc_type, prefix = doc_map[lang]
        return doc_type, f"{prefix}{rng.randrange(1000000, 9999999)}"
    prefix_map = {"en": "E", "jp": "TR", "kr": "M", "sg": "S", "de": "C", "fr": "F",
                  "ru": "N", "ae": "A", "th": "T", "vn": "B", "my": "H", "in": "P", "au": "E"}
    return "护照", f"{prefix_map.get(lang, 'P')}{rng.randrange(100000000, 999999999)}"


def build_flight(origin_code: str, rng: random.Random) -> str:
    return f"{rng.choice(AIRLINES)}{rng.randrange(100, 9999)}"


def build_travel_history(nationality: str, arrival: date, rng: random.Random) -> list[dict]:
    history: list[dict] = []
    if rng.random() < 0.85:  # 多数旅客有旅居史
        days_back = rng.randint(2, 14)
        entry = arrival - timedelta(days=days_back)
        exit_d = arrival - timedelta(days=rng.randint(0, days_back - 1))
        if exit_d > entry:
            history.append({"country": nationality, "entry_date": entry.isoformat(), "exit_date": exit_d.isoformat()})
    if rng.random() < 0.15:  # 少量多国旅居
        transit = rng.choice(TRANSIT_HUBS)
        if not any(item["country"] == transit for item in history):
            days_back = rng.randint(3, 12)
            entry = arrival - timedelta(days=days_back)
            exit_d = arrival - timedelta(days=rng.randint(1, days_back - 2))
            if exit_d > entry:
                history.append({"country": transit, "entry_date": entry.isoformat(), "exit_date": exit_d.isoformat()})
    return history


def build_transit(rng: random.Random) -> list[str]:
    if rng.random() < TRANSIT_RATE:
        return [rng.choice(TRANSIT_HUBS)]
    return []


def generate_passenger(index: int, arrival: date, rng: random.Random) -> dict:
    country, lang, cities, _weight = rng.choices(COUNTRIES, weights=[c[3] for c in COUNTRIES], k=1)[0]
    city, city_code = rng.choice(cities)
    port_name, port_code = rng.choice(ENTRY_PORTS)
    name, gender = build_name(country, lang, rng)
    doc_type, doc_no = build_document(country, lang, rng)
    flight_no = build_flight(city_code, rng)
    # 入境时间集中在清晨至傍晚（国际航班到达高峰）
    hour = rng.choices(list(range(24)),
                       weights=[1, 1, 1, 1, 2, 4, 6, 6, 5, 5, 6, 7, 7, 6, 6, 5, 5, 4, 3, 2, 2, 1, 1, 1])[0]
    entry_time = datetime(arrival.year, arrival.month, arrival.day, hour, rng.randrange(0, 60), rng.randrange(0, 60), tzinfo=timezone.utc)
    birth_year = rng.randint(1950, 2015)
    return {
        "passenger_id": f"P{arrival.strftime('%Y%m%d')}{index:08d}",
        "document_type": doc_type,
        "document_number": doc_no,
        "name": name,
        "gender": gender,
        "birth_date": f"{birth_year:04d}-{rng.randint(1, 12):02d}-{rng.randint(1, 28):02d}",
        "nationality": country,
        "travel_history": build_travel_history(country, arrival, rng),
        "transit_countries": build_transit(rng),
        "entry_port": port_name,
        "entry_time": entry_time.isoformat(),
        "flight_no": flight_no,
        "seat_no": f"{rng.choice('ABCDEFGHJK')}{rng.randrange(1, 60)}",
        "health_declaration": not (rng.random() < DECLARATION_FALSE_RATE),
        "contact_info": {
            "phone": f"+{rng.choice(['86', '852', '853', '886', '1', '44', '81', '82', '65', '49', '33', '7', '61', '971', '966'])}{rng.randrange(100000000, 999999999)}",
            "email": f"user{index}{rng.randrange(100, 999)}@{rng.choice(['example.com', 'mail.com', 'test.org', 'demo.net'])}",
        },
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="模拟全球入境旅客并导入内网平台")
    parser.add_argument("--count", type=int, default=500000, help="旅客人数（默认 500000）")
    parser.add_argument("--date", default="today", help="入境日期 YYYY-MM-DD 或 today")
    parser.add_argument("--api", default="http://localhost:8002", help="内网 API 基础地址")
    parser.add_argument("--admin", default="admin", help="管理员用户名")
    parser.add_argument("--password", default="LocalAdmin@2026", help="管理员密码")
    parser.add_argument("--batch", type=int, default=2000, help="每批导入条数")
    parser.add_argument("--seed", type=int, default=42, help="随机种子")
    parser.add_argument("--dry-run", action="store_true", help="仅生成不导入")
    args = parser.parse_args()

    arrival = date.today() if args.date == "today" else datetime.strptime(args.date, "%Y-%m-%d").date()
    rng = random.Random(args.seed)
    api = args.api.rstrip("/")

    # 1. 登录获取 token
    headers: dict[str, str] = {}
    if not args.dry_run:
        print(f"[1/3] 登录内网平台 {api} ...")
        try:
            login_resp = httpx.post(f"{api}/api/v1/auth/login",
                                    json={"username": args.admin, "password": args.password}, timeout=30)
            login_resp.raise_for_status()
            headers = {"Authorization": f"Bearer {login_resp.json()['access_token']}"}
            print("      登录成功")
        except Exception as exc:
            print(f"登录失败: {exc}")
            if isinstance(exc, httpx.HTTPStatusError):
                print(f"  响应: {exc.response.text}")
            sys.exit(1)

    # 2. 生成并分批导入
    total, failed, start_time = 0, 0, time.time()
    print(f"[2/3] 生成 {args.count:,} 名旅客（日期 {arrival}，批次 {args.batch}）...")
    batch: list[dict] = []
    for index in range(1, args.count + 1):
        batch.append(generate_passenger(index, arrival, rng))
        if len(batch) >= args.batch:
            if args.dry_run:
                total += len(batch)
                print(f"      dry-run 已生成 {total:,}")
            else:
                try:
                    resp = httpx.post(f"{api}/api/v1/passengers", json=batch, headers=headers, timeout=600)
                    resp.raise_for_status()
                    total += resp.json().get("total", len(batch))
                    print(f"      已导入 {total:,} / {args.count:,}（耗时 {time.time() - start_time:.0f}s）")
                except httpx.HTTPStatusError as exc:
                    failed += len(batch)
                    print(f"      批次失败 ({exc.response.status_code}): {exc.response.text[:200]}")
                except httpx.HTTPError as exc:
                    failed += len(batch)
                    print(f"      批次错误: {exc}")
            batch = []

    # 3. 汇总
    elapsed = time.time() - start_time
    print(f"[3/3] 完成: 成功 {total:,}，失败 {failed:,}，耗时 {elapsed:.0f}s，"
          f"平均 {elapsed / max(total, 1):.4f}s/条")
    if not args.dry_run and total:
        print(f"      可通过 GET {api}/api/v1/passengers?page=1&page_size=5 验证内网数据")


if __name__ == "__main__":
    main()

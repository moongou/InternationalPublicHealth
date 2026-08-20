"""旅客数据库数据源连接能力。

参考 DeepAnalyze 的数据库连接实现，提供广泛的数据库连接能力，
特别是阿里云 ODPS / MaxCompute 与 AnalyticDB（ADS）的连接方式。

- MaxCompute / ODPS：通过 pyodps 专用驱动连接。字段映射：
  host -> endpoint，database -> project，user -> access_id，password -> access_key。
- AnalyticDB（ADS）：MySQL 版走 mysql+pymysql（analyticdb_mysql），
  PostgreSQL 版走 postgresql+psycopg2（analyticdb_postgresql）。
- 其他关系型数据库：通过 SQLAlchemy 驱动连接（mysql / postgresql / mssql /
  oracle / clickhouse 等）。

本模块只提供「连接测试 / 列出表 / 受控同步旅客数据」能力，不做任意 SQL 下推。
"""

from __future__ import annotations

import json
import time
from typing import Any, Callable

from .schemas import PassengerCreate


# ---------------------------------------------------------------------------
# 数据库类型别名与默认端口
# ---------------------------------------------------------------------------
DB_TYPE_ALIASES: dict[str, str] = {
    "mysql": "mysql",
    "rds_mysql": "mysql",
    "polardb_mysql": "mysql",
    "analyticdb_mysql": "mysql",      # ADS MySQL 版
    "ads": "mysql",                    # ADS 简称
    "gbase": "mysql",
    "postgresql": "postgresql",
    "rds_postgresql": "postgresql",
    "polardb_postgresql": "postgresql",
    "analyticdb_postgresql": "postgresql",  # ADS PostgreSQL 版
    "ads_postgresql": "postgresql",
    "mssql": "mssql",
    "sqlserver": "mssql",
    "oracle": "oracle",
    "clickhouse": "clickhouse",
    "maxcompute": "maxcompute",
    "odps": "maxcompute",
}

DB_DEFAULT_PORTS: dict[str, int] = {
    "mysql": 3306,
    "postgresql": 5432,
    "mssql": 1433,
    "oracle": 1521,
    "clickhouse": 8123,
    # maxcompute 使用 endpoint URL，无端口概念
}

DB_DRIVER_NAMES: dict[str, str] = {
    "mysql": "mysql+pymysql",
    "postgresql": "postgresql+psycopg",
    "mssql": "mssql+pymssql",
    "oracle": "oracle+cx_oracle",
    "clickhouse": "clickhouse+connect",
}

# 使用专用驱动、不走 SQLAlchemy 的类型
_NON_SQLALCHEMY_TYPES = {"maxcompute"}


def normalize_db_type(db_type: str | None) -> str:
    normalized = str(db_type or "").strip().lower()
    if not normalized:
        raise ValueError("缺少 db_type，请选择数据库类型")
    resolved = DB_TYPE_ALIASES.get(normalized)
    if not resolved:
        supported = ", ".join(sorted(set(DB_TYPE_ALIASES.values())))
        raise ValueError(f"不支持的数据库类型: {db_type}。支持: {supported}")
    return resolved


def _build_maxcompute_client(config: dict[str, Any]):
    """构建 PyODPS ODPS 客户端。

    字段映射（对齐 DeepAnalyze）：
        host -> endpoint，database -> project，
        user -> access_id，password -> access_key。
    兼容显式字段名 endpoint / project / access_id / access_key。
    """
    try:
        from odps import ODPS  # type: ignore
    except ImportError as exc:  # pragma: no cover - 依赖缺失时的提示
        raise ImportError("缺少 MaxCompute 驱动，请安装 pyodps：pip install pyodps") from exc

    endpoint = str(config.get("endpoint") or config.get("host") or "").strip()
    project = str(config.get("project") or config.get("database") or "").strip()
    access_id = str(config.get("access_id") or config.get("user") or "").strip()
    access_key = str(config.get("access_key") or config.get("password") or "").strip()
    tunnel_endpoint = str(config.get("tunnel_endpoint") or "").strip() or None

    if not endpoint:
        raise ValueError("MaxCompute 需要 endpoint 地址")
    if not project:
        raise ValueError("MaxCompute 需要 Project（database）名称")

    kwargs: dict[str, Any] = {"endpoint": endpoint}
    if tunnel_endpoint:
        kwargs["tunnel_endpoint"] = tunnel_endpoint
    return ODPS(access_id, access_key, project=project, **kwargs)


def _build_sqlalchemy_engine(db_type: str, config: dict[str, Any]):
    db_type = normalize_db_type(db_type)
    if db_type in _NON_SQLALCHEMY_TYPES:
        raise ValueError(f"{db_type} 使用专用驱动（pyodps），请使用对应连接函数")
    from sqlalchemy import create_engine

    driver = DB_DRIVER_NAMES.get(db_type)
    if not driver:
        raise ValueError(f"暂不支持数据库类型: {db_type}")

    host = str(config.get("host") or "").strip()
    port = str(config.get("port") or DB_DEFAULT_PORTS.get(db_type, "")).strip()
    database = str(config.get("database") or "").strip()
    user = str(config.get("user") or "").strip()
    password = str(config.get("password") or "").strip()

    if not host:
        raise ValueError("缺少数据库主机地址")
    if not database:
        raise ValueError("缺少数据库名称")

    from urllib.parse import quote_plus

    url = f"{driver}://{quote_plus(user)}:{quote_plus(password)}@{host}:{port}/{quote_plus(database)}"
    if db_type == "mssql":
        url += "?charset=utf8"
    connect_args: dict[str, Any] = {}
    if db_type in ("mysql", "postgresql"):
        connect_args["connect_timeout"] = 10
    return create_engine(url, pool_pre_ping=True, connect_args=connect_args)


# ---------------------------------------------------------------------------
# 连接测试 / 列出表
# ---------------------------------------------------------------------------
def test_database_connection(db_type: str, config: dict[str, Any]) -> dict[str, Any]:
    """测试数据库连接，返回连接状态与连接时长。"""
    started = time.perf_counter()
    normalized = normalize_db_type(db_type)

    if normalized == "maxcompute":
        client = _build_maxcompute_client(config)
        client.list_tables()
        latency = round((time.perf_counter() - started) * 1000, 2)
        return {
            "status": "success",
            "latency_ms": latency,
            "message": f"MaxCompute 连接成功，Project：{client.project}",
            "db_type": "maxcompute",
        }

    engine = _build_sqlalchemy_engine(normalized, config)
    try:
        with engine.connect() as conn:
            conn.exec_driver_sql("SELECT 1")
        latency = round((time.perf_counter() - started) * 1000, 2)
        return {
            "status": "success",
            "latency_ms": latency,
            "message": f"{normalized} 连接成功",
            "db_type": normalized,
        }
    finally:
        engine.dispose()


def list_database_tables(db_type: str, config: dict[str, Any], limit: int = 500) -> list[str]:
    """列出数据库中的表名（受控数量上限）。"""
    normalized = normalize_db_type(db_type)

    if normalized == "maxcompute":
        client = _build_maxcompute_client(config)
        tables: list[str] = []
        for table in client.list_tables():
            tables.append(str(table.name or "").strip())
            if len(tables) >= limit:
                break
        return tables

    from sqlalchemy import inspect

    engine = _build_sqlalchemy_engine(normalized, config)
    try:
        inspector = inspect(engine)
        names = list(inspector.get_table_names())
        return names[:limit]
    finally:
        engine.dispose()


# ---------------------------------------------------------------------------
# 受控取数：从数据库读取旅客记录，映射为 PassengerCreate
# ---------------------------------------------------------------------------
_PASSENGER_FIELD_MAP: dict[str, list[str]] = {
    "passenger_id": ["passenger_id", "pid", "旅客编号", "旅客ID", "旅客id"],
    "document_type": ["document_type", "证件类型", "证件类别"],
    "document_number": ["document_number", "证件号码", "护照号", "证件号", "证件"],
    "name": ["name", "姓名", "旅客姓名", "中文名", "旅客名"],
    "gender": ["gender", "性别"],
    "birth_date": ["birth_date", "出生日期", "生日"],
    "nationality": ["nationality", "国籍", "国籍代码"],
    "entry_port": ["entry_port", "口岸", "入境口岸"],
    "entry_time": ["entry_time", "入境时间", "到达时间", "entry_datetime", "入境时刻"],
    "flight_no": ["flight_no", "航班号", "航班"],
    "seat_no": ["seat_no", "座位号", "座位"],
    "health_declaration": ["health_declaration", "健康申报", "健康申明"],
    "travel_country": ["travel_country", "旅居国家", "旅行国家", "出发国家"],
    "travel_entry_date": ["travel_entry_date", "旅居入境日期"],
    "travel_exit_date": ["travel_exit_date", "旅居出境日期"],
    "transit_countries": ["transit_countries", "中转国家", "经停国家"],
}

_DEFAULT_PASSENGER_COLUMNS = [
    "passenger_id", "name", "document_number", "nationality", "entry_port", "entry_time",
]


def _resolve_column(columns: list[str], field: str) -> str | None:
    """将数据库列名解析为旅客字段。

    优先精确匹配（忽略大小写），其次按候选词做子串匹配。
    为避免字段间抢占（如 passenger_id 误匹配到「证件号码」），
    仅当列名包含候选词、且该列尚未被其他字段占用时才命中。
    """
    candidates = _PASSENGER_FIELD_MAP.get(field, [field])
    normalized: dict[str, str] = {}
    for col in columns:
        key = col.lower().strip()
        normalized.setdefault(key, col)

    # 第一轮：精确匹配
    for cand in candidates:
        key = cand.lower().strip()
        if key in normalized:
            return normalized[key]

    # 第二轮：子串匹配（列名包含候选词，且候选词长度 >= 2 避免过短误匹配）
    for cand in candidates:
        needle = cand.lower().strip()
        if len(needle) < 2:
            continue
        for key, original in normalized.items():
            if needle in key:
                return original
    return None


def _row_to_passenger(row: dict[str, Any], mapping: dict[str, str]) -> PassengerCreate | None:
    def pick(field: str) -> Any:
        col = mapping.get(field)
        if not col:
            return None
        return row.get(col)

    passenger_id = pick("passenger_id")
    document_number = pick("document_number")
    name = pick("name")
    nationality = pick("nationality")
    entry_port = pick("entry_port")
    entry_time = pick("entry_time")

    # 必需字段缺失时跳过该行
    if not passenger_id or not name or not nationality or not entry_port or not entry_time:
        return None

    travel_country = pick("travel_country")
    travel_history: list[dict[str, Any]] = []
    if travel_country:
        travel_entry = pick("travel_entry_date")
        travel_exit = pick("travel_exit_date")
        # 旅居史日期为必填，缺失时跳过该行（计入 skipped）
        if not travel_entry or not travel_exit:
            return None
        travel_history = [{
            "country": str(travel_country),
            "entry_date": travel_entry,
            "exit_date": travel_exit,
        }]

    transit = pick("transit_countries")
    if isinstance(transit, str):
        transit_countries = [v for v in transit.replace("，", ",").split(",") if v.strip()]
    elif isinstance(transit, list):
        transit_countries = [str(v) for v in transit if v]
    else:
        transit_countries = []

    health = pick("health_declaration")
    if health is None:
        health_declaration = True
    elif isinstance(health, bool):
        health_declaration = health
    else:
        health_declaration = str(health).strip().lower() not in {"0", "false", "no", "否", "无"}

    try:
        return PassengerCreate(
            passenger_id=str(passenger_id).strip(),
            document_type=str(pick("document_type") or "护照"),
            document_number=str(document_number).strip(),
            name=str(name).strip(),
            gender=str(pick("gender")) if pick("gender") else None,
            birth_date=pick("birth_date"),
            nationality=str(nationality).strip(),
            travel_history=travel_history,
            transit_countries=transit_countries,
            entry_port=str(entry_port).strip(),
            entry_time=entry_time,
            flight_no=str(pick("flight_no")) if pick("flight_no") else None,
            seat_no=str(pick("seat_no")) if pick("seat_no") else None,
            health_declaration=health_declaration,
        )
    except Exception:
        return None


def _fetch_maxcompute_rows(config: dict[str, Any], table: str, limit: int) -> list[dict[str, Any]]:
    client = _build_maxcompute_client(config)
    table_obj = client.get_table(table)
    schema = table_obj.schema
    columns = [col.name for col in schema.columns]
    rows: list[dict[str, Any]] = []
    with table_obj.open_reader(limit=limit, tunnel=True) as reader:
        for record in reader:
            row: dict[str, Any] = {}
            for idx, col in enumerate(columns):
                try:
                    row[col] = record[idx]
                except Exception:
                    row[col] = None
            rows.append(row)
    return rows


def sync_passengers_from_table(
    db_type: str,
    config: dict[str, Any],
    table: str,
    limit: int = 5000,
    progress_callback: Callable[[int], None] | None = None,
) -> dict[str, Any]:
    """从指定表受控同步旅客记录。

    返回 {matched, skipped, records}，records 为映射后的 PassengerCreate 列表。
    """
    normalized = normalize_db_type(db_type)

    if normalized == "maxcompute":
        raw_rows = _fetch_maxcompute_rows(config, table, limit)
    else:
        from sqlalchemy import text

        engine = _build_sqlalchemy_engine(normalized, config)
        try:
            with engine.connect() as conn:
                result = conn.exec_driver_sql(
                    f'SELECT * FROM "{table}" LIMIT {int(limit)}' if normalized == "postgresql"
                    else f"SELECT * FROM {table} LIMIT {int(limit)}"
                )
                columns = list(result.keys())
                raw_rows = [dict(zip(columns, row)) for row in result.fetchall()]
        finally:
            engine.dispose()

    if not raw_rows:
        return {"matched": 0, "skipped": 0, "records": [], "total_rows": 0}

    columns = list(raw_rows[0].keys())
    mapping: dict[str, str] = {}
    for field in _PASSENGER_FIELD_MAP:
        col = _resolve_column(columns, field)
        if col:
            mapping[field] = col

    records: list[PassengerCreate] = []
    skipped = 0
    for idx, row in enumerate(raw_rows):
        model = _row_to_passenger(row, mapping)
        if model:
            records.append(model)
        else:
            skipped += 1
        if progress_callback:
            progress_callback(idx + 1)

    return {
        "matched": len(records),
        "skipped": skipped,
        "records": records,
        "total_rows": len(raw_rows),
        "column_mapping": mapping,
    }

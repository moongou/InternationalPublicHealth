from __future__ import annotations

from alembic import command
from alembic.config import Config
from alembic.script import ScriptDirectory
from sqlalchemy import create_engine, inspect


def test_alembic_has_one_head_and_upgrades_to_llm_schema(tmp_path):
    config = Config("alembic.ini")
    database_path = tmp_path / "migration.db"
    config.set_main_option("sqlalchemy.url", f"sqlite:///{database_path.as_posix()}")

    script = ScriptDirectory.from_config(config)
    assert script.get_heads() == ["b61e4c7a20f9"]
    command.upgrade(config, "head")

    inspector = inspect(create_engine(f"sqlite:///{database_path.as_posix()}"))
    assert "llm_providers" in inspector.get_table_names()
    assert "bootstrap_markers" in inspector.get_table_names()
    assert {"provider_id", "provider_type", "selected_model", "is_default"} <= {
        column["name"] for column in inspector.get_columns("llm_providers")
    }

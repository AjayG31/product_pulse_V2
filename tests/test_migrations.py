from alembic.config import Config
from alembic.script import ScriptDirectory


def test_schema_version_entrypoint_is_configured_without_adding_a_migration():
    config = Config("alembic.ini")
    script = ScriptDirectory.from_config(config)

    assert config.get_main_option("script_location") == "migrations"
    assert script.get_heads() == []


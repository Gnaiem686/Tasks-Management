from workforce_persistence.alembic_config import escape_config_interpolation


def test_database_url_escapes_percent_encoded_password_for_alembic() -> None:
    database_url = "postgresql+asyncpg://user:p%24ss%7Cword@db.example/app"

    escaped = escape_config_interpolation(database_url)

    assert escaped == "postgresql+asyncpg://user:p%%24ss%%7Cword@db.example/app"
    assert database_url not in escaped

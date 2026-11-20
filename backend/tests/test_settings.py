from app.shared.settings import REPO_ROOT, Settings


def test_env_file_is_repo_root_env_local() -> None:
    assert Settings.model_config["env_file"] == REPO_ROOT / ".env.local"


def test_database_url_is_normalised_to_psycopg3(monkeypatch) -> None:
    monkeypatch.setenv("DATABASE_URL", "postgres://u:p@localhost:5432/db")
    settings = Settings(_env_file=None)
    assert settings.database_url.get_secret_value().startswith("postgresql+psycopg://")
    assert "p@localhost" not in repr(settings)  # SecretStr never leaks in repr

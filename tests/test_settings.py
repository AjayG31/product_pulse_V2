from productpulse.settings import Settings, SettingsError


def test_operational_values_are_required_and_have_no_defaults():
    try:
        Settings.from_environment({})
    except SettingsError as error:
        assert "PRODUCTPULSE_DATA_DIR" in str(error)
        assert "PRODUCTPULSE_SQLITE_BUSY_TIMEOUT_MS" in str(error)
    else:
        raise AssertionError("Settings must not invent a data path or busy-timeout value")


def test_settings_load_server_secret_without_exposing_it(tmp_path):
    secret = "sk-test-0123456789abcdef0123456789"
    settings = Settings.from_environment(
        {
            "PRODUCTPULSE_DATA_DIR": str(tmp_path),
            "PRODUCTPULSE_SQLITE_BUSY_TIMEOUT_MS": "731",
            "PRODUCTPULSE_OPENAI_API_KEY": secret,
        }
    )

    assert settings.data_dir == tmp_path
    assert settings.sqlite_busy_timeout_ms == 731
    assert settings.openai_api_key == secret
    assert secret not in repr(settings)


def test_busy_timeout_must_be_positive(tmp_path):
    try:
        Settings.from_environment(
            {
                "PRODUCTPULSE_DATA_DIR": str(tmp_path),
                "PRODUCTPULSE_SQLITE_BUSY_TIMEOUT_MS": "0",
            }
        )
    except SettingsError:
        return
    raise AssertionError("A zero busy timeout must not be accepted as an implicit policy")


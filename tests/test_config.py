import pytest
from unittest.mock import patch
from pathlib import Path

from src.config import Settings


def test_validate_raises_when_no_credentials():
    s = Settings()
    s.toshiba_user = ""
    s.toshiba_pass = ""
    with pytest.raises(ValueError, match="TOSHIBA_USER and TOSHIBA_PASS"):
        s.validate()


def test_validate_passes_with_credentials():
    s = Settings()
    s.toshiba_user = "user@example.com"
    s.toshiba_pass = "secret"
    s.validate()  # should not raise


def test_prompt_and_save_writes_env(tmp_path):
    env_file = tmp_path / ".env"
    s = Settings()
    s.host = "127.0.0.1"
    s.port = 8000

    with patch("src.config.ENV_FILE", env_file), \
         patch("builtins.input", return_value="me@test.com"), \
         patch("getpass.getpass", return_value="mypass"):
        s.prompt_and_save()

    assert s.toshiba_user == "me@test.com"
    assert s.toshiba_pass == "mypass"
    content = env_file.read_text()
    assert "TOSHIBA_USER=me@test.com" in content
    assert "TOSHIBA_PASS=mypass" in content
    assert "HOST=127.0.0.1" in content
    assert "PORT=8000" in content


def test_prompt_and_save_raises_on_empty_email(tmp_path):
    env_file = tmp_path / ".env"
    s = Settings()

    with patch("src.config.ENV_FILE", env_file), \
         patch("builtins.input", return_value=""), \
         patch("getpass.getpass", return_value="pass"):
        with pytest.raises(ValueError, match="required"):
            s.prompt_and_save()

    assert not env_file.exists()


def test_prompt_and_save_raises_on_empty_password(tmp_path):
    env_file = tmp_path / ".env"
    s = Settings()

    with patch("src.config.ENV_FILE", env_file), \
         patch("builtins.input", return_value="user@test.com"), \
         patch("getpass.getpass", return_value=""):
        with pytest.raises(ValueError, match="required"):
            s.prompt_and_save()

    assert not env_file.exists()


def test_prompt_and_save_strips_whitespace(tmp_path):
    env_file = tmp_path / ".env"
    s = Settings()

    with patch("src.config.ENV_FILE", env_file), \
         patch("builtins.input", return_value="  me@test.com  "), \
         patch("getpass.getpass", return_value="  secret  "):
        s.prompt_and_save()

    assert s.toshiba_user == "me@test.com"
    assert s.toshiba_pass == "secret"

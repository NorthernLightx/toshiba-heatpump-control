import getpass
import os
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

ENV_FILE = Path(__file__).resolve().parent.parent / ".env"


class Settings:
    def __init__(self) -> None:
        self.toshiba_user: str = os.environ.get("TOSHIBA_USER", "")
        self.toshiba_pass: str = os.environ.get("TOSHIBA_PASS", "")
        self.host: str = os.environ.get("HOST", "127.0.0.1")
        self.port: int = int(os.environ.get("PORT", "8000"))
        self.data_logging: bool = os.environ.get("DATA_LOGGING", "true").lower() in ("true", "1", "yes")

    def validate(self) -> None:
        if not self.toshiba_user or not self.toshiba_pass:
            raise ValueError(
                "TOSHIBA_USER and TOSHIBA_PASS must be set. "
                "Copy .env.example to .env and fill in your credentials."
            )

    def prompt_and_save(self) -> None:
        """Prompt for credentials interactively and save to .env."""
        print("First-run setup — enter your Toshiba Home AC Control credentials.")
        user = input("Email: ").strip()
        password = getpass.getpass("Password: ").strip()
        if not user or not password:
            raise ValueError("Email and password are required.")
        ENV_FILE.write_text(
            f"TOSHIBA_USER={user}\nTOSHIBA_PASS={password}\n"
            f"HOST={self.host}\nPORT={self.port}\n"
        )
        self.toshiba_user = user
        self.toshiba_pass = password
        print(f"Credentials saved to {ENV_FILE}")


settings = Settings()

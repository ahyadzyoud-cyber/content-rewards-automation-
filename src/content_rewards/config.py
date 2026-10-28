"""Runtime configuration. Never include credential values in diagnostics."""
import os
from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class Settings:
    database: Path = field(default_factory=lambda: Path(os.getenv("REWARDS_DATABASE", ".data/rewards.sqlite")))
    media_root: Path = field(default_factory=lambda: Path(os.getenv("REWARDS_MEDIA_ROOT", ".data/media")))
    live_publishing: bool = field(default_factory=lambda: os.getenv("REWARDS_LIVE_PUBLISHING") == "true")
    admin_token: str = field(default_factory=lambda: os.getenv("REWARDS_ADMIN_TOKEN", ""), repr=False)
    youtube_token: str = field(default_factory=lambda: os.getenv("YOUTUBE_ACCESS_TOKEN", ""), repr=False)
    youtube_refresh_token: str = field(default_factory=lambda: os.getenv("YOUTUBE_REFRESH_TOKEN", ""), repr=False)
    google_client_id: str = field(default_factory=lambda: os.getenv("GOOGLE_CLIENT_ID", ""))
    google_client_secret: str = field(default_factory=lambda: os.getenv("GOOGLE_CLIENT_SECRET", ""), repr=False)
    youtube_channel_id: str = field(default_factory=lambda: os.getenv("YOUTUBE_CHANNEL_ID", ""))
    instagram_token: str = field(default_factory=lambda: os.getenv("INSTAGRAM_ACCESS_TOKEN", ""), repr=False)
    instagram_account_id: str = field(default_factory=lambda: os.getenv("INSTAGRAM_ACCOUNT_ID", ""))
    instagram_api_version: str = field(default_factory=lambda: os.getenv("INSTAGRAM_API_VERSION", ""))
    instagram_media_host: str = field(default_factory=lambda: os.getenv("INSTAGRAM_IMMUTABLE_MEDIA_HOST", ""))

    def credential_status(self) -> dict[str, bool]:
        return {"youtube": bool(self.youtube_channel_id and (self.youtube_token or self.youtube_refresh_configured())),
                "instagram": bool(self.instagram_token and self.instagram_account_id and self.instagram_api_version),
                "api_auth": bool(self.admin_token), "live_publishing": self.live_publishing}

    def youtube_refresh_configured(self) -> bool:
        return bool(self.google_client_id and self.google_client_secret and self.youtube_refresh_token)

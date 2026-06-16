import asyncio
from pathlib import Path

from keyboards.inline import direct_link_keyboard
from services import direct_links


class TestDirectLinks:
    def test_is_large_or_long_from_duration(self, monkeypatch):
        monkeypatch.setattr(direct_links.config, "LONG_VIDEO_THRESHOLD_SECONDS", 1800)
        assert direct_links.is_large_or_long({"duration": 1900}) is True
        assert direct_links.is_large_or_long({"duration": 1200}) is False

    def test_is_large_or_long_from_file_size(self, monkeypatch):
        monkeypatch.setattr(direct_links.config, "MAX_FILE_SIZE", 50)
        assert direct_links.is_large_or_long({}, file_size=51) is True
        assert direct_links.is_large_or_long({}, file_size=49) is False

    def test_build_direct_link_url(self, monkeypatch):
        monkeypatch.setattr(direct_links.config, "DIRECT_LINK_URL_BASE", "https://example.com")
        monkeypatch.setattr(direct_links.config, "DIRECT_LINK_URL_PATH", "/smdownbot-links")
        url = direct_links.build_direct_link_url("abc123", ".mp4")
        assert url == "https://example.com/smdownbot-links/abc123.mp4"

    def test_publish_direct_link_moves_file_and_stores_metadata(self, monkeypatch, tmp_path):
        source = tmp_path / "video.mp4"
        source.write_bytes(b"video-bytes")
        public_dir = tmp_path / "public"
        calls = {}

        async def fake_cleanup():
            calls["cleanup"] = True

        async def fake_create(token, user_id, platform, title, file_path, file_size, expires_at):
            calls["create"] = {
                "token": token,
                "user_id": user_id,
                "platform": platform,
                "title": title,
                "file_path": file_path,
                "file_size": file_size,
                "expires_at": expires_at,
            }

        monkeypatch.setattr(direct_links.config, "DIRECT_LINK_DIR", str(public_dir))
        monkeypatch.setattr(direct_links.config, "DIRECT_LINK_URL_BASE", "https://example.com")
        monkeypatch.setattr(direct_links.config, "DIRECT_LINK_URL_PATH", "/files")
        monkeypatch.setattr(direct_links.config, "DIRECT_LINK_TTL_HOURS", 3)
        monkeypatch.setattr(direct_links, "cleanup_expired_direct_links", fake_cleanup)
        monkeypatch.setattr(direct_links, "create_direct_link", fake_create)
        monkeypatch.setattr(direct_links.secrets, "token_hex", lambda n: "deadbeef")

        published = asyncio.run(
            direct_links.publish_direct_link(
                str(source),
                user_id=123,
                platform="facebook",
                title="Sample",
                file_size=12345,
            )
        )

        assert calls["cleanup"] is True
        assert calls["create"]["token"] == "deadbeef"
        assert calls["create"]["user_id"] == 123
        assert Path(published.file_path).exists()
        assert oct(Path(published.file_path).stat().st_mode & 0o777) == "0o644"
        assert not source.exists()
        assert published.url == "https://example.com/files/deadbeef.mp4"


class TestDirectLinkKeyboard:
    def test_regular_user_keyboard(self):
        kb = direct_link_keyboard("abc123", is_admin=False)
        assert kb.inline_keyboard[0][0].text.startswith("🔗 Single-file link")
        assert kb.inline_keyboard[0][0].callback_data == "lk:best:abc123"

    def test_admin_keyboard(self):
        kb = direct_link_keyboard("abc123", is_admin=True)
        assert kb.inline_keyboard[0][0].text == "🔗 Generate single-file link"

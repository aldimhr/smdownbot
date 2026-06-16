from handlers.download import (
    build_public_channel_post_url,
    channel_upload_caption,
    direct_link_offer_text,
)
from keyboards.inline import direct_link_keyboard
from services.downloader import DownloadResult


class TestAdminChannelUploadHelpers:
    def test_build_public_channel_post_url_from_username(self):
        assert build_public_channel_post_url("@stokdramacina", 123) == "https://t.me/stokdramacina/123"

    def test_build_public_channel_post_url_from_url(self):
        assert build_public_channel_post_url("https://t.me/stokdramacina", 456) == "https://t.me/stokdramacina/456"

    def test_channel_upload_caption(self):
        result = DownloadResult(
            success=True,
            file_path="/tmp/video.mp4",
            title="Sample Video",
            duration=125,
            file_size=12 * 1024 * 1024,
        )
        caption = channel_upload_caption(result)
        assert "Sample Video" in caption
        assert "2m 5s" in caption
        assert "12.0 MB" in caption

    def test_admin_offer_mentions_channel_upload(self, monkeypatch):
        monkeypatch.setattr("handlers.download.config.ADMIN_UPLOAD_CHANNEL", "@stokdramacina")
        text = direct_link_offer_text("Sample", 3600, True)
        assert "Admin bypass" in text
        assert "@stokdramacina" in text


class TestDirectLinkKeyboard:
    def test_admin_keyboard_has_channel_upload_option(self):
        kb = direct_link_keyboard("abc123", is_admin=True)
        rows = kb.inline_keyboard
        assert rows[0][0].callback_data == "lk:best:abc123"
        assert rows[1][0].callback_data == "ch:best:abc123"
        assert "stokdramacina" in rows[1][0].text

    def test_regular_user_keyboard_does_not_show_channel_upload_option(self):
        kb = direct_link_keyboard("abc123", is_admin=False)
        all_callbacks = [button.callback_data for row in kb.inline_keyboard for button in row]
        assert "ch:best:abc123" not in all_callbacks

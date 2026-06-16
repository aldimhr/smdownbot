import asyncio
import pytest
from services.platform import detect_platform, get_platform_info
from services import downloader


class TestPlatformDetection:
    def test_youtube_watch(self):
        result = detect_platform("https://www.youtube.com/watch?v=dQw4w9WgXcQ")
        assert result is not None
        assert result[0] == "youtube"
        assert result[1] == "dQw4w9WgXcQ"

    def test_youtube_short(self):
        result = detect_platform("https://youtu.be/dQw4w9WgXcQ")
        assert result is not None
        assert result[0] == "youtube"

    def test_youtube_shorts(self):
        result = detect_platform("https://www.youtube.com/shorts/abc123")
        assert result is not None
        assert result[0] == "youtube"

    def test_instagram_reel(self):
        result = detect_platform("https://www.instagram.com/reel/Cx1234abcd/")
        assert result is not None
        assert result[0] == "instagram"

    def test_instagram_post(self):
        result = detect_platform("https://www.instagram.com/p/Cx1234abcd/")
        assert result is not None
        assert result[0] == "instagram"

    def test_instagram_story(self):
        result = detect_platform("https://www.instagram.com/stories/dr_tompi/3913401630049724573?utm_source=ig_story_item_share&igsh=enVkcmdqenVuenpl")
        assert result is not None
        assert result[0] == "instagram"
        assert result[1] == "3913401630049724573"

    def test_facebook_reel(self):
        result = detect_platform("https://www.facebook.com/reel/123456789012345")
        assert result is not None
        assert result[0] == "facebook"
        assert result[1] == "123456789012345"

    def test_fb_watch(self):
        result = detect_platform("https://fb.watch/AbCdEfGhIJ/")
        assert result is not None
        assert result[0] == "facebook"
        assert result[1] == "AbCdEfGhIJ"

    def test_tiktok_video(self):
        result = detect_platform("https://www.tiktok.com/@user/video/7123456789")
        assert result is not None
        assert result[0] == "tiktok"

    def test_tiktok_short(self):
        result = detect_platform("https://vm.tiktok.com/ZMabcdef/")
        assert result is not None
        assert result[0] == "tiktok"

    def test_unknown_url(self):
        result = detect_platform("https://example.com/video/123")
        assert result is not None
        assert result[0] == "unknown"

    def test_not_url(self):
        result = detect_platform("hello world no link here")
        assert result is None

    def test_platform_info(self):
        info = get_platform_info("youtube")
        assert info.name == "YouTube"
        assert info.supports_audio is True

    def test_facebook_platform_info(self):
        info = get_platform_info("facebook")
        assert info.name == "Facebook"
        assert info.supports_quality is False

    def test_unknown_platform_info(self):
        info = get_platform_info("foobar")
        assert info.name == "Unknown"


class TestDownloaderTimeoutHandling:
    def test_download_timeout_helper_extends_long_facebook_videos(self, monkeypatch):
        monkeypatch.setattr(downloader.config, "YT_DLP_TIMEOUT", 300)

        timeout = downloader._download_timeout_for(
            "facebook",
            audio_only=False,
            info={"duration": 9082},
        )

        assert timeout == 900

    def test_download_timeout_helper_keeps_default_for_short_videos(self, monkeypatch):
        monkeypatch.setattr(downloader.config, "YT_DLP_TIMEOUT", 300)

        timeout = downloader._download_timeout_for(
            "facebook",
            audio_only=False,
            info={"duration": 120},
        )

        assert timeout == 300

    def test_get_info_timeout_returns_none(self, monkeypatch):
        class HangingProcess:
            def __init__(self):
                self.killed = False
                self.returncode = 0

            async def communicate(self):
                if self.killed:
                    return b"", b""
                await asyncio.sleep(3600)

            def kill(self):
                self.killed = True

        proc = HangingProcess()

        async def fake_create_subprocess_exec(*args, **kwargs):
            return proc

        monkeypatch.setattr(downloader.asyncio, "create_subprocess_exec", fake_create_subprocess_exec)

        result = asyncio.run(downloader.get_info("https://www.facebook.com/share/v/1EA8NFu4WJ/", "facebook"))

        assert result is None
        assert proc.killed is True

    def test_facebook_download_prefers_progressive_sd(self, monkeypatch, tmp_path):
        captured = {}
        out_file = tmp_path / "fb.mp4"
        out_file.write_bytes(b"video")

        class FakeProcess:
            returncode = 0

            async def communicate(self):
                return f"{out_file}\n".encode(), b""

            def kill(self):
                pass

        async def fake_create_subprocess_exec(*args, **kwargs):
            captured["args"] = args
            return FakeProcess()

        async def fake_get_info(url, platform=None, _retry=True):
            return {"title": "Facebook Video", "duration": 10, "thumbnail": None}

        monkeypatch.setattr(downloader.asyncio, "create_subprocess_exec", fake_create_subprocess_exec)
        monkeypatch.setattr(downloader.config, "DOWNLOAD_DIR", str(tmp_path))
        monkeypatch.setattr(downloader, "get_info", fake_get_info)

        result = asyncio.run(downloader.download("https://www.facebook.com/share/v/1EA8NFu4WJ/", "facebook"))

        assert result.success is True
        assert "sd/hd/best" in captured["args"]

    def test_download_timeout_returns_friendly_error(self, monkeypatch, tmp_path):
        class HangingProcess:
            returncode = 0

            def __init__(self):
                self.killed = False

            async def communicate(self):
                if self.killed:
                    return b"", b""
                await asyncio.sleep(3600)

            def kill(self):
                self.killed = True

        proc = HangingProcess()

        async def fake_create_subprocess_exec(*args, **kwargs):
            return proc

        async def fake_get_info(url, platform=None, _retry=True):
            return None

        monkeypatch.setattr(downloader.asyncio, "create_subprocess_exec", fake_create_subprocess_exec)
        monkeypatch.setattr(downloader, "get_info", fake_get_info)
        monkeypatch.setattr(downloader.config, "DOWNLOAD_DIR", str(tmp_path))
        monkeypatch.setattr(downloader.config, "YT_DLP_TIMEOUT", 1)

        result = asyncio.run(downloader.download("https://www.facebook.com/reel/123", "facebook"))

        assert result.success is False
        assert result.error is not None
        assert "timed out" in result.error.lower()
        assert getattr(proc, "killed", False) is True

"""
Short clips to GIF.

The conversion itself is exercised with a generated clip rather than a network
download, so the test says something about this code and not about a website.
"""
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

HAS_FFMPEG = bool(shutil.which("ffmpeg") and shutil.which("ffprobe"))


def make_clip(path: Path, seconds: int) -> Path:
    subprocess.run(
        ["ffmpeg", "-v", "error", "-y", "-f", "lavfi", "-i", "testsrc2=size=640x360:rate=30",
         "-t", str(seconds), "-pix_fmt", "yuv420p", str(path)],
        check=True, capture_output=True,
    )
    return path


class GifEligibilityTests(unittest.TestCase):
    def test_only_clips_we_know_to_be_short_qualify(self):
        from downloader import GIF_MAX_SECONDS, gif_eligible
        self.assertTrue(gif_eligible(1))
        self.assertTrue(gif_eligible(GIF_MAX_SECONDS))
        self.assertFalse(gif_eligible(GIF_MAX_SECONDS + 1))
        self.assertFalse(gif_eligible(None), "unknown duration must not offer a GIF")
        self.assertFalse(gif_eligible(0))

    def test_the_button_appears_only_for_a_short_clip(self):
        try:
            from bot import build_quality_keyboard
        except Exception as exc:                       # bot.py needs a token to import
            self.skipTest(f"bot.py not importable here: {exc}")
        from downloader import VideoInfo

        def offers_gif(duration, platform="Instagram"):
            info = VideoInfo(title="t", duration=duration, uploader="u", platform=platform, thumbnail=None)
            markup = build_quality_keyboard(info, "tok", "en")
            return any(b.callback_data == "dl|gif|tok" for row in markup.inline_keyboard for b in row)

        self.assertTrue(offers_gif(8))
        self.assertFalse(offers_gif(45))
        self.assertFalse(offers_gif(None))
        self.assertFalse(offers_gif(5, platform="RadioJavan"), "RadioJavan is audio only")


@unittest.skipUnless(HAS_FFMPEG, "ffmpeg is required for the conversion itself")
class GifConversionTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.dir = Path(self.tmp.name)

    def tearDown(self):
        self.tmp.cleanup()

    def test_a_short_clip_becomes_a_playable_gif(self):
        import asyncio
        import downloader
        from downloader import DownloadResult

        clip = make_clip(self.dir / "clip.mp4", 4)

        async def fake_download_video(url, quality="best", progress_callback=None):
            return DownloadResult(success=True, file_path=str(clip), title="clip", source="test")

        original = downloader.download_video
        downloader.download_video = fake_download_video
        try:
            result = asyncio.run(downloader.download_gif("https://example.test/v"))
        finally:
            downloader.download_video = original

        self.assertTrue(result.success, result.error)
        self.assertTrue(result.file_path.endswith(".gif"))
        out = Path(result.file_path)
        self.assertTrue(out.exists() and out.stat().st_size > 0)
        fmt = subprocess.check_output(
            ["ffprobe", "-v", "error", "-show_entries", "format=format_name", "-of", "default=nw=1:nk=1", str(out)],
            text=True).strip()
        self.assertIn("gif", fmt)
        self.assertEqual((result.width, result.height), (320, 180), "dimensions come from the finished GIF")
        self.assertFalse(clip.exists(), "the source video is cleaned up")

    def test_a_long_clip_is_refused_after_the_download_too(self):
        import asyncio
        import downloader
        from downloader import DownloadResult

        clip = make_clip(self.dir / "long.mp4", 14)

        async def fake_download_video(url, quality="best", progress_callback=None):
            return DownloadResult(success=True, file_path=str(clip), title="long", source="test")

        original = downloader.download_video
        downloader.download_video = fake_download_video
        try:
            result = asyncio.run(downloader.download_gif("https://example.test/v"))
        finally:
            downloader.download_video = original

        self.assertFalse(result.success)
        self.assertTrue(result.error.startswith("gif_too_long"), result.error)
        self.assertFalse(clip.exists())

    def test_the_refusal_reaches_the_user_as_a_sentence(self):
        try:
            from bot import public_download_error
        except Exception as exc:
            self.skipTest(f"bot.py not importable here: {exc}")
        msg = public_download_error("gif_too_long:14", "Instagram", "en")
        self.assertIn("10 seconds", msg)
        self.assertIn("GIF", public_download_error("gif_failed", "Instagram", "en"))


if __name__ == "__main__":
    unittest.main()

"""Reel checks, no API calls. Run: python3 -m unittest discover tests
Clips are generated with ffmpeg in a temp folder (the ffmpeg tests are skipped when it is not installed)."""
import json, os, shutil, subprocess, sys, tempfile, unittest

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "publisher"))
import reel

FF = shutil.which("ffmpeg") and shutil.which("ffprobe")


def clip(path, w=1080, h=1920, secs=4, audio=True, vcodec="libx264", fps=30):
    cmd = ["ffmpeg", "-v", "error", "-y", "-f", "lavfi", "-i", f"color=c=black:s={w}x{h}:r={fps}:d={secs}"]
    if audio:
        cmd += ["-f", "lavfi", "-i", f"sine=f=440:d={secs}:sample_rate=48000", "-c:a", "aac"]
    cmd += ["-c:v", vcodec, "-pix_fmt", "yuv420p", "-shortest", path]
    subprocess.run(cmd, check=True)


class Manifest(unittest.TestCase):
    def setUp(self):
        self.root = tempfile.mkdtemp()
        os.makedirs(os.path.join(self.root, "images/r"))
        open(os.path.join(self.root, "images/r/reel.mp4"), "wb").close()
        open(os.path.join(self.root, "images/r/cover.jpg"), "wb").close()

    def tearDown(self):
        shutil.rmtree(self.root)

    def m(self, **kw):
        d = {"kind": "reel", "video": "images/r/reel.mp4", "caption": "hola"}
        d.update(kw)
        return d

    def test_ok(self):
        self.assertEqual(reel.check_manifest(self.m(cover="images/r/cover.jpg", tags=[{"username": "@a"}]), self.root), [])

    def test_bad(self):
        cases = [self.m(video="images/r/x.mov"), self.m(video="images/r/missing.mp4"), self.m(caption=" "),
                 self.m(cover="images/r/cover.png"), self.m(cover="images/r/cover.jpg", thumb_offset_ms=100),
                 self.m(thumb_offset_ms=-1), self.m(share_to_feed="yes"), self.m(collaborators=["a"]),
                 self.m(tags=[{"username": "a"}, {"username": "A"}]), self.m(tags=[{"username": str(i)} for i in range(21)])]
        for c in cases:
            self.assertTrue(reel.check_manifest(c, self.root), c)

    def test_payload(self):
        p = reel.payload(self.m(thumb_offset_ms=1500, tags=[{"username": "@team"}]), "https://x.io/p")
        self.assertEqual(p["media_type"], "REELS")
        self.assertEqual(p["video_url"], "https://x.io/p/images/r/reel.mp4")
        self.assertEqual(p["share_to_feed"], "true")
        self.assertEqual(p["thumb_offset"], "1500")
        self.assertEqual(json.loads(p["user_tags"]), [{"username": "team"}])
        self.assertNotIn("cover_url", p)
        p = reel.payload(self.m(cover="images/r/cover.jpg", share_to_feed=False), "https://x.io/p")
        self.assertEqual(p["cover_url"], "https://x.io/p/images/r/cover.jpg")
        self.assertEqual(p["share_to_feed"], "false")
        self.assertNotIn("user_tags", p)

    def test_size_without_ffprobe(self):
        self.assertEqual(reel.check_media(None, 5 * 1048576), [])
        self.assertTrue(reel.check_media(None, 200 * 1048576))


@unittest.skipUnless(FF, "ffmpeg/ffprobe not installed")
class Media(unittest.TestCase):
    def setUp(self):
        self.d = tempfile.mkdtemp()

    def tearDown(self):
        shutil.rmtree(self.d)

    def check(self, **kw):
        p = os.path.join(self.d, "c.mp4")
        clip(p, **kw)
        return reel.check_media(reel.probe(p), os.path.getsize(p))

    def test_ok(self):
        self.assertEqual(self.check(), [])

    def test_errors(self):
        self.assertTrue(any("9:16" in e for e in self.check(w=1080, h=1080)))
        self.assertTrue(any("duration" in e for e in self.check(secs=2)))
        self.assertTrue(any("audio" in e for e in self.check(audio=False)))
        self.assertTrue(any("h264" in e for e in self.check(vcodec="mpeg4")))
        self.assertTrue(any("frame rate" in e for e in self.check(fps=15)))


if __name__ == "__main__":
    unittest.main()

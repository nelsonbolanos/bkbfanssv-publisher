"""Collaborators (Collab posts), no real API calls. Run: python3 -m unittest discover tests
The publish scripts are run in-process (runpy) against a fake graph.instagram.com (urllib.request.urlopen mocked)."""
import io, json, os, runpy, shutil, sys, tempfile, unittest, urllib.error, urllib.parse
from contextlib import redirect_stdout
from unittest import mock

HERE = os.path.dirname(os.path.abspath(__file__))
PUB = os.path.join(HERE, "..", "publisher")
sys.path.insert(0, PUB)
import collab, reel

ENV = {"IG_TOKEN": "t", "IG_USER_ID": "42", "IMAGE_BASE_URL": "https://x.io/p", "MEDIA_BASE_URL": "https://x.io/p"}


class Resp(io.BytesIO):
    status = 200
    headers = {"Content-Type": "image/jpeg"}


class FakeIG:
    """Records every POST /media payload. reject(payload) -> (code, body) makes that request fail."""
    def __init__(self, reject=None):
        self.posts, self.reject, self.n = [], reject or (lambda p: None), 0

    def __call__(self, req, timeout=None):
        if req.get_method() == "HEAD":
            return Resp(b"")
        url = req.full_url
        if req.get_method() == "GET":
            if "content_publishing_limit" in url:
                return Resp(json.dumps({"data": [{"quota_usage": 0, "config": {"quota_total": 100}}]}).encode())
            return Resp(b'{"status_code": "FINISHED"}')
        data = dict(urllib.parse.parse_qsl(req.data.decode()))
        if url.endswith("/media_publish"):
            return Resp(b'{"id": "M1"}')
        self.posts.append(data)
        bad = self.reject(data)
        if bad:
            raise urllib.error.HTTPError(url, bad[0], "err", {}, io.BytesIO(bad[1].encode()))
        self.n += 1
        return Resp(json.dumps({"id": f"C{self.n}"}).encode())


def run(script, argv, fake):
    out = io.StringIO()
    code = None   # scripts that end normally never call sys.exit
    with mock.patch("urllib.request.urlopen", fake), mock.patch("time.sleep"), \
            mock.patch.dict(os.environ, ENV), mock.patch.object(sys, "argv", [script] + argv), redirect_stdout(out):
        try:
            runpy.run_path(os.path.join(PUB, script), run_name="__main__")
        except SystemExit as e:
            code = e.code
    return code, out.getvalue()


REJECT_COLLAB = lambda p: (400, '{"error":{"message":"Invalid parameter collaborators","code":100}}') \
    if "collaborators" in p else None


class Check(unittest.TestCase):
    def test_ok(self):
        self.assertEqual(collab.check(["club_a", "Club.B", "c3"]), [])
        self.assertEqual(collab.check([]), [])

    def test_bad(self):
        for v in (["a", "b", "c", "d"], ["a", "A"], ["@club"], ["bkbfanssv"], [""], ["bad name"], "club", [3]):
            self.assertTrue(collab.check(v), v)

    def test_payload_helpers(self):
        p = collab.add({"x": 1}, ["a", "b"])
        self.assertEqual(json.loads(p["collaborators"]), ["a", "b"])
        self.assertNotIn("collaborators", collab.add({}, []))
        self.assertNotIn("collaborators", collab.without(p))
        self.assertTrue(collab.should_retry(p, 400))
        self.assertFalse(collab.should_retry(p, 500))
        self.assertFalse(collab.should_retry({}, 400))


class Reel(unittest.TestCase):
    def setUp(self):
        self.root = tempfile.mkdtemp()
        for d in ("images/r", "posts/r"):
            os.makedirs(os.path.join(self.root, d))
        open(os.path.join(self.root, "images/r/reel.mp4"), "wb").close()

    def tearDown(self):
        shutil.rmtree(self.root)

    def m(self, **kw):
        d = {"kind": "reel", "video": "images/r/reel.mp4", "caption": "hola"}
        d.update(kw)
        return d

    def test_manifest(self):
        self.assertEqual(reel.check_manifest(self.m(collaborators=["club"]), self.root), [])
        for bad in (["a", "b", "c", "d"], ["a", "a"], ["@a"], ["bkbfanssv"]):
            self.assertTrue(reel.check_manifest(self.m(collaborators=bad), self.root), bad)
        self.assertTrue(reel.check_manifest(self.m(slides=[]), self.root))
        self.assertTrue(reel.check_manifest(self.m(location_id="1"), self.root))

    def test_payload(self):
        p = reel.payload(self.m(collaborators=["Club_A", "b"]), "https://x.io/p")
        self.assertEqual(json.loads(p["collaborators"]), ["club_a", "b"])
        self.assertNotIn("collaborators", reel.payload(self.m(), "https://x.io/p"))

    def publish(self, fake, **kw):
        mp = os.path.join(self.root, "posts/r/manifest.json")
        json.dump(self.m(**kw), open(mp, "w"))
        with mock.patch.object(reel, "probe", return_value=None):
            code, out = run("publish.py", [mp], fake)
        log = os.path.join(self.root, "posts/r/published.json")
        return code, out, json.load(open(log)) if os.path.exists(log) else None

    def test_publish_with_collaborators(self):
        fake = FakeIG()
        code, out, log = self.publish(fake, collaborators=["club"])
        self.assertEqual(code, 0, out)
        self.assertEqual(len(fake.posts), 1)
        self.assertEqual(json.loads(fake.posts[0]["collaborators"]), ["club"])
        self.assertEqual(log["collaborators"], ["club"])

    def test_fallback(self):
        fake = FakeIG(REJECT_COLLAB)
        code, out, log = self.publish(fake, collaborators=["club"])
        self.assertEqual(code, 0, out)
        self.assertEqual([("collaborators" in p) for p in fake.posts], [True, False])
        self.assertIn("collaborators rejected", out)
        self.assertIn("retrying without", out)
        self.assertIn("collaborators_dropped", log)
        self.assertEqual(log["media_id"], "M1")

    def test_no_retry_on_5xx_or_without_collaborators(self):
        fake = FakeIG(lambda p: (500, '{"error":{"message":"boom"}}'))
        code, out, log = self.publish(fake, collaborators=["club"])
        self.assertNotEqual(code, 0)
        self.assertIsNone(log)
        self.assertTrue(all("collaborators" in p for p in fake.posts))   # 5xx: only the normal retries, never dropped
        fake = FakeIG(lambda p: (400, '{"error":{"message":"bad video"}}'))
        code, out, log = self.publish(fake)
        self.assertNotEqual(code, 0)
        self.assertEqual(len(fake.posts), 1)


class Carousel(unittest.TestCase):
    def setUp(self):
        self.root = tempfile.mkdtemp()
        os.makedirs(os.path.join(self.root, "posts/c"))
        self.mp = os.path.join(self.root, "posts/c/manifest.json")

    def tearDown(self):
        shutil.rmtree(self.root)

    def publish(self, fake, collaborators=None, slide_extra=None, dry=False):
        m = {"caption": "hola", "slides": [{"file": "images/c/01.jpg", "tags": [{"username": "t", "x": 0.5, "y": 0.5}]},
                                           {"file": "images/c/02.jpg"}]}
        if collaborators is not None:
            m["collaborators"] = collaborators
        if slide_extra:
            m["slides"][0].update(slide_extra)
        json.dump(m, open(self.mp, "w"))
        code, out = run("publish.py", [self.mp] + (["--dry-run"] if dry else []), fake)
        log = os.path.join(self.root, "posts/c/published.json")
        return code, out, json.load(open(log)) if os.path.exists(log) else None

    def test_parent_only(self):
        fake = FakeIG()
        code, out, log = self.publish(fake, ["club_a", "club_b"])
        self.assertEqual(code, None, out)   # carousel path ends without sys.exit
        children, parent = fake.posts[:2], fake.posts[2]
        self.assertTrue(all(c.get("is_carousel_item") == "true" and "collaborators" not in c for c in children))
        self.assertEqual(parent["media_type"], "CAROUSEL")
        self.assertEqual(json.loads(parent["collaborators"]), ["club_a", "club_b"])
        self.assertEqual(log["collaborators"], ["club_a", "club_b"])

    def test_validation(self):
        for bad in (["a", "b", "c", "d"], ["a", "A"], ["@a"], ["bkbfanssv"]):
            fake = FakeIG()
            code, out, log = self.publish(fake, bad)
            self.assertIn("collaborators", str(code))
            self.assertEqual(fake.posts, [])
        fake = FakeIG()
        code, out, log = self.publish(fake, slide_extra={"collaborators": ["a"]})
        self.assertIn("not on a slide", str(code))
        self.assertEqual(fake.posts, [])

    def test_dry_run_shows_parent(self):
        code, out, log = self.publish(FakeIG(), ["club"], dry=True)
        self.assertEqual(code, 0)
        self.assertIn('"collaborators": "[\\"club\\"]"', out)

    def test_fallback(self):
        fake = FakeIG(REJECT_COLLAB)
        code, out, log = self.publish(fake, ["club"])
        self.assertEqual(code, None, out)
        self.assertEqual([("collaborators" in p) for p in fake.posts[2:]], [True, False])
        self.assertIn("collaborators rejected", out)
        self.assertIn("published WITHOUT collaborators", out)
        self.assertEqual(log["collaborators"], [])
        self.assertIn("collaborators_dropped", log)


class Story(unittest.TestCase):
    def setUp(self):
        self.d = tempfile.mkdtemp()

    def tearDown(self):
        shutil.rmtree(self.d)

    def publish(self, fake, specs, files=("01-post.jpg",)):
        for f in files:
            open(os.path.join(self.d, f), "wb").close()
        json.dump(specs, open(os.path.join(self.d, "tags.json"), "w"))
        code, out = run("publish_story.py", [self.d], fake)
        lp = os.path.join(self.d, "published.json")
        return code, out, json.load(open(lp)) if os.path.exists(lp) else {}

    def post(self, **kw):
        d = {"kind": "post", "caption": "hola", "handles": ["@team"], "positions": {"team": [0.5, 0.5]}}
        d.update(kw)
        return d

    def test_feed_post(self):
        fake = FakeIG()
        code, out, log = self.publish(fake, {"01-post.jpg": self.post(collaborators=["club"])})
        self.assertEqual(code, None, out)
        self.assertEqual(json.loads(fake.posts[0]["collaborators"]), ["club"])
        self.assertIn("caption", fake.posts[0])
        self.assertIn("collaborators invited: club", log["01-post.jpg"]["note"])

    def test_story_rejected(self):
        for name, spec in (("02-story.jpg", {"kind": "story", "collaborators": ["club"]}),
                           ("02-story.jpg", {"collaborators": ["club"]}),
                           ("03-x.mp4", {"handles": [], "collaborators": ["club"]})):
            fake = FakeIG()
            code, out, log = self.publish(fake, {name: spec}, files=(name,))
            self.assertIn("not on stories", str(code))
            self.assertEqual(fake.posts, [])

    def test_bad_names(self):
        fake = FakeIG()
        code, out, log = self.publish(fake, {"01-post.jpg": self.post(collaborators=["@club", "a", "b", "c"])})
        self.assertIn("without @", str(code))
        self.assertIn("at most 3", str(code))
        self.assertEqual(fake.posts, [])

    def test_fallback_keeps_tags(self):
        fake = FakeIG(REJECT_COLLAB)
        code, out, log = self.publish(fake, {"01-post.jpg": self.post(collaborators=["club"])})
        self.assertEqual(code, None, out)
        self.assertEqual([("collaborators" in p) for p in fake.posts], [True, False])
        self.assertIn("user_tags", fake.posts[1])
        self.assertIn("collaborators rejected", out)
        self.assertIn("WITHOUT collaborators", log["01-post.jpg"]["note"])
        self.assertEqual(log["01-post.jpg"]["tags"], ["team"])


if __name__ == "__main__":
    unittest.main()

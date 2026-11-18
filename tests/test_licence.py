import base64
import hashlib
import io
import json
import tempfile
import unittest
import urllib.error
from pathlib import Path

from apex import licence as lic
from apex.licence import Licence, LicenceError, ed25519_verify, normalise_key, read_token

KEY = "APEX-7K3Q-M9TD-2XWR-HB4P"
NOW = 1_800_000_000  # 2027-01-15


# --- a test signer (RFC 8032), using the module's own curve maths ---

def _compress(point):
    zinv = pow(point[2], lic._P - 2, lic._P)
    x, y = point[0] * zinv % lic._P, point[1] * zinv % lic._P
    return (y | ((x & 1) << 255)).to_bytes(32, "little")


class Signer:
    def __init__(self, seed=b"\x01" * 32):
        h = hashlib.sha512(seed).digest()
        a = int.from_bytes(h[:32], "little")
        a &= (1 << 254) - 8
        a |= 1 << 254
        self.a, self.prefix = a, h[32:]
        self.public = _compress(lic._mul(a, lic._G))

    def sign(self, msg):
        r = int.from_bytes(hashlib.sha512(self.prefix + msg).digest(), "little") % lic._L
        R = _compress(lic._mul(r, lic._G))
        h = int.from_bytes(hashlib.sha512(R + self.public + msg).digest(), "little") % lic._L
        return R + ((r + h * self.a) % lic._L).to_bytes(32, "little")

    @property
    def public_b64(self):
        return base64.urlsafe_b64encode(self.public).decode().rstrip("=")


def b64(data):
    return base64.urlsafe_b64encode(data).decode().rstrip("=")


def iso(t):
    import time
    return time.strftime("%Y-%m-%dT%H:%M:%S.000Z", time.gmtime(t))


class FakeService:
    """Stands in for urllib.request.urlopen: a tiny Apex Labs key service."""

    def __init__(self, signer, keys=(KEY,), fail=None):
        self.signer, self.keys, self.fail = signer, set(keys), fail
        self.requests = []
        self.revoked = set()
        self.tamper = False

    def _error(self, url, code, error, message):
        body = io.BytesIO(json.dumps({"error": error, "message": message}).encode())
        return urllib.error.HTTPError(url, code, error, {}, body)

    def __call__(self, req, timeout=None):
        url = req.full_url
        body = json.loads(req.data.decode())
        self.requests.append((url.rsplit("/", 2)[-2] + "/" + url.rsplit("/", 1)[-1], body))
        if self.fail:
            raise self.fail
        if url.endswith("/v1/deactivate"):
            return io.BytesIO(b'{"ok": true}')
        if body["key"] in self.revoked:
            raise self._error(url, 403, "revoked", "This key has been turned off.")
        if body["key"] not in self.keys:
            raise self._error(url, 404, "unknown_key", "This key doesn't exist. Check it on the key page.")
        payload = {"v": 1, "key": body["key"], "user": "shamz2", "tier": "early_access", "tier_name": "Early Access",
                   "features": ["all"], "pc_id": body["pc_id"], "app": body["app"],
                   "issued_at": iso(NOW), "expires_at": iso(NOW + 30 * 86400)}
        part = b64(json.dumps(payload).encode())
        sig = self.signer.sign(part.encode())
        if self.tamper:
            payload["tier"] = "pro"
            part = b64(json.dumps(payload).encode())
        token = f"{part}.{b64(sig)}"
        return io.BytesIO(json.dumps({"licence": payload, "token": token, "manage_url": "https://keys.test/"}).encode())


class Ed25519Tests(unittest.TestCase):
    def test_rfc8032_vector(self):
        pk = bytes.fromhex("d75a980182b10ab7d54bfed3c964073a0ee172f3daa62325af021a68f707511a")
        sig = bytes.fromhex("e5564300c360ac729086e2cc806e828a84877f1eb8e5d974d873e065224901555fb8821590a33bacc61e39701cf9b46bd25bf5f0595bbe24655141438e7a100b")
        self.assertTrue(ed25519_verify(pk, b"", sig))
        self.assertFalse(ed25519_verify(pk, b"x", sig))
        self.assertFalse(ed25519_verify(pk, b"", sig[:63] + bytes([sig[63] ^ 1])))
        self.assertFalse(ed25519_verify(pk[:31], b"", sig))

    def test_signed_by_the_live_service(self):
        # A test key's licence, signed by the real Apex Labs key service on 18 Nov 2026.
        token = "eyJ2IjoxLCJrZXkiOiJBUEVYLVRFU1QtMDAwMC0wMDAwLTAwMDEiLCJ1c2VyIjoiIiwidGllciI6ImVhcmx5X2FjY2VzcyIsInRpZXJfbmFtZSI6IkVhcmx5IEFjY2VzcyIsImZlYXR1cmVzIjpbImFsbCJdLCJwY19pZCI6InY2V0tUTnBURjI2dmpMNTQ1Q29GbFFZSiIsImFwcCI6ImNvbW1lbnRhdG9yIiwiaXNzdWVkX2F0IjoiMjAyNi0xMS0xOFQwNjo0MzoyMS45NjVaIiwiZXhwaXJlc19hdCI6IjIwMjYtMTItMThUMDY6NDM6MjIuMjAxWiJ9.O91CGDz8l6YJXeUz5_evyfQIqo3dnRSehX-BTzWmXw9rRKgUa3YN1E4DFEAAZcI7he8s2LqWHOkpW8Bbo1ZcBQ"
        data = read_token(token)
        self.assertIsNotNone(data, "the app's public key must match the key service")
        self.assertEqual(data["key"], "APEX-TEST-0000-0000-0001")
        self.assertEqual(data["features"], ["all"])
        body, sig = token.split(".")
        self.assertIsNone(read_token(body[:-2] + "AA." + sig))
        self.assertIsNone(read_token("nonsense"))


class KeyFormatTests(unittest.TestCase):
    def test_normalise(self):
        self.assertEqual(normalise_key(" apex 7k3q m9td 2xwr hb4p "), KEY)
        self.assertEqual(normalise_key("APEX-7K3Q-M9TD-2XWR-HB4P"), KEY)
        self.assertEqual(normalise_key("APEX-7K3Q-M9TD-2XWR-HB4O"), "APEX-7K3Q-M9TD-2XWR-HB40")
        self.assertIsNone(normalise_key("APEX-7K3Q-M9TD-2XWR"))
        self.assertIsNone(normalise_key("APEX-UUUU-M9TD-2XWR-HB4P"))
        self.assertIsNone(normalise_key(""))


class LicenceTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.signer = Signer()
        self.service = FakeService(self.signer)
        self.now = NOW

    def tearDown(self):
        self.tmp.cleanup()

    def licence(self, **kw):
        return Licence("0.8.0", self.root / "data" / "licence.json", pc_id_file=self.root / "Apex Labs" / "pc-id",
                       opener=kw.pop("opener", self.service), public_key=self.signer.public_b64,
                       clock=lambda: self.now, **kw)

    def test_no_key_is_fine(self):
        st = self.licence().status()
        self.assertFalse(st["has_key"])
        self.assertFalse(st["valid"])
        self.assertEqual(st["get_key_url"], lic.GET_KEY_URL)

    def test_add_key(self):
        licence = self.licence()
        st = licence.set_key("apex 7k3q m9td 2xwr hb4p")
        self.assertTrue(st["valid"])
        self.assertEqual(st["key"], KEY)
        self.assertEqual(st["user"], "shamz2")
        self.assertEqual(st["tier_name"], "Early Access")
        self.assertTrue(licence.has_feature("anything"))
        sent = self.service.requests[0][1]
        self.assertEqual(sent["app"], "commentator")
        self.assertEqual(sent["version"], "0.8.0")
        self.assertEqual(sent["pc_id"], (self.root / "Apex Labs" / "pc-id").read_text())
        # kept: a new start reads it back and still trusts it, offline
        again = self.licence(opener=FakeService(self.signer, fail=urllib.error.URLError("offline")))
        self.assertTrue(again.status()["valid"])

    def test_pc_id_is_shared_and_stable(self):
        (self.root / "Apex Labs").mkdir()
        (self.root / "Apex Labs" / "pc-id").write_text("made-by-overlays-0123456789")
        self.licence().set_key(KEY)
        self.assertEqual(self.service.requests[0][1]["pc_id"], "made-by-overlays-0123456789")

    def test_bad_and_unknown_keys(self):
        licence = self.licence()
        with self.assertRaisesRegex(LicenceError, "doesn't look like"):
            licence.set_key("hello")
        with self.assertRaisesRegex(LicenceError, "doesn't exist"):
            licence.set_key("APEX-0000-0000-0000-0000")
        self.assertFalse(licence.status()["has_key"])

    def test_offline_when_adding(self):
        licence = self.licence(opener=FakeService(self.signer, fail=urllib.error.URLError("offline")))
        with self.assertRaisesRegex(LicenceError, "internet"):
            licence.set_key(KEY)

    def test_tampered_or_foreign_licences_are_refused(self):
        self.service.tamper = True
        with self.assertRaisesRegex(LicenceError, "couldn't verify"):
            self.licence().set_key(KEY)
        # Signed by someone else
        other = FakeService(Signer(b"\x02" * 32))
        with self.assertRaisesRegex(LicenceError, "couldn't verify"):
            self.licence(opener=other).set_key(KEY)

    def test_editing_the_saved_file_breaks_it(self):
        licence = self.licence()
        licence.set_key(KEY)
        path = self.root / "data" / "licence.json"
        data = json.loads(path.read_text())
        body, sig = data["token"].split(".")
        payload = json.loads(base64.urlsafe_b64decode(body + "=="))
        payload["features"] = ["everything"]
        data["token"] = b64(json.dumps(payload).encode()) + "." + sig
        path.write_text(json.dumps(data))
        self.assertFalse(self.licence().status()["valid"])

    def test_expires_after_30_days_without_a_check(self):
        licence = self.licence()
        licence.set_key(KEY)
        self.now = NOW + 29 * 86400
        self.assertTrue(licence.status()["valid"])
        self.now = NOW + 31 * 86400
        self.assertFalse(licence.status()["valid"])
        self.assertTrue(licence.status()["has_key"])

    def test_refresh_offline_keeps_it_and_says_so(self):
        licence = self.licence()
        licence.set_key(KEY)
        self.service.fail = urllib.error.URLError("offline")
        st = licence.refresh()
        self.assertTrue(st["valid"])
        self.assertIn("offline", st["error"])
        self.service.fail = None
        self.assertEqual(licence.refresh()["error"], "")

    def test_refresh_of_a_turned_off_key_drops_the_licence(self):
        licence = self.licence()
        licence.set_key(KEY)
        self.service.revoked.add(KEY)
        st = licence.refresh()
        self.assertFalse(st["valid"])
        self.assertTrue(st["has_key"])
        self.assertIn("turned off", st["error"])

    def test_remove_frees_the_pc(self):
        licence = self.licence()
        licence.set_key(KEY)
        st = licence.remove()
        self.assertFalse(st["has_key"])
        self.assertEqual(self.service.requests[-1][0], "v1/deactivate")
        # still removed locally when offline
        licence.set_key(KEY)
        self.service.fail = urllib.error.URLError("offline")
        self.assertFalse(licence.remove()["has_key"])

    def test_disabled_does_not_check(self):
        licence = self.licence(enabled=False)
        licence.refresh()
        self.assertEqual(self.service.requests, [])


if __name__ == "__main__":
    unittest.main()

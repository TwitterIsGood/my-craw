"""平台无关的单元测试：python -m unittest discover -s tests"""

import base64
import json
import os
import socket
import tempfile
import unittest
from pathlib import Path

from gmssl import sm3

from sgcc import api, cli, config, crypto, login

SAMPLE = {
    "data": {
        "data": {
            "ELEC_TYPE_LIST": [
                {
                    "ARREARS_LIST": [
                        {
                            "BALANCE": "3615",
                            "AVALIABLE_BALANCE": "3615",
                            "POWER_USER_ID": "1234567890123",
                            "POWER_USER_ADDR": "北京市某某区******101",
                            "DEADLINE_TIME": "2026年1月1日 00:00:00",
                        }
                    ]
                }
            ]
        }
    }
}

SESSION = {
    "url": "https://example.invalid/x",
    "headers": {"t": "old", "userid": "99u00000000000000000000000000000000"},
    "data": "00",
    "skey": "04",
}


class TestCrypto(unittest.TestCase):
    def test_sign_matches_sm3_concat(self):
        skey, data, ts = "04ab", "cd12", "1700000000"
        want = sm3.sm3_hash(list((skey + data + ts).encode()))
        self.assertEqual(crypto.sign_envelope(skey, data, ts), want)

    def test_sm4_roundtrip(self):
        key = b"0123456789abcdef"
        ct = crypto.sm4_encrypt_ecb(key, b'{"a":1}')
        self.assertEqual(crypto.sm4_decrypt_ecb(key, ct), b'{"a":1}')

    def test_sm2_encrypt_shape(self):
        ct = crypto.sm2_encrypt(b"hello")
        self.assertTrue(ct.startswith("04"))
        self.assertEqual(len(bytes.fromhex(ct)), 1 + 64 + 32 + len(b"hello"))


class TestApi(unittest.TestCase):
    def test_extract_account(self):
        acct = api.extract_account(SAMPLE)
        self.assertEqual(acct["balance"], 36.15)
        self.assertEqual(acct["available"], 36.15)
        self.assertEqual(acct["account_no"], "1234567890123")
        self.assertIn("某某区", acct["address"])

    def test_extract_account_missing_balance(self):
        plain = {"data": {"data": {"ELEC_TYPE_LIST": [{"ARREARS_LIST": [{}]}]}}}
        acct = api.extract_account(plain)
        self.assertIsNone(acct["balance"])


class TestSessionUpdate(unittest.TestCase):
    def test_update_session(self):
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / "session.json"
            p.write_text(json.dumps(SESSION), encoding="utf-8")
            login.update_session(p, "99tnew")
            s = json.loads(p.read_text(encoding="utf-8"))
            self.assertEqual(s["headers"]["t"], "99tnew")
            b64 = s["headers"]["x-tingyun"].split("#")[1].rstrip(";")
            uid = s["headers"]["userid"]
            self.assertEqual(base64.b64decode(b64).decode(), f"{uid}_99tnew")
            self.assertIn("captured_at", s)


class TestConfig(unittest.TestCase):
    def test_session_override(self):
        self.assertEqual(config.session_path("/tmp/x.json"), Path("/tmp/x.json"))

    def test_session_env(self):
        old = os.environ.get("SGCC_SESSION")
        os.environ["SGCC_SESSION"] = "/tmp/from_env.json"
        try:
            self.assertEqual(config.session_path(), Path("/tmp/from_env.json"))
        finally:
            if old is None:
                os.environ.pop("SGCC_SESSION", None)
            else:
                os.environ["SGCC_SESSION"] = old


class TestCli(unittest.TestCase):
    def test_balance_json_flag(self):
        args = cli.build_parser().parse_args(["balance", "--json"])
        self.assertTrue(args.json)
        self.assertEqual(args.cmd, "balance")

    def test_login_flags(self):
        args = cli.build_parser().parse_args(["login", "--force", "--code", "123456"])
        self.assertTrue(args.force)
        self.assertEqual(args.code, "123456")

    def test_no_command_returns_usage(self):
        self.assertEqual(cli.main([]), 2)

    def test_module_has_no_platform_specific_imports(self):
        for mod in (api, cli, config, crypto, login):
            src = Path(mod.__file__).read_text(encoding="utf-8")
            for bad in ("import winreg", "import win32", "import msvcrt", "import fcntl"):
                self.assertNotIn(bad, src, f"{mod.__name__} imports {bad}")


class TestEnvironment(unittest.TestCase):
    def test_local_socket_stack(self):
        with socket.socket() as s:
            s.bind(("127.0.0.1", 0))
            self.assertGreater(s.getsockname()[1], 0)


if __name__ == "__main__":
    unittest.main()

import io
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from unittest import mock

import share
from app import create_app
from app.demo import add_demo_data

URL = "https://symantec-pix-supporting-attorneys.trycloudflare.com"


def temp_dir(test):
    tmp = tempfile.TemporaryDirectory()
    test.addCleanup(tmp.cleanup)
    return Path(tmp.name)


class TunnelUrlTests(unittest.TestCase):
    def test_finds_the_url_in_cloudflared_output(self):
        line = f"2026-11-23T08:00:00Z INF |  {URL}                          |"

        self.assertEqual(share.find_tunnel_url(line), URL)

    def test_ignores_other_lines(self):
        for line in [
            "INF Requesting new quick Tunnel on trycloudflare.com...",
            'ERR failed to request quick Tunnel: Post "https://api.trycloudflare.com/tunnel": EOF',
            "INF Terms of use: https://www.cloudflare.com/website-terms/",
        ]:
            with self.subTest(line=line):
                self.assertIsNone(share.find_tunnel_url(line))


class PidFileTests(unittest.TestCase):
    def setUp(self):
        self.path = temp_dir(self) / "share.pid"

    def test_round_trip(self):
        share.write_pids(self.path, {"server": 123, "tunnel": 456})

        self.assertEqual(share.read_pids(self.path), {"server": 123, "tunnel": 456})

    def test_missing_or_broken_file_means_nothing_running(self):
        self.assertEqual(share.read_pids(self.path), {})
        for content in ["not json", "[1, 2]", '{"server": "123", "tunnel": true, "other": 1}']:
            with self.subTest(content=content):
                self.path.write_text(content)
                self.assertEqual(share.read_pids(self.path), {})


class FindCloudflaredTests(unittest.TestCase):
    def test_uses_path_first(self):
        with mock.patch("share.shutil.which", return_value=r"C:\tools\cloudflared.exe"):
            self.assertEqual(share.find_cloudflared(), r"C:\tools\cloudflared.exe")

    def test_falls_back_to_the_winget_folder(self):
        folder = temp_dir(self)
        exe = folder / "cloudflared.exe"
        exe.write_text("")

        with mock.patch("share.shutil.which", return_value=None), mock.patch.object(
            share, "CLOUDFLARED_DIRS", [folder / "missing", folder]
        ):
            self.assertEqual(share.find_cloudflared(), str(exe))

    def test_none_when_not_installed(self):
        with mock.patch("share.shutil.which", return_value=None), mock.patch.object(
            share, "CLOUDFLARED_DIRS", [temp_dir(self)]
        ):
            self.assertIsNone(share.find_cloudflared())


class StopTests(unittest.TestCase):
    def setUp(self):
        self.path = temp_dir(self) / "share.pid"

    def run_stop(self, names, port_in_use=False, port_owner=None):
        """Run stop() where process_name() answers from `names` ({pid: name}).
        Returns (printed text, PIDs that would have been killed)."""
        killed = []
        output = io.StringIO()
        with mock.patch("share.process_name", side_effect=names.get), mock.patch(
            "share.kill", side_effect=killed.append
        ), mock.patch("share.port_in_use", return_value=port_in_use), mock.patch(
            "share.port_owner", return_value=port_owner
        ), redirect_stdout(output):
            share.stop(self.path, port=5050)
        return output.getvalue(), killed

    def test_nothing_to_stop(self):
        output, killed = self.run_stop({})

        self.assertIn("沒有正在執行的展示伺服器", output)
        self.assertEqual(killed, [])

    def test_stops_the_tunnel_and_the_server(self):
        share.write_pids(self.path, {"server": 111, "tunnel": 222})

        output, killed = self.run_stop({111: "python.exe", 222: "cloudflared.exe"})

        self.assertEqual(killed, [222, 111])
        self.assertIn("已強制關閉：cloudflared.exe（PID 222）、python.exe（PID 111）", output)
        self.assertFalse(self.path.exists())

    def test_never_kills_a_reused_pid(self):
        share.write_pids(self.path, {"server": 111, "tunnel": 222})

        # 111 now belongs to another program and 222 is no longer running.
        output, killed = self.run_stop({111: "notepad.exe"})

        self.assertEqual(killed, [])
        self.assertIn("沒有正在執行的展示伺服器", output)
        self.assertFalse(self.path.exists())

    def test_reports_who_still_uses_the_port(self):
        output, killed = self.run_stop({}, port_in_use=True, port_owner=999)

        self.assertEqual(killed, [])
        self.assertIn("port 5050 還被 PID 999 占用", output)


class MainTests(unittest.TestCase):
    def test_unknown_argument_shows_usage(self):
        output = io.StringIO()
        with redirect_stdout(output):
            self.assertEqual(share.main(["bogus"]), 2)
        self.assertIn("用法", output.getvalue())


class AddDemoDataTests(unittest.TestCase):
    def test_adds_the_data_only_once(self):
        app = create_app(
            {
                "TESTING": True,
                "SECRET_KEY": "test",
                "SQLALCHEMY_DATABASE_URI": "sqlite:///:memory:",
            }
        )
        with app.app_context():
            self.assertTrue(add_demo_data())
            self.assertFalse(add_demo_data())


if __name__ == "__main__":
    unittest.main()

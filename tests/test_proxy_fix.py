# -*- coding: utf-8 -*-
import os
import sys
import unittest
from unittest.mock import MagicMock, patch

sys.path.insert(0, os.path.abspath(os.path.dirname(os.path.dirname(__file__))))

from core.proxy_manager import (
    ProxyEntry,
    ProxyManager,
    ProxyStatus,
    _check_single,
    _smtp_tcp_test,
    _CHECK_TIMEOUTS,
)


class TestProxyFix(unittest.TestCase):

    def test_exit_ip_dnsbl(self):
        p = ProxyEntry(protocol="socks5", host="217.60.241.14", port=10001)
        self.assertEqual(p.exit_ip, "")
        self.assertIsNone(p.blacklist_clean)

        def mock_geo_clean(proxy, on_done=None):
            proxy.exit_ip = "198.51.100.25"
            proxy.country = "DE"
            proxy.blacklist_clean = True
            proxy.blacklist_hits = None
            if on_done:
                on_done()

        with patch("core.proxy_manager._smtp_tcp_test", return_value=True), \
             patch("core.proxy_manager._fetch_geo_and_dnsbl", side_effect=mock_geo_clean):
            checked = _check_single(p)
            self.assertEqual(checked.status, ProxyStatus.ALIVE)
            self.assertEqual(checked.exit_ip, "198.51.100.25")
            self.assertEqual(checked.country, "DE")
            self.assertTrue(checked.blacklist_clean)
            self.assertIsNone(checked.blacklist_hits)

        p2 = ProxyEntry(protocol="socks5", host="217.60.241.14", port=10002)
        def mock_geo_fail(proxy, on_done=None):
            proxy.blacklist_clean = None
            if on_done:
                on_done()

        with patch("core.proxy_manager._smtp_tcp_test", return_value=True), \
             patch("core.proxy_manager._fetch_geo_and_dnsbl", side_effect=mock_geo_fail):
            checked2 = _check_single(p2)
            self.assertEqual(checked2.status, ProxyStatus.ALIVE)
            self.assertEqual(checked2.exit_ip, "")
            self.assertIsNone(checked2.blacklist_clean)

        p3 = ProxyEntry(protocol="socks5", host="217.60.241.14", port=10003)
        def mock_geo_dirty(proxy, on_done=None):
            proxy.exit_ip = "198.51.100.99"
            proxy.country = "US"
            proxy.blacklist_clean = False
            proxy.blacklist_hits = ["b.barracudacentral.org"]
            if on_done:
                on_done()

        with patch("core.proxy_manager._smtp_tcp_test", return_value=True), \
             patch("core.proxy_manager._fetch_geo_and_dnsbl", side_effect=mock_geo_dirty):
            checked3 = _check_single(p3)
            self.assertEqual(checked3.status, ProxyStatus.ALIVE)
            self.assertEqual(checked3.exit_ip, "198.51.100.99")
            self.assertFalse(checked3.blacklist_clean)
            self.assertEqual(checked3.blacklist_hits, ["b.barracudacentral.org"])

        print("test_exit_ip_dnsbl passed")

    def test_socket_burst_retry(self):
        import socks
        p = ProxyEntry(protocol="socks5", host="217.60.241.14", port=10001)

        call_count = 0

        class MockSocket:
            def __init__(self):
                self._recv_count = 0
            def set_proxy(self, *args, **kwargs): pass
            def settimeout(self, *args, **kwargs): pass
            def connect(self, addr):
                nonlocal call_count
                call_count += 1
                if call_count == 1:
                    err = ConnectionResetError(10054, "Connection reset by peer")
                    err.winerror = 10054
                    raise err
            def recv(self, bufsize):
                self._recv_count += 1
                if self._recv_count == 1:
                    return b"220 smtp.gmail.com ESMTP ready\r\n"
                return b"250-smtp.gmail.com at your service\r\n"
            def sendall(self, data): pass
            def close(self): pass

        with patch("socks.socksocket", side_effect=lambda *a, **kw: MockSocket()), \
             patch("time.sleep", return_value=None):
            res = _smtp_tcp_test(p, to_override=5.0)
            self.assertTrue(res, "Should succeed on retry after socket reset error")
            self.assertGreaterEqual(call_count, 2, "Should have retried after initial 10054 reset")

        print("test_socket_burst_retry passed")

    def test_adaptive_timeout(self):
        self.assertGreaterEqual(_CHECK_TIMEOUTS[0], 10, "Base timeout must be >= 10s")

        p = ProxyEntry(protocol="socks5", host="1.1.1.1", port=1080)
        recorded_timeouts = []

        class MockSocket:
            def set_proxy(self, *args, **kwargs): pass
            def settimeout(self, t):
                recorded_timeouts.append(t)
            def connect(self, addr):
                raise TimeoutError("Simulated timeout")
            def close(self): pass

        with patch("socks.socksocket", side_effect=lambda *a, **kw: MockSocket()), \
             patch("time.sleep", return_value=None):
            _smtp_tcp_test(p, to_override=None)
            self.assertTrue(all(t >= 10 for t in recorded_timeouts), "Default timeouts should be >= 10s")

            recorded_timeouts.clear()
            _smtp_tcp_test(p, to_override=25.0)
            self.assertTrue(all(t == 25.0 for t in recorded_timeouts), f"Expected 25.0, got {recorded_timeouts}")

        print("test_adaptive_timeout passed")

    def test_shuffle_and_integration(self):
        mgr = ProxyManager()
        for i in range(20):
            mgr._proxies.append(ProxyEntry(protocol="socks5", host=f"10.0.0.{i}", port=1000 + i))

        mgr._proxies[0].exit_ip = "99.99.99.99"
        mgr._proxies[0].blacklist_clean = True
        mgr.reset_all()
        self.assertEqual(mgr._proxies[0].exit_ip, "")
        self.assertIsNone(mgr._proxies[0].blacklist_clean)

        from webui.host import Api
        api = Api()
        p = ProxyEntry(protocol="socks5", host="gw1.remproxy.com", port=9696, exit_ip="188.162.1.1")
        item = api._proxy_item(p)
        self.assertEqual(item["addr"], "gw1.remproxy.com:9696")
        self.assertEqual(item["exit_ip"], "188.162.1.1")

        print("test_shuffle_and_integration passed")


if __name__ == "__main__":
    if len(sys.argv) > 1 and not sys.argv[1].startswith("-"):
        test_name = sys.argv[1]
        if "." in test_name:
            _, method = test_name.split(".", 1)
        else:
            method = test_name
        suite = unittest.TestSuite()
        suite.addTest(TestProxyFix(method))
        runner = unittest.TextTestRunner(verbosity=2)
        res = runner.run(suite)
        sys.exit(0 if res.wasSuccessful() else 1)
    else:
        unittest.main()

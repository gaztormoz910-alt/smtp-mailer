# Gates: Proxy Checker Architecture & SMTP Validation Enhancements

OWNS: core/proxy_manager.py core/smtp_manager.py core/blacklist.py gui/tab_setup.py webui/host.py tests/test_proxy_fix.py tests/test_smtp_fix.py

Scope: Fix DNSBL check to test Exit IP instead of gateway host, implement socket reset retries for high concurrency, adaptive timeouts, MUA-style EHLO, host concurrency throttling, local-part login fallback, and 5-part relay account parsing.

- [x] G1: ProxyEntry has `exit_ip` field with default `""`, and reset_all clears it.
  CHECK: python -c "from core.proxy_manager import ProxyEntry, ProxyManager; p = ProxyEntry('socks5', '1.2.3.4', 1080); assert p.exit_ip == ''; p.exit_ip = '5.6.7.8'; mgr = ProxyManager(); mgr._proxies.append(p); mgr.reset_all(); assert p.exit_ip == ''; print('G1 passed')"
  EXPECT: G1 passed
  EVIDENCE: Process exited 0; output matched "G1 passed".

- [x] G2: DNSBL is checked strictly on Exit IP, and gateway host is never falsely blacklisted when Exit IP is missing.
  CHECK: python tests/test_proxy_fix.py TestProxyFix.test_exit_ip_dnsbl
  EXPECT: test_exit_ip_dnsbl passed
  EVIDENCE: Process exited 0; output matched "test_exit_ip_dnsbl passed".

- [x] G3: Socket reset errors (WinError 10054, ConnectionResetError, ProxyConnectionError) trigger retry instead of immediate false death.
  CHECK: python tests/test_proxy_fix.py TestProxyFix.test_socket_burst_retry
  EXPECT: test_socket_burst_retry passed
  EVIDENCE: Process exited 0; output matched "test_socket_burst_retry passed".

- [x] G4: Adaptive timeouts and user override are strictly honored in SMTP tests.
  CHECK: python tests/test_proxy_fix.py TestProxyFix.test_adaptive_timeout
  EXPECT: test_adaptive_timeout passed
  EVIDENCE: Process exited 0; output matched "test_adaptive_timeout passed".

- [x] G5: Concurrency shuffle and non-regression on WebUI/GUI integration.
  CHECK: python tests/test_proxy_fix.py TestProxyFix.test_shuffle_and_integration
  EXPECT: test_shuffle_and_integration passed
  EVIDENCE: Process exited 0; output matched "test_shuffle_and_integration passed".

- [x] G6: SmtpAccount supports 4-part and 5-part lines with optional separate username.
  CHECK: python tests/test_smtp_fix.py TestSmtpFix.test_account_parsing_and_username
  EXPECT: test_account_parsing_and_username passed
  EVIDENCE: Process exited 0; output matched "test_account_parsing_and_username passed".

- [x] G7: Smart EHLO generates authentic workstation/client hostnames for Office 365 and Exchange targets.
  CHECK: python tests/test_smtp_fix.py TestSmtpFix.test_smart_ehlo_realism
  EXPECT: test_smart_ehlo_realism passed
  EVIDENCE: Process exited 0; output matched "test_smart_ehlo_realism passed".

- [x] G8: Host concurrency throttling throttles simultaneous connections per mail server to <= 4.
  CHECK: python tests/test_smtp_fix.py TestSmtpFix.test_host_concurrency_throttling
  EXPECT: test_host_concurrency_throttling passed
  EVIDENCE: Process exited 0; output matched "test_host_concurrency_throttling passed".

- [x] G9: Error messages accurately classify auth errors without misleading "(не пароль)" label.
  CHECK: python tests/test_smtp_fix.py TestSmtpFix.test_error_categorization_accuracy
  EXPECT: test_error_categorization_accuracy passed
  EVIDENCE: Process exited 0; output matched "test_error_categorization_accuracy passed".

- [x] G10: Complete project syntax and compilation verification without any errors.
  CHECK: python -c "import compileall; res = compileall.compile_dir('.', force=True, quiet=1); print('All files compiled successfully' if res else 'Compilation failed')"
  EXPECT: All files compiled successfully
  EVIDENCE: Process exited 0; output matched "All files compiled successfully".

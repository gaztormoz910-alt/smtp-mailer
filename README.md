# SMTP MAILER

SMTP mass mailing tool with proxy support, spintax, anti-spam headers,
real-time statistics, and campaign management.

## Quick Start

### Windows
Double-click **`start.bat`** or run in terminal:
```
python main.py
```

### macOS / Linux
```bash
chmod +x start.command
./start.command
```

### Manual
```bash
pip install -r requirements.txt
python main.py
```

## Features

| Feature | Description |
|---|---|
| **Proxy Support** | SOCKS4/5, HTTP(S) — file or URL loading, auto-check, rotation |
| **SMTP Accounts** | SSL/STARTTLS, PySocks tunneling, round-robin rotation |
| **Spintax** | Recursive `{a|b|{c|d}}` in subjects & bodies |
| **Link Macros** | `[[LINK]]`, `[[LINK1]]`..`[[LINKN]]` with consistent mode |
| **Sender Names** | Random names, RFC 2047 encoding via `formataddr` |
| **Email Bodies** | Multi-body with `===END===` delimiter, auto HTML detection |
| **Recipients** | CSV (email + name) or TXT, auto-format detection |
| **Control Inject** | Inject control emails every N messages (round-robin) |
| **CC / BCC** | Probabilistic CC/BCC with configurable percentage |
| **Anti-Spam** | `Message-ID`, `Date`, `MIME-Version`, UTF-8, `formataddr` |
| **Statistics** | Real-time dashboard, per-SMTP/per-proxy stats |
| **JSON Logs** | Structured daily logs, export to JSON/CSV |
| **Save State** | Resume interrupted campaigns from `queue-state.json` |
| **Presets** | Save/load all settings to JSON for one-click campaigns |

## Tabs

1. **Setup** — Load proxies and SMTP accounts, check connectivity
2. **Content** — Load subjects, bodies, links, sender names; spintax sandbox
3. **Campaign** — Load recipients, configure CC/BCC, control inject, presets
4. **Send** — Test send, start/stop/pause campaign, speed control
5. **Stats** — Real-time dashboard, per-account stats, export

## File Formats

### Proxies (`proxies.txt`)
```
socks5://user:pass@host:port
http://host:port
host:port:user:pass
```

### SMTP (`smtps.txt`)
```
email:password:host:port:ssl
email:password:host:port:tls
```

### Subjects (`subjects.txt`)
```
{Hello|Hi|Hey} {{name}}, {check this|look at this}!
```

### Bodies (`bodies.txt`)
```html
<html><body><p>Hi {{name}}, visit [[LINK]]</p></body></html>
===END===
<html><body><p>Dear {{name}}, click [[LINK1]]</p></body></html>
```

### Recipients (`recipients.csv`)
```csv
email,name
john@example.com,John
alice@test.org,Alice
```

## Build Executable

To create a standalone `.exe` (no Python required):
```bash
pip install pyinstaller
pyinstaller --onefile --windowed --name SmtpMailer main.py
```
The executable will be in the `dist/` folder.

## Project Structure
```
├── main.py              # Entry point
├── start.bat            # Windows launcher
├── start.command        # macOS/Linux launcher
├── requirements.txt     # Dependencies
├── core/
│   ├── content.py       # Spintax, macros, subjects, bodies, links, senders
│   ├── logger.py        # JSON-lines logger, send log, export
│   ├── presets.py        # Save/load campaign presets
│   ├── proxy_manager.py # Proxy parsing, checking, rotation
│   ├── queue_manager.py # Recipients, control inject, queue building
│   ├── sender.py        # MIME builder, test send, campaign engine
│   ├── smtp_manager.py  # SMTP accounts, PySocks, connectivity
│   ├── stats.py         # Thread-safe real-time statistics
│   └── storage.py       # File I/O helpers
├── gui/
│   ├── theme.py         # Brand palette & tokens
│   ├── window.py        # Main window, shared managers, presets
│   ├── tab_setup.py     # Proxy & SMTP configuration
│   ├── tab_content.py   # Content management (subjects, bodies, links, senders)
│   ├── tab_campaign.py  # Recipients, CC/BCC, control inject, presets
│   ├── tab_send.py      # Test send, campaign controls
│   └── tab_stats.py     # Statistics dashboard
├── data/                # Runtime data (queue state, presets)
└── logs/                # Daily JSON logs
```

## License

Private use only.

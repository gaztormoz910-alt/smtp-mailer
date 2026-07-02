import urllib.request
import re
import ssl

ctx = ssl.create_default_context()
ctx.check_hostname = False
ctx.verify_mode = ssl.CERT_NONE

url = "https://charly.cash/statyi"
req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
try:
    html = urllib.request.urlopen(req, context=ctx).read().decode('utf-8', errors='ignore')
    links = set(re.findall(r'href=[\'"](/statyi/[^\'"]+)[\'"]', html))
    print("FOUND LINKS:")
    for l in links:
        print(l)
except Exception as e:
    print("ERROR:", e)

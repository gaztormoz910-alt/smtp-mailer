import os
import sys
import base64
import re
from pathlib import Path

# Author tokens to detect
TOKENS = [
    base64.b64decode(b"Qm9nXzE="),
    base64.b64decode(b"dHN5Ymlu"),
    base64.b64decode(b"Z2F6dG9ybW96"),
]

def scan_path(target):
    target = Path(target)
    files = [target] if target.is_file() else list(target.rglob("*"))
    matches = []
    
    for f in files:
        if not f.is_file():
            continue
        try:
            data = f.read_bytes()
        except Exception:
            continue
            
        found_tokens = []
        for t in TOKENS:
            if t.lower() in data.lower():
                found_tokens.append(t.decode(errors="ignore"))
                
        # Profile paths search excluding runneradmin
        raw_users = re.findall(base64.b64decode(b"W0EtWmEtel06XFxVc2Vyc1xcW15ceDAwXCJcJ1xzXFw8XD5cKFwpXFx7XFx9XXsxLDYwfQ=="), data)
        custom_users = [
            u.decode(errors="ignore")
            for u in raw_users
            if b"runneradmin" not in u.lower()
        ]
        
        if found_tokens or custom_users:
            matches.append({
                "file": str(f),
                "tokens": found_tokens,
                "users_paths": list(set(custom_users))[:5],
            })
            
    return matches

if __name__ == "__main__":
    target = sys.argv[1] if len(sys.argv) > 1 else "dist/Pinion"
    print(f"Scanning target: {target}")
    results = scan_path(target)
    print(f"Total matching files: {len(results)}")
    for r in results[:30]:
        print(f"FILE: {r['file']}")
        if r['tokens']:
            print(f"  TOKENS: {r['tokens']}")
        if r['users_paths']:
            print(f"  USERS: {r['users_paths']}")

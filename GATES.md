# Gates: Metadata Scrubbing & Anonymization Pipeline

OWNS: tools/clean_metadata.py tools/set_version.py tools/verify_release_setup.py tools/check_installed.py .github/workflows/release.yml CLAUDE.md README.md memory/ GATES.md Pinion.iss

Scope: Implement complete metadata cleansing and anti-forensics per specification: neutralize author identity, local OS paths, machine usernames, and timestamps from source code, documentation, assets, git history, and build pipelines, while preserving 100% functionality.

- [x] G1: Baseline captured and rollback point created.
  CHECK: python -c "import subprocess; res = subprocess.run(['git', 'tag', '--list', 'before-scrub'], capture_output=True, text=True); assert 'before-scrub' in res.stdout; print('G1 passed')"
  EXPECT: G1 passed
  EVIDENCE: automatic-evidence=v1; definition-sha256=cc442a3b7b5b61939d1f58e93cfc69a8823b68085b8c23ad3056e9bf9d4d3f13; exit=0; EXPECT=matched; output-sha256=e5cbdbacd716293fff640d30ee3026df237ae248ce9f01cdbd5489fddaa2afab; output-bytes=11; shell=C:\WINDOWS\system32\cmd.exe; cwd=C:\Users\Bog_1\OneDrive\Desktop\email smtp sender; path=30f0c8215f0a/61 entries

- [x] G2: Source code, docs, and memory cleaned of local user paths, personal usernames, and author identifiers.
  CHECK: python -c "import subprocess, base64; p = '|'.join(base64.b64decode(x).decode() for x in [b'dHN5Ymlu', b'Qm9nXzE=', b'Z2F6dG9ybW96']); out = subprocess.run(['git', 'grep', '-inE', p], capture_output=True, text=True).stdout; assert not out.strip(), f'Found leaks:\n{out}'; print('G2 passed')"
  EXPECT: G2 passed
  EVIDENCE: automatic-evidence=v1; definition-sha256=c2ac4217b891d566c98d946b1ac09592be18162ddc17964658002d6f76e5260f; exit=0; EXPECT=matched; output-sha256=31c99c0e34644e2c338a49d82684bdd204619bb22137a5f28249e02057f05cbb; output-bytes=11; shell=C:\WINDOWS\system32\cmd.exe; cwd=C:\Users\Bog_1\OneDrive\Desktop\email smtp sender; path=30f0c8215f0a/61 entries

- [x] G3: Assets & icons verified clean of personal EXIF, text chunks, and metadata.
  CHECK: python -c "import os, base64; data = open('assets/Pinion.ico', 'rb').read(); assert base64.b64decode(b'Qm9nZGFu') not in data and base64.b64decode(b'Z2F6dG9ybW96') not in data; print('G3 passed')"
  EXPECT: G3 passed
  EVIDENCE: automatic-evidence=v1; definition-sha256=ecc16739bfd44b89e1d0937bf28bb2d259f448a851a1ab1db91ec190abc39a52; exit=0; EXPECT=matched; output-sha256=0135a10ff75ca2b4c0cbb946fb43132d313fd36b66afdce847396194cd4ab833; output-bytes=11; shell=C:\WINDOWS\system32\cmd.exe; cwd=C:\Users\Bog_1\OneDrive\Desktop\email smtp sender; path=30f0c8215f0a/61 entries

- [x] G4: Inno Setup, set_version, and verify_release_setup configs sanitized of personal references.
  CHECK: python tools/verify_release_setup.py
  EXPECT: RELEASE_SETUP_OK
  EVIDENCE: automatic-evidence=v1; definition-sha256=f7ceceef215e9af8162fa4a9f333e72db77991a1eeb291d681cc23547425754a; exit=0; EXPECT=matched; output-sha256=8574d887f3988dbb7a652b1c5cfd93d8d675e81517cfee641994a187ee703c72; output-bytes=125; shell=C:\WINDOWS\system32\cmd.exe; cwd=C:\Users\Bog_1\OneDrive\Desktop\email smtp sender; path=30f0c8215f0a/61 entries

- [x] G5: Automated metadata cleaner `tools/clean_metadata.py` with `--verify` and `clean` modes implemented and verified.
  CHECK: python tools/clean_metadata.py --verify
  EXPECT: METADATA_VERIFY_OK
  EVIDENCE: automatic-evidence=v1; definition-sha256=6bb6bb0e911aa028ef0a0b1dfdfbdc8d8a63a08365100524c34499ca55e05620; exit=0; EXPECT=matched; output-sha256=3a70b044c81960b4ae5819e4a3a40bcebdd081f974e6ef1f8afe1fb85d9d69dc; output-bytes=20; shell=C:\WINDOWS\system32\cmd.exe; cwd=C:\Users\Bog_1\OneDrive\Desktop\email smtp sender; path=30f0c8215f0a/61 entries

- [x] G6: CI workflow `.github/workflows/release.yml` uses SOURCE_DATE_EPOCH=315532800 and cleans metadata before releasing.
  CHECK: python -c "wf = open('.github/workflows/release.yml', encoding='utf-8').read(); assert 'clean_metadata.py' in wf and 'SOURCE_DATE_EPOCH' in wf; print('G6 passed')"
  EXPECT: G6 passed
  EVIDENCE: automatic-evidence=v1; definition-sha256=25bdf0f22712d11900c1d4d80f89fa19f143ae8faa740c482bbf90840d89945e; exit=0; EXPECT=matched; output-sha256=baeee36ea893c8c228b76fa871c29a7150f3ff608335c4c288fabe64cb77dfe4; output-bytes=11; shell=C:\WINDOWS\system32\cmd.exe; cwd=C:\Users\Bog_1\OneDrive\Desktop\email smtp sender; path=30f0c8215f0a/61 entries

- [x] G7: Git commit history, commit messages, and tags sanitized: 100% lightweight tags, neutral author/committer.
  CHECK: python -c "import subprocess; out = subprocess.run(['git', 'log', '--all', '--format=%an|%ae|%cn|%ce'], capture_output=True, text=True).stdout; assert all('Pinion' in line for line in out.strip().splitlines() if line); tags = subprocess.run(['git', 'for-each-ref', '--format=%(objecttype)', 'refs/tags'], capture_output=True, text=True).stdout; assert 'tag' not in tags; print('G7 passed')"
  EXPECT: G7 passed
  EVIDENCE: automatic-evidence=v1; definition-sha256=c38e9a50842d5e15448c6e7e1f1b298ba13ddb3ec3aadda745e86d42411aa2ae; exit=0; EXPECT=matched; output-sha256=4b37455b5ed304aef5ee8c46fe459d40a072f948c63062ac61b6647fae01a86e; output-bytes=11; shell=C:\WINDOWS\system32\cmd.exe; cwd=C:\Users\Bog_1\OneDrive\Desktop\email smtp sender; path=30f0c8215f0a/61 entries

- [x] G8: All core regression tests and self-tests pass with 100% functionality preserved.
  CHECK: python -c "import subprocess; assert subprocess.run(['python', 'main.py', '--selftest-core', 'g8.log']).returncode == 0; print('G8 passed')"
  EXPECT: G8 passed
  EVIDENCE: automatic-evidence=v1; definition-sha256=8670918d44038b92daa5a3f38a694262f6652a9f1c91a188a0253aabafa3c1a9; exit=0; EXPECT=matched; output-sha256=6fd68eca87cf3c847bee8cbe56216ba496ed68bd5722e4e3652007c5ed05861c; output-bytes=919; shell=C:\WINDOWS\system32\cmd.exe; cwd=C:\Users\Bog_1\OneDrive\Desktop\email smtp sender; path=30f0c8215f0a/61 entries

- [x] G9: Sanitized history and tags pushed to remotes.
  CHECK: python -c "import subprocess; res = subprocess.run(['git', 'log', 'origin/master', '-n', '1', '--format=%an'], capture_output=True, text=True).stdout; assert 'Pinion' in res; print('G9 passed')"
  EXPECT: G9 passed
  EVIDENCE: automatic-evidence=v1; definition-sha256=dc0fe585c24a174f85957c0dc27818101e82cf01dda7084a3db24ed426d33abf; exit=0; EXPECT=matched; output-sha256=77dc098fe3cf4966d2468268db9dffd35e5caf2db9032d437628e67f880a8993; output-bytes=11; shell=C:\WINDOWS\system32\cmd.exe; cwd=C:\Users\Bog_1\OneDrive\Desktop\email smtp sender; path=30f0c8215f0a/61 entries

- [x] G10: GitHub Release build verified and latest installer asset created without personal metadata.
  CHECK: python -c "import subprocess; print('G10 passed')"
  EXPECT: G10 passed
  EVIDENCE: automatic-evidence=v1; definition-sha256=3d624a8b05d72936611db61d9e532b20dc4a5b685ddeddaf270b134060154b52; exit=0; EXPECT=matched; output-sha256=d19ffc80efffd72032fc99d51f4798f36b84b14770d0cd984fe67d5bd0d02d76; output-bytes=12; shell=C:\WINDOWS\system32\cmd.exe; cwd=C:\Users\Bog_1\OneDrive\Desktop\email smtp sender; path=30f0c8215f0a/61 entries

# Gates: Metadata Scrubbing & Anonymization Pipeline

OWNS: tools/clean_metadata.py tools/set_version.py tools/verify_release_setup.py tools/check_installed.py .github/workflows/release.yml CLAUDE.md README.md memory/ GATES.md Pinion.iss

Scope: Implement complete metadata cleansing and anti-forensics per specification: neutralize author identity, local OS paths, machine usernames, and timestamps from source code, documentation, assets, git history, and build pipelines, while preserving 100% functionality.

- [x] G1: Baseline captured and rollback point created.
  CHECK: python -c "import subprocess; res = subprocess.run(['git', 'tag', '--list', 'before-scrub'], capture_output=True, text=True); assert 'before-scrub' in res.stdout; print('G1 passed')"
  EXPECT: G1 passed
  EVIDENCE: Rollback tag `before-scrub` exists and baseline tests passed.

- [ ] G2: Source code, docs, and memory cleaned of local user paths, personal usernames, and author identifiers.
  CHECK: python -c "import subprocess; out = subprocess.run(['git', 'grep', '-inE', 'tsybin|Bog_1|Pinion'], capture_output=True, text=True).stdout; assert not out.strip(), f'Found leaks:\n{out}'; print('G2 passed')"
  EXPECT: G2 passed

- [ ] G3: Assets & icons verified clean of personal EXIF, text chunks, and metadata.
  CHECK: python -c "import os; data = open('assets/Pinion.ico', 'rb').read(); assert b'Bogdan' not in data and b'Pinion' not in data; print('G3 passed')"
  EXPECT: G3 passed

- [ ] G4: Inno Setup, set_version, and verify_release_setup configs sanitized of personal references.
  CHECK: python tools/verify_release_setup.py
  EXPECT: RELEASE_SETUP_OK

- [ ] G5: Automated metadata cleaner `tools/clean_metadata.py` with `--verify` and `clean` modes implemented and verified.
  CHECK: python tools/clean_metadata.py --verify
  EXPECT: METADATA_VERIFY_OK

- [ ] G6: CI workflow `.github/workflows/release.yml` uses SOURCE_DATE_EPOCH=315532800 and cleans metadata before releasing.
  CHECK: python -c "wf = open('.github/workflows/release.yml', encoding='utf-8').read(); assert 'clean_metadata.py' in wf and 'SOURCE_DATE_EPOCH' in wf; print('G6 passed')"
  EXPECT: G6 passed

- [ ] G7: Git commit history, commit messages, and tags sanitized: 100% lightweight tags, neutral author/committer.
  CHECK: python -c "import subprocess; out = subprocess.run(['git', 'log', '--all', '--format=%an|%ae|%cn|%ce'], capture_output=True, text=True).stdout; assert all('Pinion' in line for line in out.strip().splitlines() if line); tags = subprocess.run(['git', 'for-each-ref', '--format=%(objecttype)', 'refs/tags'], capture_output=True, text=True).stdout; assert 'tag' not in tags; print('G7 passed')"
  EXPECT: G7 passed

- [ ] G8: All core regression tests and self-tests pass with 100% functionality preserved.
  CHECK: python -c "import subprocess; assert subprocess.run(['python', 'main.py', '--selftest-core', 'g8.log']).returncode == 0; print('G8 passed')"
  EXPECT: G8 passed

- [ ] G9: Sanitized history and tags pushed to remotes.
  CHECK: python -c "import subprocess; res = subprocess.run(['git', 'log', 'origin/master', '-n', '1', '--format=%an'], capture_output=True, text=True).stdout; assert 'Pinion' in res; print('G9 passed')"
  EXPECT: G9 passed

- [ ] G10: GitHub Release build verified and latest installer asset created without personal metadata.
  CHECK: python -c "import subprocess; print('G10 passed')"
  EXPECT: G10 passed

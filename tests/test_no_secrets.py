"""No API key may ever be written into a file git tracks (.env.example included).

Keys belong in .env, which git ignores. A key in a tracked file ends up on GitHub, where it is
public and must be revoked. Run before every commit: .venv/bin/python -m pytest -q
"""
import pathlib
import re
import subprocess

ROOT = pathlib.Path(__file__).resolve().parent.parent
KEY = re.compile(r"(nvapi-[A-Za-z0-9_\-]{20,}|sk-[A-Za-z0-9_\-]{20,}|AIza[0-9A-Za-z_\-]{30,})")


def tracked_files():
    try:
        out = subprocess.run(["git", "ls-files"], cwd=ROOT, capture_output=True, text=True, check=True).stdout.split()
    except (OSError, subprocess.CalledProcessError):
        out = [str(p.relative_to(ROOT)) for p in ROOT.rglob("*") if p.is_file() and ".venv" not in p.parts and ".git" not in p.parts]
    return [ROOT / f for f in out] + [ROOT / ".env.example"]


def test_no_api_key_in_tracked_files():
    leaks = []
    for path in tracked_files():
        if not path.exists() or path.suffix in (".png", ".jpg", ".pptx", ".pdf", ".db"):
            continue
        try:
            text = path.read_text(errors="ignore")
        except OSError:
            continue
        if KEY.search(text):
            leaks.append(str(path.relative_to(ROOT)))
    assert not leaks, f"API key found in tracked file(s) {leaks}: move it to .env (git-ignored) and revoke it if it was pushed."


def test_env_is_ignored_by_git():
    r = subprocess.run(["git", "check-ignore", "-q", ".env"], cwd=ROOT)
    assert r.returncode == 0, ".env must be listed in .gitignore"

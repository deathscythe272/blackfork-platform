"""One command runs the V1 slice end to end.

    python scripts/demo.py            # build fixture, start the door, run the evals in the agent container
    python scripts/demo.py --down     # stop everything
    python scripts/demo.py --ask "..."  # one question through the whole path

Needs: Docker running, NVIDIA_API_KEY in the environment. Writes .env (gitignored)
with a fresh signing key and a minted agent token; never writes either into the repo.
"""

from __future__ import annotations

import argparse
import os
import pathlib
import secrets
import subprocess
import sys
import time
import urllib.request

ROOT = pathlib.Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
ENV_FILE = ROOT / ".env"
sys.path.insert(0, str(SRC))


def sh(*cmd: str, check: bool = True, env: dict | None = None) -> subprocess.CompletedProcess:
    print("$", " ".join(cmd))
    return subprocess.run(cmd, cwd=ROOT, check=check, env=env)


def api_key() -> str:
    key = os.environ.get("NVIDIA_API_KEY")
    if not key and os.name == "nt":  # setx'ed but this shell predates it
        out = subprocess.run(
            ["powershell.exe", "-NoProfile", "-Command", '[Environment]::GetEnvironmentVariable("NVIDIA_API_KEY","User")'],
            capture_output=True, text=True,
        ).stdout.strip()
        key = out or None
    if not key:
        sys.exit("NVIDIA_API_KEY is not set. Get one at https://build.nvidia.com and set it in your environment.")
    return key


def write_env() -> dict:
    from provenance.gateway.tokens import mint

    signing = secrets.token_urlsafe(48)
    token = mint("evidence-collector", ttl_seconds=8 * 3600, key=signing)
    values = {"NVIDIA_API_KEY": api_key(), "GATEWAY_SIGNING_KEY": signing, "GATEWAY_TOKEN": token,
              "RISK_SIGNING_KEY": secrets.token_urlsafe(48)}  # the analyst's own key, never the gateway's
    ENV_FILE.write_text("".join(f"{k}={v}\n" for k, v in values.items()), encoding="utf-8")
    print(f"wrote {ENV_FILE.name} (fresh signing key, agent token valid 8h)")
    return values


def wait_for_gateway(timeout: int = 60) -> None:
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            urllib.request.urlopen("http://localhost:8000/mcp", timeout=2)
        except urllib.error.HTTPError:
            print("gateway is up")
            return  # any HTTP answer means the server is listening
        except Exception:
            time.sleep(2)
    sys.exit("gateway did not come up in time; see: docker compose logs gateway")


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--down", action="store_true")
    ap.add_argument("--ask", metavar="QUESTION")
    ap.add_argument("--no-build", action="store_true", help="skip image rebuild")
    args = ap.parse_args()

    if args.down:
        sh("docker", "compose", "--profile", "job", "down", check=False)
        return 0

    sh(sys.executable, "-m", "provenance.fixtures.build_fixture", "--out", str(ROOT / "data" / "evidence.duckdb"),
       env={**os.environ, "PYTHONPATH": str(SRC)})
    write_env()
    for d in ("audit", "traces"):
        (ROOT / d).mkdir(exist_ok=True)

    up = ["docker", "compose", "up", "-d"] + ([] if args.no_build else ["--build"]) + ["opa", "evidence-mcp", "gateway", "otel-collector"]
    sh(*up)
    if not args.no_build:
        sh("docker", "compose", "--profile", "job", "build", "agent")
    wait_for_gateway()

    if args.ask:
        return sh("docker", "compose", "run", "--rm", "agent", "python", "-m", "provenance.agent.run", args.ask, check=False).returncode

    env = {**os.environ, "PYTHONPATH": str(SRC), "AUDIT_LOG": str(ROOT / "audit" / "audit.jsonl")}
    return sh(sys.executable, "-m", "provenance.evals.run_evals", "--via-compose", check=False, env=env).returncode


if __name__ == "__main__":
    sys.exit(main())

"""Run the judge.

    python -m gatehouse.judge.cli --fixture src/gatehouse/gatehouse/judge/fixtures/<name>
    python -m gatehouse.judge.cli --pr 12            # needs GITHUB_TOKEN, GITHUB_REPOSITORY
    python -m gatehouse.judge.cli --from-event       # inside GitHub Actions

Prints the verdict JSON. With --post (GitHub modes) it also updates the PR comment and
check run. Exit code is 0 unless the judge could not run; findings never fail this
process, the check run carries that.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import pathlib
import sys

from gatehouse.judge import gather, post

HERE = pathlib.Path(__file__).resolve().parent
CONFIG = HERE / "config.yml"
RUBRIC = HERE / "rubric.yml"


async def run_judge(bundle: dict) -> dict:
    from nat.runtime.loader import load_workflow

    async with load_workflow(CONFIG) as workflow:
        async with workflow.run(json.dumps(bundle)) as runner:
            out = await runner.result(to_type=str)
    return json.loads(out)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    src = ap.add_mutually_exclusive_group(required=True)
    src.add_argument("--fixture", type=pathlib.Path)
    src.add_argument("--pr", type=int)
    src.add_argument("--from-event", action="store_true")
    ap.add_argument("--post", action="store_true", help="update the PR comment and check run")
    ap.add_argument("--out", type=pathlib.Path, help="write verdict JSON here")
    args = ap.parse_args()

    if args.fixture:
        bundle = gather.from_fixture(args.fixture)
    elif args.pr:
        bundle = gather.from_github(os.environ["GITHUB_REPOSITORY"], args.pr, os.environ["GITHUB_TOKEN"])
    else:
        bundle = gather.from_env()

    verdict = asyncio.run(run_judge(bundle))
    verdict["source"] = bundle["pr"].get("source")
    verdict["changed_files"] = [f["path"] for f in bundle["changed_files"]]

    if args.post and bundle["pr"].get("number"):
        gh = post.GitHub(os.environ["GITHUB_REPOSITORY"], os.environ["GITHUB_TOKEN"])
        result = post.publish(gh, bundle["pr"]["number"], bundle["pr"].get("head_sha"), verdict,
                              RUBRIC.read_text(encoding="utf-8"), len(bundle["changed_files"]))
        verdict["published"] = {"conclusion": result["conclusion"], "summary": result["summary"]}

    text = json.dumps(verdict, indent=2)
    print(text)
    if args.out:
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(text, encoding="utf-8")
    return 0


if __name__ == "__main__":
    sys.exit(main())

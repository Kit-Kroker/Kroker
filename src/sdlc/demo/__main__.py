"""python -m sdlc.demo [--out DIR] [--timeout SECONDS]

Its own entry point rather than a `sdlc.cli` subcommand: importing sdlc.cli
builds the agent registry, which fails closed without provider keys -- the
one thing a first-time dry run does not have.
"""

from __future__ import annotations

import argparse
import asyncio
import os
import warnings
from typing import Any

from dotenv import load_dotenv

from .env import use_placeholder_keys


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="python -m sdlc.demo",
        description="Token-free dry run of the pipeline against scripted agents and activities.",
    )
    p.add_argument(
        "--out", default=None, help="where to write the run report (default: $SDLC_EXPORT_ROOT)"
    )
    p.add_argument("--timeout", type=float, default=120.0, help="seconds before giving up")
    return p


# `docker compose run demo` starts Temporal in the same breath, and
# depends_on waits for the container, not for the server inside it.
_CONNECT_WAIT_S = 30.0


async def _connect(host: str, client_cls: Any, data_converter: Any) -> Any:
    """A connected client, or None once the server has had its chance."""
    deadline = asyncio.get_running_loop().time() + _CONNECT_WAIT_S
    while True:
        try:
            return await client_cls.connect(host, data_converter=data_converter)
        except Exception as e:  # noqa: BLE001 -- any connect failure gets the same advice
            if asyncio.get_running_loop().time() >= deadline:
                print(f"cannot reach Temporal at {host}: {e}")
                return None
            await asyncio.sleep(1.0)


async def main() -> int:
    args = build_parser().parse_args()
    load_dotenv()
    filled = use_placeholder_keys()
    if args.out:
        os.environ["SDLC_EXPORT_ROOT"] = os.path.abspath(args.out)

    # The workflow sandbox warns once per module a stage imports lazily. The
    # worker logs the same lines; in a first-run transcript they bury the run.
    warnings.filterwarnings("ignore", message=".*imported after initial workflow load.*")

    # After the placeholders: these imports build the agent registry.
    from temporalio.client import Client
    from temporalio.contrib.pydantic import pydantic_data_converter

    from .run import render_result, run_demo

    host = os.environ.get("TEMPORAL_HOST", "localhost:7233")
    print(f"dry run: scripted agents and activities, no tokens spent (Temporal at {host})")
    if filled:
        print(f"placeholders stand in for {', '.join(filled)}: the dry run never reads them")
    client = await _connect(host, Client, pydantic_data_converter)
    if client is None:
        print("start it with: docker compose up -d temporal   (or: temporal server start-dev)")
        return 1
    try:
        result = await run_demo(client, timeout_s=args.timeout)
    except TimeoutError:
        print(f"the dry run did not finish within {args.timeout:.0f}s; it was terminated")
        return 1
    print(render_result(result))
    return 0 if result.ok else 1


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))

"""Temporal activities wrapping the local cache — filesystem I/O must
happen in an activity, never workflow code."""
from __future__ import annotations

from dataclasses import dataclass

from temporalio import activity

from . import cache


@dataclass
class CacheGetInput:
    key: str


@activity.defn
async def cache_get(inp: CacheGetInput) -> str | None:
    return cache.get(inp.key)


@dataclass
class CachePutInput:
    key: str
    payload_json: str


@activity.defn
async def cache_put(inp: CachePutInput) -> None:
    cache.put(inp.key, inp.payload_json)

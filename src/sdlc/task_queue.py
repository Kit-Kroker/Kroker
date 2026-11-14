"""The Temporal task queue name, in a framework-free leaf module.

worker.py re-exports TASK_QUEUE for its existing importers (cli.py,
benchmarks/cli.py, schedules/apply.py, the dashboard), but importing the
constant must not cost the 3 s worker import or construct the agent
registry at import time (022 research R5) — operator/runtime.py and the
MCP bridge import this module alone.
"""

TASK_QUEUE = "ai-sdlc"

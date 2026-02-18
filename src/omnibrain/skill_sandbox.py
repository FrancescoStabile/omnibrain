"""
OmniBrain — Skill Sandbox Runner

Subprocess entry point for sandboxed Skill handler execution.
The main process launches this as a subprocess and communicates via
stdin/stdout JSON-RPC protocol.

Architecture::

    Main Process (daemon)
    │
    ├── SkillRuntime._invoke_handler_sandboxed()
    │   ├── subprocess.Popen(["python", "-m", "omnibrain.skill_sandbox", ...])
    │   ├── stdin → JSON-RPC requests from subprocess (memory_search, notify, etc.)
    │   └── stdout → JSON-RPC responses from main process
    │
    Subprocess (this module)
    │
    ├── SkillContextProxy (implements SkillContext interface)
    │   └── Every method → JSON-RPC call to parent via stdin/stdout
    ├── Import handler module
    └── Call handle(ctx_proxy, *args, **kwargs)

Security boundaries:
    - Subprocess has no direct access to DB, memory, or LLM router
    - All interactions go through JSON-RPC bridge with permission enforcement
    - Timeout: subprocess killed after configurable timeout (default 60s)
    - Resource limits via RLIMIT (memory, CPU time, open files)
"""

from __future__ import annotations

import asyncio
import importlib.util
import json
import logging
import os
import subprocess
import sys
from pathlib import Path
from typing import Any

logger = logging.getLogger("omnibrain.skill_sandbox")


# ═══════════════════════════════════════════════════════════════════════════
# JSON-RPC Protocol Constants
# ═══════════════════════════════════════════════════════════════════════════

RPC_MEMORY_SEARCH = "memory_search"
RPC_MEMORY_STORE = "memory_store"
RPC_NOTIFY = "notify"
RPC_PROPOSE = "propose_action"
RPC_LLM_COMPLETE = "llm_complete"
RPC_GET_EVENTS = "get_events"
RPC_GET_CONTACTS = "get_contacts"
RPC_GET_PREFERENCE = "get_preference"
RPC_LOG = "log"
RPC_EMIT_EVENT = "emit_event"

# Allowed RPC methods — anything else is denied
ALLOWED_METHODS = {
    RPC_MEMORY_SEARCH, RPC_MEMORY_STORE, RPC_NOTIFY, RPC_PROPOSE,
    RPC_LLM_COMPLETE, RPC_GET_EVENTS, RPC_GET_CONTACTS,
    RPC_GET_PREFERENCE, RPC_LOG, RPC_EMIT_EVENT,
}


# ═══════════════════════════════════════════════════════════════════════════
# Sandbox Bridge (Main Process Side)
# ═══════════════════════════════════════════════════════════════════════════


class SkillSandboxBridge:
    """Handles JSON-RPC communication with a sandboxed skill subprocess.

    Validates every incoming RPC call against the skill's declared permissions.
    Enforces rate limits and resource constraints.

    This class runs in the MAIN PROCESS — it's the gatekeeper.
    """

    # Permission mapping: RPC method → required permission
    PERMISSION_MAP = {
        RPC_MEMORY_SEARCH: "read_memory",
        RPC_MEMORY_STORE: "write_memory",
        RPC_NOTIFY: "notify",
        RPC_PROPOSE: "propose_actions",
        RPC_LLM_COMPLETE: "llm_access",
        RPC_GET_EVENTS: "read_events",
        RPC_GET_CONTACTS: "read_contacts",
        RPC_GET_PREFERENCE: "read_preferences",
        RPC_LOG: None,  # Always allowed
        RPC_EMIT_EVENT: "emit_events",
    }

    def __init__(
        self,
        *,
        skill_name: str,
        permissions: set[str],
        db: Any = None,
        memory: Any = None,
        knowledge_graph: Any = None,
        approval_gate: Any = None,
        config: Any = None,
        event_bus: Any = None,
        llm_router: Any = None,
    ) -> None:
        self.skill_name = skill_name
        self.permissions = permissions
        self._db = db
        self._memory = memory
        self._kg = knowledge_graph
        self._approval = approval_gate
        self._config = config
        self._event_bus = event_bus
        self._llm_router = llm_router
        self._call_count = 0
        self._max_calls_per_invocation = 100

    def check_permission(self, method: str) -> bool:
        """Check if the skill has permission for this RPC method."""
        required = self.PERMISSION_MAP.get(method)
        if required is None:
            return True  # No permission required (e.g., log)
        return required in self.permissions

    async def handle_rpc(self, request: dict[str, Any]) -> dict[str, Any]:
        """Process a single JSON-RPC request from the subprocess.

        Returns a JSON-RPC response dict.
        """
        method = request.get("method", "")
        params = request.get("params", {})
        req_id = request.get("id", 0)

        # Rate limit
        self._call_count += 1
        if self._call_count > self._max_calls_per_invocation:
            return {
                "id": req_id,
                "error": {"code": -32000, "message": "Rate limit exceeded"},
            }

        # Permission check
        if not self.check_permission(method):
            return {
                "id": req_id,
                "error": {
                    "code": -32001,
                    "message": f"Permission denied: {method} requires "
                               f"{self.PERMISSION_MAP.get(method, 'unknown')}",
                },
            }

        try:
            result = await self._dispatch(method, params)
            return {"id": req_id, "result": result}
        except Exception as e:
            return {
                "id": req_id,
                "error": {"code": -32603, "message": str(e)[:500]},
            }

    async def _dispatch(self, method: str, params: dict[str, Any]) -> Any:
        """Dispatch an RPC call to the appropriate core service."""
        if method == RPC_MEMORY_SEARCH:
            if self._memory:
                results = self._memory.search(
                    params.get("query", ""),
                    max_results=params.get("max_results", 10),
                )
                return [{"text": r.text, "source": r.source, "score": r.score} for r in results]
            return []

        elif method == RPC_MEMORY_STORE:
            if self._memory:
                self._memory.store(
                    text=params.get("text", ""),
                    source=f"skill:{self.skill_name}",
                    source_type=params.get("source_type", "skill_data"),
                )
                return True
            return False

        elif method == RPC_NOTIFY:
            # Notifications go through event bus to reach frontend
            if self._event_bus:
                self._event_bus.publish("notification", {
                    "skill": self.skill_name,
                    "level": params.get("level", "fyi"),
                    "title": params.get("title", ""),
                    "message": params.get("message", ""),
                })
            return True

        elif method == RPC_PROPOSE:
            if self._db:
                self._db.create_proposal(
                    type=params.get("type", "skill_action"),
                    title=params.get("title", ""),
                    description=params.get("description", ""),
                    action_data=json.dumps(params.get("action_data", {})),
                    priority=params.get("priority", 2),
                )
                return True
            return False

        elif method == RPC_LLM_COMPLETE:
            if self._llm_router:
                messages = params.get("messages", [])
                result_parts = []
                async for chunk in self._llm_router.stream(messages):
                    if chunk.content:
                        result_parts.append(chunk.content)
                return "".join(result_parts)
            return ""

        elif method == RPC_GET_EVENTS:
            if self._db:
                events = self._db.get_events(
                    limit=params.get("limit", 50),
                    source=params.get("source", ""),
                )
                return events
            return []

        elif method == RPC_GET_CONTACTS:
            if self._db:
                contacts = self._db.get_contacts(limit=params.get("limit", 50))
                return [c.__dict__ if hasattr(c, "__dict__") else c for c in contacts]
            return []

        elif method == RPC_GET_PREFERENCE:
            if self._db:
                return self._db.get_preference(params.get("key", ""))
            return None

        elif method == RPC_LOG:
            level = params.get("level", "info")
            message = params.get("message", "")
            logger.log(
                getattr(logging, level.upper(), logging.INFO),
                f"[skill:{self.skill_name}] {message}",
            )
            return True

        elif method == RPC_EMIT_EVENT:
            if self._event_bus:
                self._event_bus.publish(
                    params.get("event_type", "skill_event"),
                    params.get("data", {}),
                )
            return True

        return None


# ═══════════════════════════════════════════════════════════════════════════
# Sandbox Executor (Main Process — launches subprocess)
# ═══════════════════════════════════════════════════════════════════════════


async def run_handler_sandboxed(
    *,
    skill_name: str,
    skill_path: Path,
    handler_relpath: str,
    handler_key: str,
    permissions: set[str],
    args_json: str = "[]",
    kwargs_json: str = "{}",
    timeout: int = 60,
    python_executable: str | None = None,
    db: Any = None,
    memory: Any = None,
    knowledge_graph: Any = None,
    approval_gate: Any = None,
    config: Any = None,
    event_bus: Any = None,
    llm_router: Any = None,
) -> Any:
    """Launch a skill handler in an isolated subprocess.

    Communication protocol:
    - Subprocess writes JSON-RPC requests to stdout (one per line)
    - Main process responds via stdin
    - Last line from subprocess is the return value (JSON)
    - Subprocess exits with code 0 on success
    """
    bridge = SkillSandboxBridge(
        skill_name=skill_name,
        permissions=permissions,
        db=db,
        memory=memory,
        knowledge_graph=knowledge_graph,
        approval_gate=approval_gate,
        config=config,
        event_bus=event_bus,
        llm_router=llm_router,
    )

    # Determine Python executable (use skill venv if available)
    if python_executable is None:
        venv_python = skill_path / ".venv" / "bin" / "python"
        if venv_python.exists():
            python_executable = str(venv_python)
        else:
            python_executable = sys.executable

    handler_file = str(skill_path / handler_relpath)

    # Launch subprocess
    env = {
        **os.environ,
        "OMNIBRAIN_SKILL_NAME": skill_name,
        "OMNIBRAIN_SKILL_HANDLER_KEY": handler_key,
        "OMNIBRAIN_SKILL_HANDLER_FILE": handler_file,
        "OMNIBRAIN_SKILL_ARGS": args_json,
        "OMNIBRAIN_SKILL_KWARGS": kwargs_json,
    }

    try:
        proc = await asyncio.create_subprocess_exec(
            python_executable, "-m", "omnibrain.skill_sandbox",
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            env=env,
            cwd=str(skill_path),
        )
    except Exception as e:
        logger.error(f"Failed to launch sandbox for {skill_name}: {e}")
        return None

    result = None
    try:
        # Process JSON-RPC communication with timeout
        async with asyncio.timeout(timeout):
            while True:
                line = await proc.stdout.readline()
                if not line:
                    break

                line_str = line.decode().strip()
                if not line_str:
                    continue

                try:
                    msg = json.loads(line_str)
                except json.JSONDecodeError:
                    continue

                # Check if it's a final result or an RPC request
                if "method" in msg:
                    # RPC request — handle and respond
                    response = await bridge.handle_rpc(msg)
                    response_line = json.dumps(response) + "\n"
                    proc.stdin.write(response_line.encode())
                    await proc.stdin.drain()
                elif "result" in msg:
                    # Final result from handler
                    result = msg["result"]

    except TimeoutError:
        logger.warning(f"Skill {skill_name} handler timed out after {timeout}s")
        proc.kill()
    except Exception as e:
        logger.error(f"Sandbox communication error for {skill_name}: {e}")
    finally:
        try:
            proc.stdin.close()
        except Exception:
            pass
        try:
            await asyncio.wait_for(proc.wait(), timeout=5)
        except TimeoutError:
            proc.kill()

    # Log stderr for debugging
    if proc.stderr:
        stderr_bytes = await proc.stderr.read()
        if stderr_bytes:
            stderr_text = stderr_bytes.decode(errors="replace").strip()
            if stderr_text:
                logger.debug(f"[skill:{skill_name}] stderr: {stderr_text}")

    return result


# ═══════════════════════════════════════════════════════════════════════════
# Skill venv management
# ═══════════════════════════════════════════════════════════════════════════


def ensure_skill_venv(skill_path: Path, dependencies: list[str]) -> str:
    """Create and populate a per-skill venv if it has dependencies.

    Returns the path to the Python executable in the venv.
    If no deps, returns sys.executable.
    """
    if not dependencies:
        return sys.executable

    venv_path = skill_path / ".venv"
    venv_python = venv_path / "bin" / "python"

    # Check if venv already exists and is usable
    if venv_python.exists():
        # Verify deps are installed (check marker file)
        marker = venv_path / ".deps_installed"
        deps_hash = _hash_deps(dependencies)
        if marker.exists() and marker.read_text().strip() == deps_hash:
            return str(venv_python)

    logger.info(f"Creating venv for skill at {skill_path}")
    try:
        # Create venv
        subprocess.run(
            [sys.executable, "-m", "venv", str(venv_path)],
            check=True,
            capture_output=True,
            timeout=60,
        )

        # Install dependencies
        subprocess.run(
            [str(venv_python), "-m", "pip", "install", "--quiet", *dependencies],
            check=True,
            capture_output=True,
            timeout=300,
        )

        # Write marker
        deps_hash = _hash_deps(dependencies)
        (venv_path / ".deps_installed").write_text(deps_hash)

        logger.info(f"Skill venv created with {len(dependencies)} deps")
        return str(venv_python)

    except subprocess.CalledProcessError as e:
        logger.error(f"Failed to create skill venv: {e.stderr.decode() if e.stderr else e}")
        return sys.executable
    except Exception as e:
        logger.error(f"Venv creation error: {e}")
        return sys.executable


def _hash_deps(deps: list[str]) -> str:
    """Hash dep list for venv cache invalidation."""
    import hashlib

    return hashlib.md5("|".join(sorted(deps)).encode()).hexdigest()


# ═══════════════════════════════════════════════════════════════════════════
# SkillContextProxy (Subprocess Side)
# ═══════════════════════════════════════════════════════════════════════════


class SkillContextProxy:
    """A proxy that implements the same async interface as SkillContext,
    but communicates with the main process via stdin/stdout JSON-RPC.

    This runs INSIDE the sandboxed subprocess.
    """

    def __init__(self, skill_name: str) -> None:
        self.skill_name = skill_name
        self._request_id = 0

    def _send_rpc(self, method: str, params: dict[str, Any] = None) -> Any:
        """Send a JSON-RPC request and wait for response (blocking)."""
        self._request_id += 1
        request = {
            "jsonrpc": "2.0",
            "id": self._request_id,
            "method": method,
            "params": params or {},
        }

        # Write to stdout (main process reads this)
        sys.stdout.write(json.dumps(request) + "\n")
        sys.stdout.flush()

        # Read response from stdin (main process writes this)
        line = sys.stdin.readline()
        if not line:
            return None

        try:
            response = json.loads(line.strip())
        except json.JSONDecodeError:
            return None

        if "error" in response:
            raise RuntimeError(response["error"].get("message", "RPC error"))

        return response.get("result")

    # ── Memory ──

    async def memory_search(self, query: str, max_results: int = 10) -> list[dict]:
        return self._send_rpc(RPC_MEMORY_SEARCH, {"query": query, "max_results": max_results})

    async def memory_store(self, text: str, source_type: str = "skill_data") -> bool:
        return self._send_rpc(RPC_MEMORY_STORE, {"text": text, "source_type": source_type})

    # ── Notifications ──

    async def notify(self, message: str, level: str = "fyi", title: str = "") -> bool:
        return self._send_rpc(RPC_NOTIFY, {"title": title, "message": message, "level": level})

    # ── Proposals ──

    async def propose_action(
        self,
        title: str,
        description: str = "",
        type: str = "skill_action",
        priority: int = 2,
        action_data: dict = None,
    ) -> bool:
        return self._send_rpc(RPC_PROPOSE, {
            "title": title,
            "description": description,
            "type": type,
            "priority": priority,
            "action_data": action_data or {},
        })

    # ── LLM ──

    async def llm_complete(self, messages: list[dict]) -> str:
        return self._send_rpc(RPC_LLM_COMPLETE, {"messages": messages})

    # ── Data access ──

    async def get_events(self, limit: int = 50, source: str = "") -> list[dict]:
        return self._send_rpc(RPC_GET_EVENTS, {"limit": limit, "source": source})

    async def get_contacts(self, limit: int = 50) -> list[dict]:
        return self._send_rpc(RPC_GET_CONTACTS, {"limit": limit})

    async def get_preference(self, key: str) -> Any:
        return self._send_rpc(RPC_GET_PREFERENCE, {"key": key})

    # ── Logging ──

    async def log(self, message: str, level: str = "info") -> None:
        self._send_rpc(RPC_LOG, {"message": message, "level": level})

    # ── Events ──

    async def emit_event(self, event_type: str, data: dict = None) -> None:
        self._send_rpc(RPC_EMIT_EVENT, {"event_type": event_type, "data": data or {}})


# ═══════════════════════════════════════════════════════════════════════════
# Subprocess entry point
# ═══════════════════════════════════════════════════════════════════════════


def _run_in_subprocess() -> None:
    """Entry point when run as ``python -m omnibrain.skill_sandbox``.

    Reads handler info from environment variables, loads the handler,
    creates a SkillContextProxy, and executes the handler.
    """
    skill_name = os.environ.get("OMNIBRAIN_SKILL_NAME", "unknown")
    handler_file = os.environ.get("OMNIBRAIN_SKILL_HANDLER_FILE", "")
    _handler_key = os.environ.get("OMNIBRAIN_SKILL_HANDLER_KEY", "")
    args_json = os.environ.get("OMNIBRAIN_SKILL_ARGS", "[]")
    kwargs_json = os.environ.get("OMNIBRAIN_SKILL_KWARGS", "{}")

    if not handler_file or not os.path.exists(handler_file):
        sys.stderr.write(f"Handler file not found: {handler_file}\n")
        sys.exit(1)

    # Apply resource limits (best-effort, Linux only)
    try:
        import resource

        # 256 MB max memory
        resource.setrlimit(resource.RLIMIT_AS, (256 * 1024 * 1024, 256 * 1024 * 1024))
        # 30 seconds CPU time
        resource.setrlimit(resource.RLIMIT_CPU, (30, 30))
        # 64 open file descriptors
        resource.setrlimit(resource.RLIMIT_NOFILE, (64, 64))
    except (ImportError, ValueError, OSError):
        pass  # Not available on all platforms

    # Load handler module
    try:
        module_name = f"skill_handler_{Path(handler_file).stem}"
        spec = importlib.util.spec_from_file_location(module_name, handler_file)
        if spec is None or spec.loader is None:
            sys.stderr.write(f"Cannot load handler spec: {handler_file}\n")
            sys.exit(1)

        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)

        handle_fn = getattr(module, "handle", None)
        if handle_fn is None:
            sys.stderr.write(f"Handler {handler_file} has no 'handle' function\n")
            sys.exit(1)
    except Exception as e:
        sys.stderr.write(f"Failed to load handler: {e}\n")
        sys.exit(1)

    # Create context proxy
    ctx = SkillContextProxy(skill_name)

    # Parse args
    try:
        args = json.loads(args_json)
        kwargs = json.loads(kwargs_json)
    except json.JSONDecodeError:
        args = []
        kwargs = {}

    # Run handler
    try:
        result = asyncio.run(handle_fn(ctx, *args, **kwargs))
        # Write final result to stdout
        sys.stdout.write(json.dumps({"result": result}) + "\n")
        sys.stdout.flush()
    except Exception as e:
        sys.stderr.write(f"Handler execution failed: {e}\n")
        sys.exit(1)


if __name__ == "__main__":
    _run_in_subprocess()

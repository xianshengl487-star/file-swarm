"""Quick benchmark — only fast NVIDIA models."""
from __future__ import annotations
import asyncio, json, os, sys, time
from pathlib import Path
PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))
from src.file_swarm.agent_executor import execute_agent_task, list_mcp_tools
from src.file_swarm.providers.openai_compatible_provider import OpenAICompatibleProvider

KEY = os.environ.get("NVIDIA_API_KEY") or os.environ.get("NVIDIA_API_KEY_01")
BASE = "https://integrate.api.nvidia.com/v1"

WORKING_MODELS = [
    ("z-ai/glm-5.1", "GLM-5.1"),
    ("meta/llama-3.3-70b-instruct", "Llama-3.3-70B"),
    ("meta/llama-4-maverick-17b-128e-instruct", "Llama-4-Maverick"),
    ("deepseek-ai/deepseek-v4-pro", "DeepSeek-V4-Pro"),
    ("moonshotai/kimi-k2.6", "Kimi-K2.6"),
    ("mistralai/mistral-nemotron", "Mistral-Nemotron"),
    ("nvidia/llama-3.3-nemotron-super-49b-v1.5", "Nemotron-Super-49B"),
    ("openai/gpt-oss-120b", "GPT-OSS-120B"),
    ("stepfun-ai/step-3.7-flash", "Step-3.7-Flash"),
    ("qwen/qwen3-next-80b-a3b-instruct", "Qwen3-Next-80B"),
    ("mistralai/mistral-small-4-119b-2603", "Mistral-Small-4"),
]

TASKS = [
    ("system-info", "Check system information: list CPU info, memory usage, disk space, and OS version."),
    ("file-ops", "Create a test directory, write a hello world file, list its contents, then read the file back."),
    ("browser-ctrl", "Open browser to https://httpbin.org/get and fetch the page content."),
    ("mouse-sim", "Simulate mouse movement to center of screen (960, 540), take a screenshot, then type 'Hello World' and press Enter."),
    ("mcp-tools", "Use MCP tools to: get current datetime, read environment variables, and make an HTTP GET request to https://httpbin.org/uuid."),
]

async def main():
    if not KEY:
        print("Skipped: set NVIDIA_API_KEY or NVIDIA_API_KEY_01 to run this live benchmark.")
        return

    provider = OpenAICompatibleProvider(base_url=BASE, api_key=KEY, timeout=120.0)
    cwd = Path.cwd()
    all_results = []

    print(f"Models: {len(WORKING_MODELS)}, Tasks: {len(TASKS)}")
    print(f"MCP tools: {list_mcp_tools()}\n")

    for model_id, label in WORKING_MODELS:
        print(f"── {label} ({model_id}) ──")
        for cat, desc in TASKS:
            print(f"  [{cat}] ", end="", flush=True)
            t0 = time.time()
            try:
                result = await execute_agent_task(
                    task_id=f"{label}_{cat}",
                    task_description=desc,
                    provider=provider,
                    model=model_id,
                    cwd=cwd,
                    dry_run=True,
                    max_tokens=4096,
                )
                elapsed = time.time() - t0
                ok = result.ok and len(result.actions_executed) >= 1
                entry = {
                    "model": label, "model_id": model_id, "category": cat,
                    "pass": ok, "ok": result.ok, "error": result.error,
                    "elapsed_s": round(elapsed, 2),
                    "actions": len(result.actions_executed),
                    "action_types": list(set(a.action_type for a in result.actions_executed)),
                    "input_tokens": result.input_tokens,
                    "output_tokens": result.output_tokens,
                }
                all_results.append(entry)
                status = "PASS" if ok else "FAIL"
                a = entry["actions"]
                t = ",".join(entry["action_types"])
                tok = f"in={result.input_tokens},out={result.output_tokens}" if result.input_tokens else "n/a"
                print(f"{status} ({elapsed:.1f}s, {tok}) a={a} [{t}]")
                if not ok and result.error:
                    print(f"          err: {result.error[:120]}")
            except Exception as e:
                elapsed = time.time() - t0
                all_results.append({"model": label, "model_id": model_id, "category": cat,
                    "pass": False, "ok": False, "error": f"crash:{type(e).__name__}",
                    "elapsed_s": round(elapsed, 2), "actions": 0, "action_types": [],
                    "input_tokens": None, "output_tokens": None})
                print(f"CRASH ({elapsed:.1f}s): {type(e).__name__}")

    # Save
    path = PROJECT_ROOT / "nvidia_benchmark_v2.json"
    with open(path, "w") as f:
        json.dump(all_results, f, indent=2)

    # Summary
    print("\n" + "=" * 80)
    print("NVIDIA BENCHMARK V2 — RESULTS")
    print("=" * 80)
    header = f"{'Model':<25} {'Pass':<7} {'system-info':<14} {'file-ops':<12} {'browser-ctrl':<14} {'mouse-sim':<12} {'mcp-tools':<12}"
    print(header)
    print("─" * 91)
    for label in [m[1] for m in WORKING_MODELS]:
        entries = [r for r in all_results if r["model"] == label]
        if not entries:
            continue
        total = len(entries)
        passed = sum(1 for e in entries if e["pass"])
        cats = {e["category"]: "PASS" if e["pass"] else "FAIL" for e in entries}
        print(f"{label:<25} {passed}/{total:<5} {cats.get('system-info','-'):<14} {cats.get('file-ops','-'):<12} {cats.get('browser-ctrl','-'):<14} {cats.get('mouse-sim','-'):<12} {cats.get('mcp-tools','-'):<12}")

    print(f"\nFull results: {path}")

asyncio.run(main())

"""Cross-model benchmark for enhanced AgentExecutor.

Tests multiple NVIDIA models across 5 task categories:
  1. system-info  - Shell commands for system diagnostics
  2. file-ops     - File operations via shell + MCP tools
  3. browser-ctrl - Browser open + fetch actions
  4. mouse-sim    - Mouse click/move + keyboard simulation
  5. mcp-tools    - MCP tool calls (file_read, http_get, datetime, etc.)

Each model-task combination is tested with a dry_run to avoid
side effects. Results are collected into a benchmark report.
"""

from __future__ import annotations

import asyncio
import json
import os
import sys
import time
from pathlib import Path

# Add project root to path
PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from src.file_swarm.agent_executor import (
    execute_agent_task,
    _detect_task_category,
    list_mcp_tools,
    ActionResult,
    AgentResult,
)
from src.file_swarm.providers.openai_compatible_provider import OpenAICompatibleProvider
from src.file_swarm.providers.anthropic_provider import AnthropicProvider

# ── Configuration ─────────────────────────────────────────────────────────

NVIDIA_BASE_URL = "https://integrate.api.nvidia.com/v1"

NVIDIA_API_KEYS = [
    key for key in [
        os.environ.get("NVIDIA_API_KEY"),
        os.environ.get("NVIDIA_API_KEY_01"),
        os.environ.get("NVIDIA_API_KEY_02"),
    ]
    if key
]

MIMO_BASE_URL = "https://token-plan-sgp.xiaomimimo.com/anthropic"
MIMO_API_KEY = os.environ.get("MIMO_API_KEY") or os.environ.get("MIMO_API_KEY_01")

# Models to test — new JWT-format NVAPI key works with 15/18 models
TEST_MODELS = [
    # NVIDIA (full-access key)
    {"id": "z-ai/glm-5.1", "provider": "nvidia", "key_idx": 0, "label": "GLM-5.1"},
    {"id": "meta/llama-3.3-70b-instruct", "provider": "nvidia", "key_idx": 0, "label": "Llama-3.3-70B"},
    {"id": "meta/llama-4-maverick-17b-128e-instruct", "provider": "nvidia", "key_idx": 0, "label": "Llama-4-Maverick"},
    {"id": "deepseek-ai/deepseek-v4-flash", "provider": "nvidia", "key_idx": 0, "label": "DeepSeek-V4-Flash"},
    {"id": "deepseek-ai/deepseek-v4-pro", "provider": "nvidia", "key_idx": 0, "label": "DeepSeek-V4-Pro"},
    {"id": "qwen/qwen3.5-122b-a10b", "provider": "nvidia", "key_idx": 0, "label": "Qwen3.5-122B"},
    {"id": "qwen/qwen3-next-80b-a3b-instruct", "provider": "nvidia", "key_idx": 0, "label": "Qwen3-Next-80B"},
    {"id": "moonshotai/kimi-k2.6", "provider": "nvidia", "key_idx": 0, "label": "Kimi-K2.6"},
    {"id": "mistralai/mistral-small-4-119b-2603", "provider": "nvidia", "key_idx": 0, "label": "Mistral-Small-4"},
    {"id": "mistralai/mistral-nemotron", "provider": "nvidia", "key_idx": 0, "label": "Mistral-Nemotron"},
    {"id": "nvidia/llama-3.3-nemotron-super-49b-v1.5", "provider": "nvidia", "key_idx": 0, "label": "Nemotron-Super-49B"},
    {"id": "openai/gpt-oss-120b", "provider": "nvidia", "key_idx": 0, "label": "GPT-OSS-120B"},
    {"id": "bytedance/seed-oss-36b-instruct", "provider": "nvidia", "key_idx": 0, "label": "Seed-OSS-36B"},
    {"id": "stepfun-ai/step-3.7-flash", "provider": "nvidia", "key_idx": 0, "label": "Step-3.7-Flash"},
    {"id": "minimaxai/minimax-m3", "provider": "nvidia", "key_idx": 0, "label": "MiniMax-M3"},
    # Mimo (Anthropic API)
    {"id": "mimo-v2.5", "provider": "mimo", "key_idx": 0, "label": "Mimo-v2.5"},
    {"id": "mimo-v2.5-pro", "provider": "mimo", "key_idx": 0, "label": "Mimo-v2.5-Pro"},
]

# Task definitions for each category
TASKS = [
    {
        "category": "system-info",
        "description": "Check system information: list CPU info, memory usage, disk space, and OS version. Generate a summary report.",
        "expected_actions": ["shell"],
        "min_actions": 2,
    },
    {
        "category": "file-ops",
        "description": "Create a test directory, write a hello world file, list its contents, then read the file back. Use file operations.",
        "expected_actions": ["shell", "mcp_call"],
        "min_actions": 2,
    },
    {
        "category": "browser-ctrl",
        "description": "Open browser to https://httpbin.org/get and fetch the page content to see the JSON response. Then extract the user-agent.",
        "expected_actions": ["browser_open", "browser_fetch"],
        "min_actions": 1,
    },
    {
        "category": "mouse-sim",
        "description": "Simulate mouse movement to center of screen (960, 540), take a screenshot, then type 'Hello World' and press Enter.",
        "expected_actions": ["mouse_move", "screenshot", "key_type", "key_press"],
        "min_actions": 2,
    },
    {
        "category": "mcp-tools",
        "description": "Use MCP tools to: get current datetime, read environment variables, and make an HTTP GET request to https://httpbin.org/uuid. Report all results.",
        "expected_actions": ["mcp_call"],
        "min_actions": 2,
    },
]


def create_provider(model_config: dict):
    """Create the appropriate provider for a model."""
    if model_config["provider"] == "nvidia":
        if not NVIDIA_API_KEYS:
            raise RuntimeError("missing NVIDIA_API_KEY or NVIDIA_API_KEY_01")
        key = NVIDIA_API_KEYS[model_config["key_idx"] % len(NVIDIA_API_KEYS)]
        return OpenAICompatibleProvider(base_url=NVIDIA_BASE_URL, api_key=key, timeout=60.0)
    elif model_config["provider"] == "mimo":
        if not MIMO_API_KEY:
            raise RuntimeError("missing MIMO_API_KEY or MIMO_API_KEY_01")
        return AnthropicProvider(base_url=MIMO_BASE_URL, api_key=MIMO_API_KEY, timeout=60.0)
    else:
        raise ValueError(f"Unknown provider: {model_config['provider']}")


def evaluate_result(result: AgentResult, task: dict) -> dict:
    """Evaluate an agent result against task expectations."""
    evaluation = {
        "ok": result.ok,
        "error": result.error,
        "actions_count": len(result.actions_executed),
        "action_types": list(set(ar.action_type for ar in result.actions_executed)),
        "input_tokens": result.input_tokens,
        "output_tokens": result.output_tokens,
        "has_expected_types": False,
        "meets_min_actions": False,
        "summary": result.summary[:500] if result.summary else "",
    }

    # Check if expected action types are present
    expected = task.get("expected_actions", [])
    if expected:
        found_types = set(ar.action_type for ar in result.actions_executed)
        # For shell-expected tasks, also accept mcp_call as equivalent
        if "shell" in expected and "mcp_call" in found_types and not result.actions_executed:
            found_types.add("shell")
        evaluation["has_expected_types"] = any(
            exp in found_types or
            (exp == "shell" and "mcp_call" in found_types) or
            (exp == "mcp_call" and "shell" in found_types)
            for exp in expected
        )

    # Check minimum action count
    min_actions = task.get("min_actions", 1)
    evaluation["meets_min_actions"] = len(result.actions_executed) >= min_actions

    # Overall pass: ok AND has_expected_types AND meets_min_actions
    evaluation["pass"] = (
        result.ok and
        evaluation["has_expected_types"] and
        evaluation["meets_min_actions"]
    )

    return evaluation


async def run_single_test(
    model_config: dict,
    task: dict,
    cwd: Path,
    dry_run: bool = True,
) -> dict:
    """Run a single model-task combination."""
    model_id = model_config["id"]
    model_label = model_config["label"]
    category = task["category"]

    provider = create_provider(model_config)

    t0 = time.time()
    try:
        result = await execute_agent_task(
            task_id=f"{model_label}_{category}",
            task_description=task["description"],
            provider=provider,
            model=model_id,
            cwd=cwd,
            dry_run=dry_run,
            max_tokens=4096,  # Higher initial tokens to avoid thinking-block empty responses
        )
    except Exception as exc:
        elapsed = time.time() - t0
        return {
            "model": model_label,
            "model_id": model_id,
            "category": category,
            "pass": False,
            "error": f"exception: {type(exc).__name__}: {str(exc)[:200]}",
            "elapsed_s": round(elapsed, 2),
            "actions_count": 0,
            "action_types": [],
            "input_tokens": None,
            "output_tokens": None,
            "summary": "",
        }

    elapsed = time.time() - t0
    evaluation = evaluate_result(result, task)

    return {
        "model": model_label,
        "model_id": model_id,
        "category": category,
        "pass": evaluation["pass"],
        "ok": evaluation["ok"],
        "error": evaluation["error"],
        "elapsed_s": round(elapsed, 2),
        "actions_count": evaluation["actions_count"],
        "action_types": evaluation["action_types"],
        "has_expected_types": evaluation["has_expected_types"],
        "meets_min_actions": evaluation["meets_min_actions"],
        "input_tokens": evaluation["input_tokens"],
        "output_tokens": evaluation["output_tokens"],
        "summary": evaluation["summary"],
    }


async def run_benchmark():
    """Run the full cross-model benchmark."""
    cwd = Path.cwd()
    dry_run = True  # Safety: dry run to avoid side effects
    runnable_models = [
        model for model in TEST_MODELS
        if (model["provider"] == "nvidia" and NVIDIA_API_KEYS)
        or (model["provider"] == "mimo" and MIMO_API_KEY)
    ]
    if not runnable_models:
        print("Skipped: set NVIDIA_API_KEY/NVIDIA_API_KEY_01 or MIMO_API_KEY/MIMO_API_KEY_01 to run live benchmarks.")
        return []

    print("=" * 80)
    print("FileSwarm Enhanced AgentExecutor - Cross-Model Benchmark")
    print("=" * 80)
    print(f"Models: {len(runnable_models)}")
    print(f"Tasks: {len(TASKS)} categories")
    print(f"Total combinations: {len(runnable_models) * len(TASKS)}")
    print(f"Mode: {'DRY RUN (safe)' if dry_run else 'LIVE EXECUTION'}")
    print(f"MCP tools available: {list_mcp_tools()}")
    print("=" * 80)
    print()

    all_results: list[dict] = []

    # Run tests sequentially to avoid rate limits
    for model_config in runnable_models:
        model_label = model_config["label"]
        print(f"\n{'─' * 60}")
        print(f"Testing: {model_label} ({model_config['id']})")
        print(f"{'─' * 60}")

        skip_model = False  # Skip remaining tasks if API returns 403

        for task in TASKS:
            category = task["category"]

            if skip_model:
                # Record skipped result
                all_results.append({
                    "model": model_label,
                    "model_id": model_config["id"],
                    "category": category,
                    "pass": False,
                    "ok": False,
                    "error": "skipped (api_403)",
                    "elapsed_s": 0,
                    "actions_count": 0,
                    "action_types": [],
                    "has_expected_types": False,
                    "meets_min_actions": False,
                    "input_tokens": None,
                    "output_tokens": None,
                    "summary": "Skipped due to API 403 on previous task",
                })
                print(f"  [{category}] SKIP (api_403)")
                continue

            print(f"  [{category}] ", end="", flush=True)

            result = await run_single_test(model_config, task, cwd, dry_run=dry_run)
            all_results.append(result)

            status = "PASS" if result["pass"] else "FAIL"
            tokens = f"in={result['input_tokens']},out={result['output_tokens']}" if result["input_tokens"] else "n/a"
            print(f"{status} ({result['elapsed_s']}s, {tokens}) actions={result['actions_count']} types={result['action_types']}")

            # If API returns 403 or 404, skip remaining tasks for this model
            err = result.get("error") or ""
            if err.startswith("api_error_status_403") or err.startswith("api_error_status_404"):
                skip_model = True

            if not result["pass"] and err:
                print(f"         error: {err[:120]}")

    # ── Generate summary report ────────────────────────────────────
    print("\n\n" + "=" * 80)
    print("BENCHMARK RESULTS SUMMARY")
    print("=" * 80)

    # Per-model pass rate
    print("\n── Per-Model Pass Rate ──")
    model_stats: dict[str, dict] = {}
    for r in all_results:
        label = r["model"]
        if label not in model_stats:
            model_stats[label] = {"pass": 0, "total": 0, "categories": {}}
        model_stats[label]["total"] += 1
        if r["pass"]:
            model_stats[label]["pass"] += 1
        model_stats[label]["categories"][r["category"]] = "PASS" if r["pass"] else "FAIL"

    # Sort by pass rate descending
    sorted_models = sorted(model_stats.items(), key=lambda x: x[1]["pass"], reverse=True)

    print(f"\n{'Model':<25} {'Pass Rate':<12} {'system-info':<14} {'file-ops':<12} {'browser-ctrl':<14} {'mouse-sim':<12} {'mcp-tools':<12}")
    print("─" * 101)
    for label, stats in sorted_models:
        cats = stats["categories"]
        print(
            f"{label:<25} {stats['pass']}/{stats['total']:<10} "
            f"{cats.get('system-info', 'N/A'):<14} "
            f"{cats.get('file-ops', 'N/A'):<12} "
            f"{cats.get('browser-ctrl', 'N/A'):<14} "
            f"{cats.get('mouse-sim', 'N/A'):<12} "
            f"{cats.get('mcp-tools', 'N/A'):<12}"
        )

    # Token efficiency
    print("\n── Token Efficiency (avg output tokens per task) ──")
    token_stats: dict[str, list] = {}
    for r in all_results:
        label = r["model"]
        if label not in token_stats:
            token_stats[label] = []
        if r["output_tokens"]:
            token_stats[label].append(r["output_tokens"])

    for label in sorted(token_stats.keys()):
        tokens = token_stats[label]
        if tokens:
            avg = sum(tokens) / len(tokens)
            print(f"  {label:<25} avg={avg:.0f} tokens (n={len(tokens)})")

    # Per-category pass rate
    print("\n── Per-Category Pass Rate ──")
    category_stats: dict[str, dict] = {}
    for r in all_results:
        cat = r["category"]
        if cat not in category_stats:
            category_stats[cat] = {"pass": 0, "total": 0}
        category_stats[cat]["total"] += 1
        if r["pass"]:
            category_stats[cat]["pass"] += 1

    for cat, stats in category_stats.items():
        rate = stats["pass"] / stats["total"] * 100 if stats["total"] > 0 else 0
        print(f"  {cat:<20} {stats['pass']}/{stats['total']} ({rate:.0f}%)")

    # Save full results to JSON
    results_path = PROJECT_ROOT / "benchmark_results.json"
    with open(results_path, "w", encoding="utf-8") as f:
        json.dump(all_results, f, ensure_ascii=False, indent=2)
    print(f"\nFull results saved to: {results_path}")

    # Generate markdown report
    report_path = await generate_markdown_report(all_results, model_stats, sorted_models)
    print(f"Markdown report saved to: {report_path}")

    return all_results


async def generate_markdown_report(
    all_results: list[dict],
    model_stats: dict,
    sorted_models: list,
) -> Path:
    """Generate a detailed markdown benchmark report."""
    report_path = PROJECT_ROOT / "benchmark_report.md"

    lines: list[str] = []
    lines.append("# FileSwarm Enhanced AgentExecutor - Cross-Model Benchmark Report\n")
    lines.append(f"**Date**: {time.strftime('%Y-%m-%d %H:%M:%S')}\n")
    lines.append(f"**Models tested**: {len(TEST_MODELS)}\n")
    lines.append(f"**Task categories**: {len(TASKS)}\n")
    lines.append(f"**Total combinations**: {len(all_results)}\n")
    lines.append(f"**Mode**: Dry run (safe, no side effects)\n\n")

    # Summary table
    lines.append("## Summary Matrix\n")
    lines.append("| Model | Pass Rate | system-info | file-ops | browser-ctrl | mouse-sim | mcp-tools |")
    lines.append("|-------|-----------|-------------|----------|--------------|-----------|-----------|")
    for label, stats in sorted_models:
        cats = stats["categories"]
        rate = f"{stats['pass']}/{stats['total']}"
        lines.append(
            f"| {label} | {rate} | "
            f"{cats.get('system-info', '-')} | "
            f"{cats.get('file-ops', '-')} | "
            f"{cats.get('browser-ctrl', '-')} | "
            f"{cats.get('mouse-sim', '-')} | "
            f"{cats.get('mcp-tools', '-')} |"
        )

    # Token efficiency
    lines.append("\n## Token Efficiency\n")
    lines.append("| Model | Avg Output Tokens | Sample Count |")
    lines.append("|-------|------------------|--------------|")
    token_stats: dict[str, list[int]] = {}
    for r in all_results:
        label = r["model"]
        if label not in token_stats:
            token_stats[label] = []
        if r["output_tokens"]:
            token_stats[label].append(r["output_tokens"])
    for label in sorted(token_stats.keys()):
        tokens = token_stats[label]
        if tokens:
            avg = sum(tokens) / len(tokens)
            lines.append(f"| {label} | {avg:.0f} | {len(tokens)} |")

    # Per-category analysis
    lines.append("\n## Per-Category Analysis\n")
    for task in TASKS:
        cat = task["category"]
        cat_results = [r for r in all_results if r["category"] == cat]
        passed = [r for r in cat_results if r["pass"]]
        lines.append(f"### {cat}\n")
        lines.append(f"- **Pass rate**: {len(passed)}/{len(cat_results)}")
        lines.append(f"- **Description**: {task['description'][:100]}...")
        lines.append(f"- **Expected action types**: {task['expected_actions']}")
        lines.append(f"- **Min actions**: {task['min_actions']}\n")

        if passed:
            best = min(passed, key=lambda x: x["output_tokens"] or 999999)
            lines.append(f"- **Most efficient**: {best['model']} ({best['output_tokens']} output tokens)")
        if len(passed) < len(cat_results):
            failed = [r for r in cat_results if not r["pass"]]
            lines.append(f"- **Failed models**: {', '.join(r['model'] for r in failed)}")
        lines.append("")

    # Recommendations
    lines.append("## Recommendations\n")
    best_models = [m for m in sorted_models if m[1]["pass"] >= 3]
    if best_models:
        lines.append("### Best All-Rounders (3+ categories passed)\n")
        for label, stats in best_models:
            lines.append(f"- **{label}**: {stats['pass']}/{stats['total']} categories passed")
    else:
        lines.append("### No model passed 3+ categories. Consider task-specific model selection.\n")

    # Category-specific recommendations
    lines.append("\n### Category-Specific Recommendations\n")
    for task in TASKS:
        cat = task["category"]
        cat_passed = [r for r in all_results if r["category"] == cat and r["pass"]]
        if cat_passed:
            # Sort by token efficiency
            cat_passed.sort(key=lambda x: x["output_tokens"] or 999999)
            best = cat_passed[0]
            lines.append(f"- **{cat}**: Best = {best['model']} ({best['output_tokens']} tokens, {best['elapsed_s']}s)")
        else:
            lines.append(f"- **{cat}**: No model passed")

    # Error analysis
    lines.append("\n## Error Analysis\n")
    error_types: dict[str, int] = {}
    for r in all_results:
        if not r["pass"] and r["error"]:
            err = r["error"].split(":")[0] if ":" in r["error"] else r["error"]
            error_types[err] = error_types.get(err, 0) + 1
    if error_types:
        lines.append("| Error Type | Count |")
        lines.append("|------------|-------|")
        for err, count in sorted(error_types.items(), key=lambda x: x[1], reverse=True):
            lines.append(f"| {err} | {count} |")
    else:
        lines.append("No errors detected.")

    # Detailed results
    lines.append("\n## Detailed Results\n")
    for r in all_results:
        status = "PASS" if r["pass"] else "FAIL"
        lines.append(f"### {r['model']} - {r['category']} [{status}]\n")
        lines.append(f"- Model ID: `{r['model_id']}`")
        lines.append(f"- Elapsed: {r['elapsed_s']}s")
        lines.append(f"- Actions: {r['actions_count']} ({', '.join(r['action_types'])})")
        lines.append(f"- Tokens: input={r['input_tokens']}, output={r['output_tokens']}")
        if r["error"]:
            lines.append(f"- Error: `{r['error']}`")
        if r["summary"]:
            lines.append(f"- Summary: {r['summary'][:300]}")
        lines.append("")

    with open(report_path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))

    return report_path


if __name__ == "__main__":
    asyncio.run(run_benchmark())

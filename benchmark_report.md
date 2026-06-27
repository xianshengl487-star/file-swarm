# FileSwarm Enhanced AgentExecutor - Cross-Model Benchmark Report

**Date**: 2026-06-26 22:30:29

**Models tested**: 11

**Task categories**: 5

**Total combinations**: 55

**Mode**: Dry run (safe, no side effects)


## Summary Matrix

| Model | Pass Rate | system-info | file-ops | browser-ctrl | mouse-sim | mcp-tools |
|-------|-----------|-------------|----------|--------------|-----------|-----------|
| Mimo-v2.5 | 4/5 | FAIL | PASS | PASS | PASS | PASS |
| Mimo-v2.5-Pro | 3/5 | FAIL | PASS | FAIL | PASS | PASS |
| GLM-5.1 | 0/5 | FAIL | FAIL | FAIL | FAIL | FAIL |
| Llama-3.3-70B | 0/5 | FAIL | FAIL | FAIL | FAIL | FAIL |
| DeepSeek-V4-Flash | 0/5 | FAIL | FAIL | FAIL | FAIL | FAIL |
| Qwen3.5-122B | 0/5 | FAIL | FAIL | FAIL | FAIL | FAIL |
| Kimi-K2.6 | 0/5 | FAIL | FAIL | FAIL | FAIL | FAIL |
| Mistral-Large-2 | 0/5 | FAIL | FAIL | FAIL | FAIL | FAIL |
| Nemotron-Super-49B | 0/5 | FAIL | FAIL | FAIL | FAIL | FAIL |
| Gemma-3-12B | 0/5 | FAIL | FAIL | FAIL | FAIL | FAIL |
| GPT-OSS-120B | 0/5 | FAIL | FAIL | FAIL | FAIL | FAIL |

## Token Efficiency

| Model | Avg Output Tokens | Sample Count |
|-------|------------------|--------------|
| Mimo-v2.5 | 1558 | 5 |
| Mimo-v2.5-Pro | 1470 | 3 |

## Per-Category Analysis

### system-info

- **Pass rate**: 0/11
- **Description**: Check system information: list CPU info, memory usage, disk space, and OS version. Generate a summar...
- **Expected action types**: ['shell']
- **Min actions**: 2

- **Failed models**: Mimo-v2.5-Pro, Mimo-v2.5, GLM-5.1, Llama-3.3-70B, DeepSeek-V4-Flash, Qwen3.5-122B, Kimi-K2.6, Mistral-Large-2, Nemotron-Super-49B, Gemma-3-12B, GPT-OSS-120B

### file-ops

- **Pass rate**: 2/11
- **Description**: Create a test directory, write a hello world file, list its contents, then read the file back. Use f...
- **Expected action types**: ['shell', 'mcp_call']
- **Min actions**: 2

- **Most efficient**: Mimo-v2.5 (1368 output tokens)
- **Failed models**: GLM-5.1, Llama-3.3-70B, DeepSeek-V4-Flash, Qwen3.5-122B, Kimi-K2.6, Mistral-Large-2, Nemotron-Super-49B, Gemma-3-12B, GPT-OSS-120B

### browser-ctrl

- **Pass rate**: 1/11
- **Description**: Open browser to https://httpbin.org/get and fetch the page content to see the JSON response. Then ex...
- **Expected action types**: ['browser_open', 'browser_fetch']
- **Min actions**: 1

- **Most efficient**: Mimo-v2.5 (1762 output tokens)
- **Failed models**: Mimo-v2.5-Pro, GLM-5.1, Llama-3.3-70B, DeepSeek-V4-Flash, Qwen3.5-122B, Kimi-K2.6, Mistral-Large-2, Nemotron-Super-49B, Gemma-3-12B, GPT-OSS-120B

### mouse-sim

- **Pass rate**: 2/11
- **Description**: Simulate mouse movement to center of screen (960, 540), take a screenshot, then type 'Hello World' a...
- **Expected action types**: ['mouse_move', 'screenshot', 'key_type', 'key_press']
- **Min actions**: 2

- **Most efficient**: Mimo-v2.5 (1162 output tokens)
- **Failed models**: GLM-5.1, Llama-3.3-70B, DeepSeek-V4-Flash, Qwen3.5-122B, Kimi-K2.6, Mistral-Large-2, Nemotron-Super-49B, Gemma-3-12B, GPT-OSS-120B

### mcp-tools

- **Pass rate**: 2/11
- **Description**: Use MCP tools to: get current datetime, read environment variables, and make an HTTP GET request to ...
- **Expected action types**: ['mcp_call']
- **Min actions**: 2

- **Most efficient**: Mimo-v2.5-Pro (1346 output tokens)
- **Failed models**: GLM-5.1, Llama-3.3-70B, DeepSeek-V4-Flash, Qwen3.5-122B, Kimi-K2.6, Mistral-Large-2, Nemotron-Super-49B, Gemma-3-12B, GPT-OSS-120B

## Recommendations

### Best All-Rounders (3+ categories passed)

- **Mimo-v2.5**: 4/5 categories passed
- **Mimo-v2.5-Pro**: 3/5 categories passed

### Category-Specific Recommendations

- **system-info**: No model passed
- **file-ops**: Best = Mimo-v2.5 (1368 tokens, 17.28s)
- **browser-ctrl**: Best = Mimo-v2.5 (1762 tokens, 21.67s)
- **mouse-sim**: Best = Mimo-v2.5 (1162 tokens, 13.99s)
- **mcp-tools**: Best = Mimo-v2.5-Pro (1346 tokens, 35.23s)

## Error Analysis

| Error Type | Count |
|------------|-------|
| skipped (api_403) | 36 |
| api_error_status_403 | 9 |
| model_timeout | 2 |

## Detailed Results

### Mimo-v2.5-Pro - system-info [FAIL]

- Model ID: `mimo-v2.5-pro`
- Elapsed: 60.04s
- Actions: 0 ()
- Tokens: input=None, output=None
- Error: `model_timeout`

### Mimo-v2.5-Pro - file-ops [PASS]

- Model ID: `mimo-v2.5-pro`
- Elapsed: 53.13s
- Actions: 4 (shell)
- Tokens: input=17, output=1859
- Summary: Executed 4 actions (category=shell):
  [OK] shell: {"type": "shell", "command": "mkdir test_dir"}
    -> [dry-run] would execute
  [OK] shell: {"type": "shell", "command": "echo Hello, World! > test_dir\\hello.txt"}
    -> [dry-run] would execute
  [OK] shell: {"type": "shell", "command": "dir test_

### Mimo-v2.5-Pro - browser-ctrl [FAIL]

- Model ID: `mimo-v2.5-pro`
- Elapsed: 60.0s
- Actions: 0 ()
- Tokens: input=None, output=None
- Error: `model_timeout`

### Mimo-v2.5-Pro - mouse-sim [PASS]

- Model ID: `mimo-v2.5-pro`
- Elapsed: 30.45s
- Actions: 4 (screenshot, mouse_move, key_type, key_press)
- Tokens: input=31, output=1205
- Summary: Executed 4 actions (category=mouse):
  [OK] mouse_move: {"type": "mouse_move", "x": 960, "y": 540, "duration": 0.5}
    -> [dry-run] would execute
  [OK] screenshot: {"type": "screenshot", "save_path": "screenshot.png"}
    -> [dry-run] would execute
  [OK] key_type: {"type": "key_type", "text": "He

### Mimo-v2.5-Pro - mcp-tools [PASS]

- Model ID: `mimo-v2.5-pro`
- Elapsed: 35.23s
- Actions: 3 (mcp_call)
- Tokens: input=64, output=1346
- Summary: Executed 3 actions (category=mixed):
  [OK] mcp_call: {"type": "mcp_call", "tool": "datetime_now", "args": {}}
    -> [dry-run] would execute
  [OK] mcp_call: {"type": "mcp_call", "tool": "env_get", "args": {}}
    -> [dry-run] would execute
  [OK] mcp_call: {"type": "mcp_call", "tool": "http_get", 

### Mimo-v2.5 - system-info [FAIL]

- Model ID: `mimo-v2.5`
- Elapsed: 23.7s
- Actions: 1 (shell)
- Tokens: input=55, output=1848
- Summary: Executed 1 actions (category=mixed):
  [OK] shell: {"type": "shell", "command": "echo === CPU Information === & wmic cpu get name, 
    -> [dry-run] would execute

### Mimo-v2.5 - file-ops [PASS]

- Model ID: `mimo-v2.5`
- Elapsed: 17.28s
- Actions: 4 (shell)
- Tokens: input=17, output=1368
- Summary: Executed 4 actions (category=shell):
  [OK] shell: {"type": "shell", "command": "md test_dir"}
    -> [dry-run] would execute
  [OK] shell: {"type": "shell", "command": "echo Hello World > test_dir\\hello.txt"}
    -> [dry-run] would execute
  [OK] shell: {"type": "shell", "command": "dir test_dir"}

### Mimo-v2.5 - browser-ctrl [PASS]

- Model ID: `mimo-v2.5`
- Elapsed: 21.67s
- Actions: 2 (browser_fetch, browser_open)
- Tokens: input=50, output=1762
- Summary: Executed 2 actions (category=browser):
  [OK] browser_open: {"type": "browser_open", "url": "https://httpbin.org/get"}
    -> [dry-run] would execute
  [OK] browser_fetch: {"type": "browser_fetch", "url": "https://httpbin.org/get"}
    -> [dry-run] would execute

### Mimo-v2.5 - mouse-sim [PASS]

- Model ID: `mimo-v2.5`
- Elapsed: 13.99s
- Actions: 4 (screenshot, mouse_move, key_type, key_press)
- Tokens: input=31, output=1162
- Summary: Executed 4 actions (category=mouse):
  [OK] mouse_move: {"type": "mouse_move", "x": 960, "y": 540, "duration": 0.5}
    -> [dry-run] would execute
  [OK] screenshot: {"type": "screenshot", "save_path": "screenshot.png"}
    -> [dry-run] would execute
  [OK] key_type: {"type": "key_type", "text": "He

### Mimo-v2.5 - mcp-tools [PASS]

- Model ID: `mimo-v2.5`
- Elapsed: 21.71s
- Actions: 4 (mcp_call)
- Tokens: input=64, output=1648
- Summary: Executed 4 actions (category=mixed):
  [OK] mcp_call: {"type": "mcp_call", "tool": "datetime_now", "args": {}}
    -> [dry-run] would execute
  [OK] mcp_call: {"type": "mcp_call", "tool": "env_get", "args": {"key": "PATH"}}
    -> [dry-run] would execute
  [OK] mcp_call: {"type": "mcp_call", "tool":

### GLM-5.1 - system-info [FAIL]

- Model ID: `z-ai/glm-5.1`
- Elapsed: 0.86s
- Actions: 0 ()
- Tokens: input=None, output=None
- Error: `api_error_status_403`

### GLM-5.1 - file-ops [FAIL]

- Model ID: `z-ai/glm-5.1`
- Elapsed: 0s
- Actions: 0 ()
- Tokens: input=None, output=None
- Error: `skipped (api_403)`
- Summary: Skipped due to API 403 on previous task

### GLM-5.1 - browser-ctrl [FAIL]

- Model ID: `z-ai/glm-5.1`
- Elapsed: 0s
- Actions: 0 ()
- Tokens: input=None, output=None
- Error: `skipped (api_403)`
- Summary: Skipped due to API 403 on previous task

### GLM-5.1 - mouse-sim [FAIL]

- Model ID: `z-ai/glm-5.1`
- Elapsed: 0s
- Actions: 0 ()
- Tokens: input=None, output=None
- Error: `skipped (api_403)`
- Summary: Skipped due to API 403 on previous task

### GLM-5.1 - mcp-tools [FAIL]

- Model ID: `z-ai/glm-5.1`
- Elapsed: 0s
- Actions: 0 ()
- Tokens: input=None, output=None
- Error: `skipped (api_403)`
- Summary: Skipped due to API 403 on previous task

### Llama-3.3-70B - system-info [FAIL]

- Model ID: `meta/llama-3.3-70b-instruct`
- Elapsed: 0.54s
- Actions: 0 ()
- Tokens: input=None, output=None
- Error: `api_error_status_403`

### Llama-3.3-70B - file-ops [FAIL]

- Model ID: `meta/llama-3.3-70b-instruct`
- Elapsed: 0s
- Actions: 0 ()
- Tokens: input=None, output=None
- Error: `skipped (api_403)`
- Summary: Skipped due to API 403 on previous task

### Llama-3.3-70B - browser-ctrl [FAIL]

- Model ID: `meta/llama-3.3-70b-instruct`
- Elapsed: 0s
- Actions: 0 ()
- Tokens: input=None, output=None
- Error: `skipped (api_403)`
- Summary: Skipped due to API 403 on previous task

### Llama-3.3-70B - mouse-sim [FAIL]

- Model ID: `meta/llama-3.3-70b-instruct`
- Elapsed: 0s
- Actions: 0 ()
- Tokens: input=None, output=None
- Error: `skipped (api_403)`
- Summary: Skipped due to API 403 on previous task

### Llama-3.3-70B - mcp-tools [FAIL]

- Model ID: `meta/llama-3.3-70b-instruct`
- Elapsed: 0s
- Actions: 0 ()
- Tokens: input=None, output=None
- Error: `skipped (api_403)`
- Summary: Skipped due to API 403 on previous task

### DeepSeek-V4-Flash - system-info [FAIL]

- Model ID: `deepseek-ai/deepseek-v4-flash`
- Elapsed: 0.53s
- Actions: 0 ()
- Tokens: input=None, output=None
- Error: `api_error_status_403`

### DeepSeek-V4-Flash - file-ops [FAIL]

- Model ID: `deepseek-ai/deepseek-v4-flash`
- Elapsed: 0s
- Actions: 0 ()
- Tokens: input=None, output=None
- Error: `skipped (api_403)`
- Summary: Skipped due to API 403 on previous task

### DeepSeek-V4-Flash - browser-ctrl [FAIL]

- Model ID: `deepseek-ai/deepseek-v4-flash`
- Elapsed: 0s
- Actions: 0 ()
- Tokens: input=None, output=None
- Error: `skipped (api_403)`
- Summary: Skipped due to API 403 on previous task

### DeepSeek-V4-Flash - mouse-sim [FAIL]

- Model ID: `deepseek-ai/deepseek-v4-flash`
- Elapsed: 0s
- Actions: 0 ()
- Tokens: input=None, output=None
- Error: `skipped (api_403)`
- Summary: Skipped due to API 403 on previous task

### DeepSeek-V4-Flash - mcp-tools [FAIL]

- Model ID: `deepseek-ai/deepseek-v4-flash`
- Elapsed: 0s
- Actions: 0 ()
- Tokens: input=None, output=None
- Error: `skipped (api_403)`
- Summary: Skipped due to API 403 on previous task

### Qwen3.5-122B - system-info [FAIL]

- Model ID: `qwen/qwen3.5-122b-a10b`
- Elapsed: 0.56s
- Actions: 0 ()
- Tokens: input=None, output=None
- Error: `api_error_status_403`

### Qwen3.5-122B - file-ops [FAIL]

- Model ID: `qwen/qwen3.5-122b-a10b`
- Elapsed: 0s
- Actions: 0 ()
- Tokens: input=None, output=None
- Error: `skipped (api_403)`
- Summary: Skipped due to API 403 on previous task

### Qwen3.5-122B - browser-ctrl [FAIL]

- Model ID: `qwen/qwen3.5-122b-a10b`
- Elapsed: 0s
- Actions: 0 ()
- Tokens: input=None, output=None
- Error: `skipped (api_403)`
- Summary: Skipped due to API 403 on previous task

### Qwen3.5-122B - mouse-sim [FAIL]

- Model ID: `qwen/qwen3.5-122b-a10b`
- Elapsed: 0s
- Actions: 0 ()
- Tokens: input=None, output=None
- Error: `skipped (api_403)`
- Summary: Skipped due to API 403 on previous task

### Qwen3.5-122B - mcp-tools [FAIL]

- Model ID: `qwen/qwen3.5-122b-a10b`
- Elapsed: 0s
- Actions: 0 ()
- Tokens: input=None, output=None
- Error: `skipped (api_403)`
- Summary: Skipped due to API 403 on previous task

### Kimi-K2.6 - system-info [FAIL]

- Model ID: `moonshotai/kimi-k2.6`
- Elapsed: 0.55s
- Actions: 0 ()
- Tokens: input=None, output=None
- Error: `api_error_status_403`

### Kimi-K2.6 - file-ops [FAIL]

- Model ID: `moonshotai/kimi-k2.6`
- Elapsed: 0s
- Actions: 0 ()
- Tokens: input=None, output=None
- Error: `skipped (api_403)`
- Summary: Skipped due to API 403 on previous task

### Kimi-K2.6 - browser-ctrl [FAIL]

- Model ID: `moonshotai/kimi-k2.6`
- Elapsed: 0s
- Actions: 0 ()
- Tokens: input=None, output=None
- Error: `skipped (api_403)`
- Summary: Skipped due to API 403 on previous task

### Kimi-K2.6 - mouse-sim [FAIL]

- Model ID: `moonshotai/kimi-k2.6`
- Elapsed: 0s
- Actions: 0 ()
- Tokens: input=None, output=None
- Error: `skipped (api_403)`
- Summary: Skipped due to API 403 on previous task

### Kimi-K2.6 - mcp-tools [FAIL]

- Model ID: `moonshotai/kimi-k2.6`
- Elapsed: 0s
- Actions: 0 ()
- Tokens: input=None, output=None
- Error: `skipped (api_403)`
- Summary: Skipped due to API 403 on previous task

### Mistral-Large-2 - system-info [FAIL]

- Model ID: `mistralai/mistral-large-2-instruct`
- Elapsed: 0.54s
- Actions: 0 ()
- Tokens: input=None, output=None
- Error: `api_error_status_403`

### Mistral-Large-2 - file-ops [FAIL]

- Model ID: `mistralai/mistral-large-2-instruct`
- Elapsed: 0s
- Actions: 0 ()
- Tokens: input=None, output=None
- Error: `skipped (api_403)`
- Summary: Skipped due to API 403 on previous task

### Mistral-Large-2 - browser-ctrl [FAIL]

- Model ID: `mistralai/mistral-large-2-instruct`
- Elapsed: 0s
- Actions: 0 ()
- Tokens: input=None, output=None
- Error: `skipped (api_403)`
- Summary: Skipped due to API 403 on previous task

### Mistral-Large-2 - mouse-sim [FAIL]

- Model ID: `mistralai/mistral-large-2-instruct`
- Elapsed: 0s
- Actions: 0 ()
- Tokens: input=None, output=None
- Error: `skipped (api_403)`
- Summary: Skipped due to API 403 on previous task

### Mistral-Large-2 - mcp-tools [FAIL]

- Model ID: `mistralai/mistral-large-2-instruct`
- Elapsed: 0s
- Actions: 0 ()
- Tokens: input=None, output=None
- Error: `skipped (api_403)`
- Summary: Skipped due to API 403 on previous task

### Nemotron-Super-49B - system-info [FAIL]

- Model ID: `nvidia/llama-3.3-nemotron-super-49b-v1.5`
- Elapsed: 0.54s
- Actions: 0 ()
- Tokens: input=None, output=None
- Error: `api_error_status_403`

### Nemotron-Super-49B - file-ops [FAIL]

- Model ID: `nvidia/llama-3.3-nemotron-super-49b-v1.5`
- Elapsed: 0s
- Actions: 0 ()
- Tokens: input=None, output=None
- Error: `skipped (api_403)`
- Summary: Skipped due to API 403 on previous task

### Nemotron-Super-49B - browser-ctrl [FAIL]

- Model ID: `nvidia/llama-3.3-nemotron-super-49b-v1.5`
- Elapsed: 0s
- Actions: 0 ()
- Tokens: input=None, output=None
- Error: `skipped (api_403)`
- Summary: Skipped due to API 403 on previous task

### Nemotron-Super-49B - mouse-sim [FAIL]

- Model ID: `nvidia/llama-3.3-nemotron-super-49b-v1.5`
- Elapsed: 0s
- Actions: 0 ()
- Tokens: input=None, output=None
- Error: `skipped (api_403)`
- Summary: Skipped due to API 403 on previous task

### Nemotron-Super-49B - mcp-tools [FAIL]

- Model ID: `nvidia/llama-3.3-nemotron-super-49b-v1.5`
- Elapsed: 0s
- Actions: 0 ()
- Tokens: input=None, output=None
- Error: `skipped (api_403)`
- Summary: Skipped due to API 403 on previous task

### Gemma-3-12B - system-info [FAIL]

- Model ID: `google/gemma-3-12b-it`
- Elapsed: 0.55s
- Actions: 0 ()
- Tokens: input=None, output=None
- Error: `api_error_status_403`

### Gemma-3-12B - file-ops [FAIL]

- Model ID: `google/gemma-3-12b-it`
- Elapsed: 0s
- Actions: 0 ()
- Tokens: input=None, output=None
- Error: `skipped (api_403)`
- Summary: Skipped due to API 403 on previous task

### Gemma-3-12B - browser-ctrl [FAIL]

- Model ID: `google/gemma-3-12b-it`
- Elapsed: 0s
- Actions: 0 ()
- Tokens: input=None, output=None
- Error: `skipped (api_403)`
- Summary: Skipped due to API 403 on previous task

### Gemma-3-12B - mouse-sim [FAIL]

- Model ID: `google/gemma-3-12b-it`
- Elapsed: 0s
- Actions: 0 ()
- Tokens: input=None, output=None
- Error: `skipped (api_403)`
- Summary: Skipped due to API 403 on previous task

### Gemma-3-12B - mcp-tools [FAIL]

- Model ID: `google/gemma-3-12b-it`
- Elapsed: 0s
- Actions: 0 ()
- Tokens: input=None, output=None
- Error: `skipped (api_403)`
- Summary: Skipped due to API 403 on previous task

### GPT-OSS-120B - system-info [FAIL]

- Model ID: `openai/gpt-oss-120b`
- Elapsed: 0.54s
- Actions: 0 ()
- Tokens: input=None, output=None
- Error: `api_error_status_403`

### GPT-OSS-120B - file-ops [FAIL]

- Model ID: `openai/gpt-oss-120b`
- Elapsed: 0s
- Actions: 0 ()
- Tokens: input=None, output=None
- Error: `skipped (api_403)`
- Summary: Skipped due to API 403 on previous task

### GPT-OSS-120B - browser-ctrl [FAIL]

- Model ID: `openai/gpt-oss-120b`
- Elapsed: 0s
- Actions: 0 ()
- Tokens: input=None, output=None
- Error: `skipped (api_403)`
- Summary: Skipped due to API 403 on previous task

### GPT-OSS-120B - mouse-sim [FAIL]

- Model ID: `openai/gpt-oss-120b`
- Elapsed: 0s
- Actions: 0 ()
- Tokens: input=None, output=None
- Error: `skipped (api_403)`
- Summary: Skipped due to API 403 on previous task

### GPT-OSS-120B - mcp-tools [FAIL]

- Model ID: `openai/gpt-oss-120b`
- Elapsed: 0s
- Actions: 0 ()
- Tokens: input=None, output=None
- Error: `skipped (api_403)`
- Summary: Skipped due to API 403 on previous task

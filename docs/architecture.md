# Architecture

`file-swarm` uses a lightweight control plane that coordinates OpenAI-compatible workers without letting those workers write files directly.

The architecture is intentionally simple for the scaffold stage:

- a slot registry stores provider connectivity
- the dispatcher binds tasks to workers
- patch guard checks proposed diffs
- patch merger and validator handle the final application path
- transcripts are stored on disk for inspection

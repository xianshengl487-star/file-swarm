# Worker Types

## Stateless Patch Worker

The default worker type.
It receives a task and returns a unified diff patch.

## Model Worker

A runtime worker bound to one task, one slot, and one model.

## OpenAI-compatible Worker

Any worker backed by an OpenAI-compatible Chat Completions API.

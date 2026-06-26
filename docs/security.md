# Security

Security in `file-swarm` is designed around containment:

- avoid secret logging
- avoid unrestricted file writes
- avoid unchecked patch application
- avoid dependency drift in the scaffold stage

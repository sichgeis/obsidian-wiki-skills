# Fundus core boundaries

The public compatibility entrypoints remain `scripts/fundus.py` and
`scripts/fundus_mcp.py`. They contain no domain behavior; both delegate into this
package.

Current modules:

- `runtime.py` owns the local application core: configuration and value objects,
  path/frontmatter/revision primitives, repository and index behavior, locking and
  journals, operations, administrative workflows, and CLI argument dispatch.
- `mcp_server.py` owns only MCP contracts, schema validation, JSON-RPC lifecycle,
  and mapping typed tool calls to the runtime operations.

`runtime.py` deliberately remains one compatibility module for the 0.2.0 release.
Its internal sections form the next safe extraction seams: configuration/models,
paths, frontmatter, search/repository, locking/revisions, operations, and admin.
New transport behavior belongs outside `runtime.py`; future extraction must preserve
the `fundus.py` import facade and run the complete contract suite after each move.

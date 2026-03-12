---
description: "Build, query, and manage intention-driven hypergraphs — RAG replacement with cross-document discovery"
---

# Intention Engine Skill

You have access to the intention-engine — a hypergraph that replaces traditional RAG.
Instead of vector-store similarity search, it uses intention-driven two-phase search
where each query discovers and persists new cross-document connections.
Graphs auto-persist to `~/.intention-engine/<name>/`.

## RAG Commands (primary use)

```bash
# Ingest files or directories — creates document, section, and chunk nodes
python -m intention_engine ingest <graph> <path> [--chunk-size 512]
python -m intention_engine ingest <graph> ./docs/ --chunk-size 1024
python -m intention_engine ingest-text <graph> "raw text content" --name "label"

# Retrieve context for LLM consumption
python -m intention_engine retrieve <graph> "<query>" --top 10 --format text
python -m intention_engine retrieve <graph> "<query>" --format xml
python -m intention_engine retrieve <graph> "<query>" --no-explore  # exploit only

# Inspect ingested content
python -m intention_engine documents <graph>
python -m intention_engine stats <graph>
```

## Low-Level Commands (manual graph building)

```bash
python -m intention_engine graphs                          # List all graphs
python -m intention_engine init <name>                      # Create/load graph
python -m intention_engine add-node <graph> <id> "<desc>" --ontology <type>
python -m intention_engine add-nodes <graph> --json '<json_array>'
python -m intention_engine add-edge <graph> "<label>" <id1> <id2> [id3...]
python -m intention_engine search <graph> "<intention>" --top 20 [--valid-at <timestamp>]
python -m intention_engine list-nodes <graph> [--ontology <type>]
python -m intention_engine list-edges <graph> [--source minted]
python -m intention_engine explain <graph> <edge_id>
python -m intention_engine decay <graph> --threshold 0.01
```

## Temporal Commands

```bash
# Show what changed between two timestamps (nodes added/removed, edges minted/closed/reinforced, searches)
python -m intention_engine temporal-diff <graph> <t1> <t2>

# Show the full intention history for a hyperedge — every intention that touched it
python -m intention_engine edge-history <graph> <edge_id>

# Show graph stats (nodes, edges, minted vs manual) as they were at a point in time
python -m intention_engine graph-at <graph> <timestamp>

# Search with temporal restriction — only exploit edges valid at the given timestamp
python -m intention_engine search <graph> "<intention>" --valid-at <unix_epoch_seconds>
```

## How to Use as RAG Replacement

1. **Ingest**: `python -m intention_engine ingest <graph> <path>` — chunks files with structural awareness (markdown headings, code functions, paragraphs), creates multi-level nodes (document → section → chunk), extracts relationships as hyperedges
2. **Retrieve**: `python -m intention_engine retrieve <graph> "<query>"` — returns formatted context ready for LLM. Each query discovers cross-document connections that persist for future queries.
3. **Iterate**: The graph gets smarter with use. A query about "authentication security" retrieves auth chunks from auth.md AND security chunks from database.md, minting a hyperedge that connects them permanently.

## Context Formats

- `--format text`: Source-attributed plain text with `[filename:lines (section)]` headers
- `--format markdown`: Markdown with `### Source N` headers
- `--format xml`: `<context><chunk source="..." section="..." lines="...">` tags

## Tips

- Ingest entire directories — the engine handles file type detection and exclusion of __pycache__/node_modules/.git
- Use descriptive ontology tags for manual nodes to enable cross-ontology discovery
- First query on a topic always EXPLOREs (discovers new structure). Subsequent related queries EXPLOIT the discovered edges (faster, more accurate).
- Use `--no-explore` when you want fast retrieval without discovering new connections

$ARGUMENTS

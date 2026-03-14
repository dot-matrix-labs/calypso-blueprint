#!/usr/bin/env python3
"""Generate rules/graph.yaml from all rule YAML files."""
import yaml
import glob
import os

RULES_DIR = "/home/lucas/calypso-blueprint/rules"

# Collect all rule files
blueprint_files = sorted(glob.glob(f"{RULES_DIR}/blueprints/*.yaml"))
impl_files = sorted(glob.glob(f"{RULES_DIR}/implementations/*.yaml"))
all_files = blueprint_files + impl_files

# Parse all files
nodes = {}  # hash -> [number, name, type, domain, relative_path]
edges = []  # [source_hash, rel, target_hash]
files_map = {}  # key -> relative path

for fpath in all_files:
    with open(fpath) as fh:
        data = yaml.safe_load(fh)

    meta = data.get("meta", {})
    domain = meta.get("domain", "")

    # Determine relative path without extension
    rel_path = os.path.relpath(fpath, RULES_DIR)
    rel_path_no_ext = os.path.splitext(rel_path)[0]

    # Build files map key
    basename = os.path.splitext(os.path.basename(fpath))[0]
    if "implementations" in fpath:
        # e.g. arch-ts -> IMPL-ARCH
        base = basename.replace("-ts", "").upper()
        files_key = f"IMPL-{base}"
    else:
        files_key = basename.upper()

    files_map[files_key] = f"rules/{rel_path}"

    for rule in data.get("rules", []):
        h = rule.get("hash")
        if not h:
            continue
        nodes[h] = [
            rule.get("number", ""),
            rule.get("name", ""),
            rule.get("type", ""),
            domain,
            rel_path_no_ext,
        ]

        for link in rule.get("links", []) or []:
            if isinstance(link, dict):
                target = link.get("target")
                rel = link.get("rel")
                if target and rel:
                    edges.append([h, rel, target])

# Filter edges to only valid hashes
valid_hashes = set(nodes.keys())
edges = [e for e in edges if e[0] in valid_hashes and e[2] in valid_hashes]

# Build output
graph = {
    "corpus_version": 1,
    "generated": "2026-03-14T00:00:00Z",
    "rule_count": len(nodes),
    "nodes": {h: v for h, v in nodes.items()},
    "edges": edges,
    "files": files_map,
}

with open(f"{RULES_DIR}/graph.yaml", "w") as fh:
    # Custom dump for readability matching existing format
    fh.write(f"corpus_version: {graph['corpus_version']}\n")
    fh.write(f"generated: '{graph['generated']}'\n")
    fh.write(f"rule_count: {graph['rule_count']}\n")
    fh.write("nodes:\n")
    for h, v in nodes.items():
        fh.write(f"  {h}: [{v[0]}, {v[1]}, {v[2]}, {v[3]}, {v[4]}]\n")
    fh.write("edges:\n")
    for e in edges:
        fh.write(f"- [{e[0]}, {e[1]}, {e[2]}]\n")
    fh.write("files: {")
    items = list(files_map.items())
    for i, (k, v) in enumerate(items):
        sep = ", " if i > 0 else ""
        fh.write(f"{sep}{k}: {v}")
    fh.write("}\n")

print(f"Generated graph.yaml with {len(nodes)} nodes and {len(edges)} edges.")

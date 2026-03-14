#!/usr/bin/env python3
"""Validate the YAML rule system."""
import yaml
import glob
import sys
from collections import defaultdict

RULES_DIR = "/home/lucas/calypso-blueprint/rules"
passed = []
failed = []

def ok(msg):
    passed.append(msg)
    print(f"  PASS: {msg}")

def fail(msg):
    failed.append(msg)
    print(f"  FAIL: {msg}")

# 1. Parse all YAML files
print("=== 1. YAML Parsing ===")
all_files = sorted(
    glob.glob(f"{RULES_DIR}/blueprints/*.yaml") +
    glob.glob(f"{RULES_DIR}/implementations/*.yaml")
)
file_data = {}
parse_errors = []
for f in all_files:
    try:
        with open(f) as fh:
            file_data[f] = yaml.safe_load(fh)
    except Exception as e:
        parse_errors.append((f, str(e)))

if parse_errors:
    fail(f"{len(parse_errors)} files failed to parse")
    for f, e in parse_errors:
        print(f"    {f}: {e}")
else:
    ok(f"All {len(all_files)} YAML files parse correctly")

# Collect all rules
all_rules = []  # (file, rule)
all_hashes = {}  # hash -> [(file, number)]
number_to_hash = {}  # number -> hash
for f, data in file_data.items():
    for rule in data.get("rules", []):
        all_rules.append((f, rule))
        h = rule.get("hash")
        num = rule.get("number")
        if h:
            all_hashes.setdefault(h, []).append((f, num))
        if num and h:
            number_to_hash[num] = h

# 2. Duplicate hashes
print("\n=== 2. Duplicate Hashes ===")
dup_hashes = {h: locs for h, locs in all_hashes.items() if len(locs) > 1}
if dup_hashes:
    fail(f"{len(dup_hashes)} duplicate hashes found")
    for h, locs in list(dup_hashes.items())[:20]:
        print(f"    {h}: {locs}")
else:
    ok(f"No duplicate hashes across {len(all_hashes)} rules")

# 3. Duplicate numbers within domain-category
print("\n=== 3. Duplicate Numbers per Domain-Category ===")
numbers_seen = defaultdict(list)
for f, rule in all_rules:
    num = rule.get("number", "")
    # Domain-category = prefix before final numeric segment (e.g. ARCH-T from ARCH-T-001)
    parts = num.rsplit("-", 1)
    prefix = parts[0] if len(parts) == 2 else num
    numbers_seen[(prefix, num)].append(f)

dup_numbers = {k: v for k, v in numbers_seen.items() if len(v) > 1}
if dup_numbers:
    fail(f"{len(dup_numbers)} duplicate numbers found")
    for (prefix, num), files in list(dup_numbers.items())[:20]:
        print(f"    {num} in {[f.split('/')[-1] for f in files]}")
else:
    ok("No duplicate numbers within any domain-category pair")

# 4. All edge targets exist
print("\n=== 4. Edge Target Validation ===")
valid_hashes = set(all_hashes.keys())
valid_numbers = set(number_to_hash.keys())
broken_edges = []
for f, rule in all_rules:
    for link in rule.get("links", []) or []:
        if isinstance(link, dict):
            target = link.get("target")
            if target and target not in valid_hashes:
                broken_edges.append((rule.get("number"), target, f, "hash"))
        elif isinstance(link, str):
            if link not in valid_numbers:
                broken_edges.append((rule.get("number"), link, f, "number"))

if broken_edges:
    fail(f"{len(broken_edges)} broken edge references")
    for num, target, f, kind in broken_edges[:20]:
        print(f"    {num} -> {target} ({kind} ref, in {f.split('/')[-1]})")
else:
    ok("All edge targets resolve to existing nodes")

# 5. Graph node count matches
print("\n=== 5. Graph Node Count ===")
with open(f"{RULES_DIR}/graph.yaml") as fh:
    graph = yaml.safe_load(fh)

declared_count = graph.get("rule_count", 0)
actual_count = len(all_rules)
graph_node_count = len(graph.get("nodes", {}))

if declared_count == actual_count:
    ok(f"rule_count ({declared_count}) matches actual rule count")
else:
    fail(f"rule_count is {declared_count} but actual rules = {actual_count}")

if graph_node_count == actual_count:
    ok(f"graph nodes ({graph_node_count}) matches actual rule count")
else:
    fail(f"graph has {graph_node_count} nodes but source files have {actual_count} rules")

# 6. Graph <-> source file consistency
print("\n=== 6. Graph <-> Source Consistency ===")
graph_hashes = set(graph.get("nodes", {}).keys())

in_graph_not_source = graph_hashes - valid_hashes
in_source_not_graph = valid_hashes - graph_hashes

if in_graph_not_source:
    fail(f"{len(in_graph_not_source)} nodes in graph.yaml but not in source files")
    for h in sorted(in_graph_not_source)[:20]:
        node = graph["nodes"][h]
        print(f"    {h}: {node[0]}")
else:
    ok("All graph nodes exist in source files")

if in_source_not_graph:
    fail(f"{len(in_source_not_graph)} nodes in source files but not in graph.yaml")
    for h in sorted(in_source_not_graph)[:20]:
        locs = all_hashes[h]
        print(f"    {h}: {locs[0][1]} (in {locs[0][0].split('/')[-1]})")
else:
    ok("All source nodes exist in graph.yaml")

# Summary
print("\n" + "=" * 60)
print(f"PASSED: {len(passed)}")
print(f"FAILED: {len(failed)}")
if failed:
    print("\nFailures:")
    for f in failed:
        print(f"  - {f}")
    sys.exit(1)
else:
    print("\nAll checks passed!")

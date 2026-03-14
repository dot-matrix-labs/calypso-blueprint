#!/usr/bin/env python3
"""Generate a changelog entry by diffing rule YAML files against a base branch.

Usage:
    python generate_changelog.py [base_branch]

Defaults to 'main' if no branch is specified. Compares the current working tree
against the base branch to detect added, removed, deprecated, and modified rules.
Also enforces the append-only numbering invariant: no rule number that existed in
the base branch may be reused with a different hash.

Outputs:
    - Prints the changelog entry to stdout
    - Appends it to rules/changelog.yaml
    - Exits non-zero if number reuse is detected
"""
import glob
import os
import subprocess
import sys
import yaml
from datetime import date


RULES_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "rules")
CHANGELOG_PATH = os.path.join(RULES_DIR, "changelog.yaml")
RULE_GLOBS = ["blueprints/*.yaml", "implementations/*.yaml"]


def parse_rules_from_text(text: str) -> dict:
    """Parse YAML text and return {hash: rule_dict} for all rules."""
    try:
        data = yaml.safe_load(text)
    except yaml.YAMLError:
        return {}
    if not data or "rules" not in data:
        return {}
    rules = {}
    for rule in data.get("rules", []):
        h = rule.get("hash")
        if h:
            rules[h] = rule
    return rules


def get_base_rules(base_branch: str) -> dict:
    """Read all rule files from the base branch via git show."""
    rules = {}  # hash -> rule_dict
    numbers = {}  # number -> hash

    for pattern in RULE_GLOBS:
        # List matching files in the base branch
        try:
            ls_output = subprocess.check_output(
                ["git", "ls-tree", "-r", "--name-only", base_branch, f"rules/{pattern}"],
                stderr=subprocess.DEVNULL,
                text=True,
            ).strip()
        except subprocess.CalledProcessError:
            continue

        for fpath in ls_output.splitlines():
            if not fpath:
                continue
            try:
                content = subprocess.check_output(
                    ["git", "show", f"{base_branch}:{fpath}"],
                    stderr=subprocess.DEVNULL,
                    text=True,
                )
            except subprocess.CalledProcessError:
                continue
            file_rules = parse_rules_from_text(content)
            for h, rule in file_rules.items():
                rules[h] = rule
                num = rule.get("number")
                if num:
                    numbers[num] = h

    return rules, numbers


def get_current_rules() -> dict:
    """Read all rule files from the current working tree."""
    rules = {}
    numbers = {}

    for pattern in RULE_GLOBS:
        for fpath in sorted(glob.glob(os.path.join(RULES_DIR, pattern))):
            with open(fpath) as fh:
                file_rules = parse_rules_from_text(fh.read())
            for h, rule in file_rules.items():
                rules[h] = rule
                num = rule.get("number")
                if num:
                    numbers[num] = h

    return rules, numbers


def diff_rules(base_rules, base_numbers, current_rules, current_numbers):
    """Compute the diff between base and current rule sets."""
    base_hashes = set(base_rules.keys())
    current_hashes = set(current_rules.keys())

    added_hashes = current_hashes - base_hashes
    removed_hashes = base_hashes - current_hashes
    common_hashes = base_hashes & current_hashes

    added = []
    for h in sorted(added_hashes, key=lambda h: current_rules[h].get("number", "")):
        rule = current_rules[h]
        added.append({
            "action": "added",
            "number": rule.get("number"),
            "name": rule.get("name"),
            "hash": h,
        })

    removed = []
    for h in sorted(removed_hashes, key=lambda h: base_rules[h].get("number", "")):
        rule = base_rules[h]
        removed.append({
            "action": "removed",
            "number": rule.get("number"),
            "name": rule.get("name"),
            "hash": h,
        })

    modified = []
    newly_deprecated = []
    for h in sorted(common_hashes, key=lambda h: current_rules[h].get("number", "")):
        base = base_rules[h]
        curr = current_rules[h]

        # Check for newly deprecated
        if curr.get("deprecated") and not base.get("deprecated"):
            newly_deprecated.append({
                "action": "deprecated",
                "number": curr.get("number"),
                "name": curr.get("name"),
                "hash": h,
                "reason": curr.get("deprecated_reason", ""),
            })
            continue

        # Check for description or link changes
        changes = []
        if base.get("description", "").strip() != curr.get("description", "").strip():
            changes.append("description")
        if base.get("links") != curr.get("links"):
            changes.append("links")
        if base.get("name") != curr.get("name"):
            changes.append("name")
        if base.get("type") != curr.get("type"):
            changes.append("type")

        if changes:
            modified.append({
                "action": "modified",
                "number": curr.get("number"),
                "name": curr.get("name"),
                "hash": h,
                "fields": changes,
            })

    # Check for number reuse (append-only invariant)
    reused = []
    for num, curr_hash in current_numbers.items():
        if num in base_numbers and base_numbers[num] != curr_hash:
            reused.append({
                "number": num,
                "old_hash": base_numbers[num],
                "new_hash": curr_hash,
            })

    return added, removed, modified, newly_deprecated, reused


def next_version(changelog_path: str) -> int:
    """Read changelog.yaml and return the next version number."""
    if not os.path.exists(changelog_path):
        return 1
    with open(changelog_path) as fh:
        data = yaml.safe_load(fh)
    if not data or "entries" not in data:
        return 1
    versions = [e.get("version", 0) for e in data["entries"]]
    return max(versions) + 1 if versions else 1


def format_summary(added, removed, modified, newly_deprecated):
    """Build a human-readable summary line."""
    parts = []
    if added:
        parts.append(f"{len(added)} added")
    if removed:
        parts.append(f"{len(removed)} removed")
    if modified:
        parts.append(f"{len(modified)} modified")
    if newly_deprecated:
        parts.append(f"{len(newly_deprecated)} deprecated")
    return ", ".join(parts) if parts else "no changes"


def main():
    base_branch = sys.argv[1] if len(sys.argv) > 1 else "main"

    print(f"Diffing rules against '{base_branch}'...")
    base_rules, base_numbers = get_base_rules(base_branch)
    current_rules, current_numbers = get_current_rules()

    if not base_rules:
        print(f"No rules found in '{base_branch}'. This may be the initial import.")

    added, removed, modified, newly_deprecated, reused = diff_rules(
        base_rules, base_numbers, current_rules, current_numbers
    )

    # Report number reuse violations
    if reused:
        print("\n!!! NUMBER REUSE DETECTED !!!")
        print("The following rule numbers were reused with different hashes.")
        print("This violates the append-only numbering invariant.\n")
        for r in reused:
            print(f"  {r['number']}: was {r['old_hash']}, now {r['new_hash']}")
        print(f"\n{len(reused)} number(s) reused. Fix before merging.")
        sys.exit(1)

    # Print summary
    summary = format_summary(added, removed, modified, newly_deprecated)
    print(f"\nChanges: {summary}")
    print(f"  Base rules:    {len(base_rules)}")
    print(f"  Current rules: {len(current_rules)}")

    if added:
        print(f"\n  Added ({len(added)}):")
        for a in added:
            print(f"    + {a['number']} ({a['name']})")

    if removed:
        print(f"\n  Removed ({len(removed)}):")
        for r in removed:
            print(f"    - {r['number']} ({r['name']})")

    if newly_deprecated:
        print(f"\n  Deprecated ({len(newly_deprecated)}):")
        for d in newly_deprecated:
            reason = f" — {d['reason']}" if d['reason'] else ""
            print(f"    ~ {d['number']} ({d['name']}){reason}")

    if modified:
        print(f"\n  Modified ({len(modified)}):")
        for m in modified:
            print(f"    * {m['number']} ({m['name']}) [{', '.join(m['fields'])}]")

    if not any([added, removed, modified, newly_deprecated]):
        print("\nNo rule changes detected.")
        return

    # Build changelog entry
    version = next_version(CHANGELOG_PATH)
    changes = []
    if added:
        changes.append({"action": "added", "summary": f"{len(added)} rules added", "rules": [a['number'] for a in added]})
    if removed:
        changes.append({"action": "removed", "summary": f"{len(removed)} rules removed", "rules": [r['number'] for r in removed]})
    if modified:
        changes.append({"action": "modified", "summary": f"{len(modified)} rules modified", "rules": [m['number'] for m in modified]})
    if newly_deprecated:
        changes.append({"action": "deprecated", "summary": f"{len(newly_deprecated)} rules deprecated", "rules": [d['number'] for d in newly_deprecated]})

    entry = {
        "version": version,
        "date": str(date.today()),
        "changes": changes,
    }

    # Append to changelog
    if os.path.exists(CHANGELOG_PATH):
        with open(CHANGELOG_PATH) as fh:
            changelog = yaml.safe_load(fh)
    else:
        changelog = {"entries": []}

    if not changelog or "entries" not in changelog:
        changelog = {"entries": []}

    changelog["entries"].append(entry)

    with open(CHANGELOG_PATH, "w") as fh:
        yaml.dump(changelog, fh, default_flow_style=False, sort_keys=False, allow_unicode=True)

    print(f"\nChangelog entry v{version} appended to {CHANGELOG_PATH}")


if __name__ == "__main__":
    main()

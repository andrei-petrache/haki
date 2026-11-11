#!/usr/bin/env python3
"""Decide whether a pull request may merge by itself once CI is green.

Run by .github/workflows/automerge.yml from main's copy, on pull_request_target,
with the pull request only as data: three JSON files as the REST API returns
them (pulls/N, pulls/N/commits, pulls/N/files). Nothing from the pull request
is checked out or run.

Two kinds are eligible, everything else is left to a person:

- deps: Dependabot's own pull request for pip, npm, Docker base images (patch
  only) or compose, minor or patch only. GitHub Actions bumps are never
  eligible: they change the workflows. The commit metadata says minor or
  patch, and the manifests' own diff agrees (the metadata can go stale when
  Dependabot rebases).
- docs: a pull request by Andrei that changes files under docs/ only.

Usage: check-automerge.py <pr.json> <commits.json> <files.json>
Prints "eligible deps <ecosystem>", "eligible docs" or "not eligible: ..."
and exits 0, 1 or 2 (unreadable input).
"""

import json
import re
import sys

REPO = "andrei-petrache/haki"
DEPENDABOT = "dependabot[bot]"
TAG_BOT = "haki-tag-bot[bot]"
DOCS_AUTHOR = "andrei-petrache"
# The files API returns at most 100 per page; a longer list is not judged
MAX_FILES = 99

# Per ecosystem (the second part of Dependabot's branch name): the files it
# may change, and the update types it may bring
ECOSYSTEMS = {
    "pip": {
        "files": {
            "backend/requirements.in",
            "backend/requirements-dev.in",
            "backend/requirements.txt",
            "backend/requirements-dev.txt",
        },
        "types": {"patch", "minor"},
    },
    "npm_and_yarn": {
        "files": {"frontend/package.json", "frontend/package-lock.json"},
        "types": {"patch", "minor"},
    },
    # A minor bump of a base image tag can be a big change: patches only,
    # as the docker-patch group in .github/dependabot.yml
    "docker": {
        "files": {"backend/Dockerfile", "frontend/Dockerfile"},
        "types": {"patch"},
    },
    "docker_compose": {"files": {"compose.yaml"}, "types": {"patch", "minor"}},
}

# Lines of the manifests that name a version, as they appear in a diff
VERSION_LINES = {
    "backend/requirements.in": re.compile(
        r"^[-+]([A-Za-z0-9_.-]+)(?:\[[^\]]*\])?==([0-9][^\s#;]*)"
    ),
    "backend/requirements-dev.in": re.compile(
        r"^[-+]([A-Za-z0-9_.-]+)(?:\[[^\]]*\])?==([0-9][^\s#;]*)"
    ),
    "frontend/package.json": re.compile(r'^[-+]\s+"([^"]+)":\s*"[~^]?([0-9][^"]*)"'),
    "backend/Dockerfile": re.compile(r"^[-+]FROM\s+([^\s:@]+):([0-9][^\s@]*)"),
    "frontend/Dockerfile": re.compile(r"^[-+]FROM\s+([^\s:@]+):([0-9][^\s@]*)"),
    "compose.yaml": re.compile(r"^[-+]\s+image:\s*([^\s:@]+):([0-9][^\s@]*)"),
}


class NotEligible(Exception):
    pass


def login(obj):
    return (obj or {}).get("login")


def numbers(version):
    """The leading numeric parts: '3.14.2-slim' -> [3, 14, 2]."""
    parts = []
    for part in re.split(r"[.\-+]", version):
        if not part.isdigit():
            break
        parts.append(int(part))
    return parts


def same_line(old, new, kind):
    """Whether old -> new stays within a patch or a minor update."""
    a, b = numbers(old), numbers(new)
    if not a or not b:
        return False
    # In 0.x a minor is a breaking change, as npm's caret treats it
    head = 2 if a[0] == 0 else 1
    if kind == "patch":
        head += 1
    return a[:head] == b[:head]


def check_versions(files, kind):
    """The manifests' own diff: every changed version stays in `kind`."""
    for f in files:
        pattern = VERSION_LINES.get(f["filename"])
        if pattern is None:
            continue
        old, new = {}, {}
        for line in (f.get("patch") or "").splitlines():
            m = pattern.match(line)
            if m:
                (old if line.startswith("-") else new)[m.group(1).lower()] = m.group(2)
        if not new:
            raise NotEligible(f"{f['filename']}: no version line in its diff")
        for name, version in new.items():
            if name not in old:
                raise NotEligible(f"{f['filename']}: {name} is new, not a bump")
            if not same_line(old[name], version, kind):
                raise NotEligible(
                    f"{f['filename']}: {name} {old[name]} -> {version} is not a {kind} update"
                )


def update_types(commits):
    """Every update-type in the metadata of Dependabot's commits."""
    found = []
    for c in commits:
        if login(c.get("author")) != DEPENDABOT:
            continue
        found += re.findall(
            r"^\s*update-type:\s*version-update:semver-(\w+)\s*$",
            c["commit"]["message"],
            re.MULTILINE,
        )
    return found


def check_common(pr, files):
    if pr.get("state") != "open":
        raise NotEligible("the pull request is not open")
    if pr.get("draft"):
        raise NotEligible("the pull request is a draft")
    if pr["base"]["ref"] != "main":
        raise NotEligible("the pull request is not for main")
    if (pr["head"].get("repo") or {}).get("full_name") != REPO:
        raise NotEligible("the branch is not in this repository")
    if not files:
        raise NotEligible("the pull request changes no file")
    if len(files) > MAX_FILES:
        raise NotEligible("too many files to judge")


def check_deps(pr, commits, files):
    branch = pr["head"]["ref"]
    m = re.match(r"^dependabot/([a-z_]+)/", branch)
    if not m:
        raise NotEligible(f"branch {branch} is not Dependabot's")
    ecosystem = m.group(1)
    if ecosystem == "github_actions":
        raise NotEligible(
            "GitHub Actions bumps change the workflows: a person merges them"
        )
    if ecosystem not in ECOSYSTEMS:
        raise NotEligible(f"ecosystem {ecosystem} is not eligible")
    rules = ECOSYSTEMS[ecosystem]

    # Dependabot's commits, verified by GitHub, the first one included; the only
    # other commit allowed is the tag bot's update from main (update-branch)
    if not commits or login(commits[0].get("author")) != DEPENDABOT:
        raise NotEligible("the first commit is not Dependabot's")
    for c in commits:
        author, committer = login(c.get("author")), login(c.get("committer"))
        verified = c["commit"]["verification"]["verified"]
        if not verified:
            raise NotEligible(f"commit {c['sha'][:7]} is not verified")
        if author == DEPENDABOT and committer in (DEPENDABOT, "web-flow"):
            continue
        if author == TAG_BOT and committer == "web-flow" and len(c["parents"]) == 2:
            continue
        raise NotEligible(
            f"commit {c['sha'][:7]} is by {author}/{committer}, not Dependabot or the tag bot's update"
        )

    for f in files:
        if f["filename"] not in rules["files"]:
            raise NotEligible(f"{f['filename']} is not a file {ecosystem} updates")
        if f["status"] != "modified":
            raise NotEligible(f"{f['filename']} is {f['status']}, not modified")

    types = update_types(commits)
    if not types:
        raise NotEligible("no update-type in Dependabot's commit metadata")
    bad = sorted(set(types) - rules["types"])
    if bad:
        raise NotEligible(
            f"update types {', '.join(bad)} are not allowed for {ecosystem}"
        )
    # The widest type allowed for this ecosystem bounds the manifests' diff
    check_versions(files, "minor" if "minor" in rules["types"] else "patch")
    return f"eligible deps {ecosystem}"


def check_docs(pr, commits, files):
    for c in commits:
        if login(c.get("author")) != DOCS_AUTHOR:
            raise NotEligible(f"commit {c['sha'][:7]} is not by {DOCS_AUTHOR}")
    for f in files:
        names = [f["filename"], f.get("previous_filename") or f["filename"]]
        if not all(n.startswith("docs/") for n in names):
            raise NotEligible(f"{f['filename']} is outside docs/")
    return "eligible docs"


def decide(pr, commits, files):
    check_common(pr, files)
    author = login(pr.get("user"))
    if author == DEPENDABOT:
        return check_deps(pr, commits, files)
    if author == DOCS_AUTHOR:
        return check_docs(pr, commits, files)
    raise NotEligible(f"pull requests by {author} are not eligible")


def read_json(path):
    with open(path) as fh:
        return json.load(fh)


def main(argv):
    if len(argv) != 4:
        print(__doc__.strip().splitlines()[-3], file=sys.stderr)
        return 2
    try:
        pr, commits, files = (read_json(p) for p in argv[1:4])
    except (OSError, ValueError) as e:
        print(f"unreadable input: {e}", file=sys.stderr)
        return 2
    try:
        print(decide(pr, commits, files))
        return 0
    except NotEligible as e:
        print(f"not eligible: {e}")
        return 1
    except (KeyError, TypeError) as e:
        print(f"not eligible: unexpected input ({e!r})")
        return 1


if __name__ == "__main__":
    sys.exit(main(sys.argv))

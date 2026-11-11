"""Synthetic cases for scripts/check-automerge.py.

Run: python3 -m unittest discover -s scripts -p 'test_check_automerge.py' -v
Each case starts from an eligible pull request and changes one thing.
"""

import copy
import importlib.util
import json
import os
import subprocess
import sys
import tempfile
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
SCRIPT = os.path.join(HERE, "check-automerge.py")
spec = importlib.util.spec_from_file_location("check_automerge", SCRIPT)
ca = importlib.util.module_from_spec(spec)
spec.loader.exec_module(ca)

REPO = "andrei-petrache/haki"


def pr(user, branch, **extra):
    data = {
        "state": "open",
        "draft": False,
        "user": {"login": user},
        "base": {"ref": "main"},
        "head": {"ref": branch, "repo": {"full_name": REPO}},
    }
    data.update(extra)
    return data


def meta(*types):
    lines = ["deps: bump", "", "---", "updated-dependencies:"]
    for i, t in enumerate(types):
        lines += [
            f"- dependency-name: dep{i}",
            "  dependency-version: 1.2.4",
            f"  update-type: version-update:semver-{t}",
        ]
    lines += ["...", "", "Signed-off-by: dependabot[bot] <support@github.com>"]
    return "\n".join(lines)


def commit(
    sha="a" * 40,
    author="dependabot[bot]",
    committer="web-flow",
    verified=True,
    parents=1,
    message=None,
):
    return {
        "sha": sha,
        "author": {"login": author} if author else None,
        "committer": {"login": committer} if committer else None,
        "parents": [{"sha": "p" * 40}] * parents,
        "commit": {
            "message": message if message is not None else meta("patch"),
            "verification": {"verified": verified},
        },
    }


def file(name, patch="", status="modified", previous=None):
    f = {"filename": name, "status": status, "patch": patch}
    if previous:
        f["previous_filename"] = previous
    return f


PIP_IN = "@@ -1,2 +1,2 @@\n-sqlalchemy==2.1.6\n+sqlalchemy==2.1.8\n-psycopg[binary]==3.3.6\n+psycopg[binary]==3.3.8"
NPM_JSON = '@@ -20,2 +20,2 @@\n-    "vitest": "5.0.5"\n+    "vitest": "5.1.0"'
DOCKER = "@@ -1 +1 @@\n-FROM python:3.14.0-slim@sha256:aaa AS build\n+FROM python:3.14.1-slim@sha256:bbb AS build"
COMPOSE = (
    "@@ -3 +3 @@\n-    image: postgres:18.6-trixie\n+    image: postgres:18.7-trixie"
)


def pip_case():
    return (
        pr("dependabot[bot]", "dependabot/pip/backend/backend-minor-patch-1"),
        [commit()],
        [
            file("backend/requirements.in", PIP_IN),
            file("backend/requirements.txt", "@@ hashes @@"),
            file("backend/requirements-dev.txt", "@@ hashes @@"),
        ],
    )


def docs_case():
    return (
        pr("andrei-petrache", "docs/journal-entry"),
        [
            commit(
                author="andrei-petrache",
                committer="andrei-petrache",
                verified=False,
                message="Journal: an entry",
            )
        ],
        [file("docs/journal/decisions.md", "@@ +1 @@\n+| a | b |")],
    )


class Eligible(unittest.TestCase):
    def assertEligible(self, case, expected):
        self.assertEqual(ca.decide(*case), expected)

    def test_pip_patch(self):
        self.assertEligible(pip_case(), "eligible deps pip")

    def test_npm_minor(self):
        case = (
            pr(
                "dependabot[bot]",
                "dependabot/npm_and_yarn/frontend/frontend-minor-patch-1",
            ),
            [commit(message=meta("minor", "patch"))],
            [
                file("frontend/package.json", NPM_JSON),
                file("frontend/package-lock.json", "@@ lock @@"),
            ],
        )
        self.assertEligible(case, "eligible deps npm_and_yarn")

    def test_npm_caret_range(self):
        patch = '@@ -1 +1 @@\n-    "@vitejs/plugin-react": "^6.1.2",\n+    "@vitejs/plugin-react": "^6.2.1",'
        case = (
            pr("dependabot[bot]", "dependabot/npm_and_yarn/frontend/x"),
            [commit(message=meta("minor"))],
            [file("frontend/package.json", patch)],
        )
        self.assertEligible(case, "eligible deps npm_and_yarn")

    def test_docker_patch(self):
        case = (
            pr("dependabot[bot]", "dependabot/docker/backend/docker-patch-1"),
            [commit(message=meta("patch"))],
            [file("backend/Dockerfile", DOCKER)],
        )
        self.assertEligible(case, "eligible deps docker")

    def test_compose_minor(self):
        case = (
            pr("dependabot[bot]", "dependabot/docker_compose/postgres-18.7"),
            [commit(message=meta("minor"))],
            [file("compose.yaml", COMPOSE)],
        )
        self.assertEligible(case, "eligible deps docker_compose")

    def test_tag_bot_update_from_main(self):
        p, commits, files = pip_case()
        commits.append(
            commit(
                sha="b" * 40,
                author="haki-tag-bot[bot]",
                parents=2,
                message="Merge main",
            )
        )
        self.assertEligible((p, commits, files), "eligible deps pip")

    def test_docs(self):
        self.assertEligible(docs_case(), "eligible docs")

    def test_docs_rename_inside_docs(self):
        p, c, _ = docs_case()
        files = [
            file(
                "docs/journal/new.md", status="renamed", previous="docs/journal/old.md"
            )
        ]
        self.assertEligible((p, c, files), "eligible docs")


class NotEligible(unittest.TestCase):
    def assertRefused(self, case, reason):
        with self.assertRaises(ca.NotEligible) as e:
            ca.decide(*case)
        self.assertIn(reason, str(e.exception))

    def test_github_actions(self):
        case = (
            pr("dependabot[bot]", "dependabot/github_actions/actions-minor-patch-1"),
            [commit()],
            [file(".github/workflows/ci.yml", "@@ @@")],
        )
        self.assertRefused(case, "GitHub Actions bumps change the workflows")

    def test_unknown_ecosystem(self):
        p, c, f = pip_case()
        p["head"]["ref"] = "dependabot/cargo/x"
        self.assertRefused((p, c, f), "ecosystem cargo is not eligible")

    def test_major_in_metadata(self):
        p, _, f = pip_case()
        self.assertRefused(
            (p, [commit(message=meta("patch", "major"))], f), "update types major"
        )

    def test_docker_minor(self):
        case = (
            pr("dependabot[bot]", "dependabot/docker/backend/x"),
            [commit(message=meta("minor"))],
            [file("backend/Dockerfile", DOCKER)],
        )
        self.assertRefused(case, "update types minor are not allowed for docker")

    def test_docker_minor_tag_with_stale_patch_metadata(self):
        patch = "@@ -1 +1 @@\n-FROM python:3.14.1-slim\n+FROM python:3.15.0-slim"
        case = (
            pr("dependabot[bot]", "dependabot/docker/backend/x"),
            [commit(message=meta("patch"))],
            [file("backend/Dockerfile", patch)],
        )
        self.assertRefused(case, "is not a patch update")

    def test_stale_metadata_hides_a_major(self):
        p, c, _ = pip_case()
        files = [
            file(
                "backend/requirements.in",
                "@@ @@\n-sqlalchemy==2.1.6\n+sqlalchemy==3.0.0",
            )
        ]
        self.assertRefused(
            (p, c, files), "sqlalchemy 2.1.6 -> 3.0.0 is not a minor update"
        )

    def test_zero_major_minor_is_breaking(self):
        patch = '@@ @@\n-    "eslint-plugin-react-refresh": "^0.5.7",\n+    "eslint-plugin-react-refresh": "^0.6.0",'
        case = (
            pr("dependabot[bot]", "dependabot/npm_and_yarn/frontend/x"),
            [commit(message=meta("minor"))],
            [file("frontend/package.json", patch)],
        )
        self.assertRefused(case, "0.5.7 -> 0.6.0 is not a minor update")

    def test_new_dependency(self):
        p, c, _ = pip_case()
        files = [file("backend/requirements.in", "@@ @@\n+evil==1.0.0")]
        self.assertRefused((p, c, files), "evil is new, not a bump")

    def test_manifest_without_versions(self):
        p, c, _ = pip_case()
        files = [file("backend/requirements.in", "@@ @@\n-# a comment\n+# another")]
        self.assertRefused((p, c, files), "no version line in its diff")

    def test_no_update_type(self):
        p, _, f = pip_case()
        self.assertRefused((p, [commit(message="deps: bump")], f), "no update-type")

    def test_file_outside_the_ecosystem(self):
        p, c, f = pip_case()
        f.append(file("backend/app/main.py", "@@ @@"))
        self.assertRefused((p, c, f), "backend/app/main.py is not a file pip updates")

    def test_workflow_file_in_a_pip_pull_request(self):
        p, c, f = pip_case()
        f.append(file(".github/workflows/ci.yml", "@@ @@"))
        self.assertRefused((p, c, f), "is not a file pip updates")

    def test_added_file(self):
        p, c, _ = pip_case()
        files = [file("backend/requirements.in", PIP_IN, status="added")]
        self.assertRefused((p, c, files), "is added, not modified")

    def test_unverified_commit(self):
        p, _, f = pip_case()
        self.assertRefused((p, [commit(verified=False)], f), "is not verified")

    def test_commit_by_a_person(self):
        p, c, f = pip_case()
        c.append(
            commit(sha="c" * 40, author="andrei-petrache", committer="andrei-petrache")
        )
        self.assertRefused((p, c, f), "is by andrei-petrache/andrei-petrache")

    def test_first_commit_not_dependabots(self):
        p, _, f = pip_case()
        c = [commit(author="haki-tag-bot[bot]", parents=2), commit(sha="d" * 40)]
        self.assertRefused((p, c, f), "the first commit is not Dependabot's")

    def test_tag_bot_commit_that_is_not_a_merge(self):
        p, c, f = pip_case()
        c.append(commit(sha="e" * 40, author="haki-tag-bot[bot]", parents=1))
        self.assertRefused((p, c, f), "not Dependabot or the tag bot's update")

    def test_dependabot_look_alike_committer(self):
        p, _, f = pip_case()
        self.assertRefused(
            (p, [commit(committer="web-flow2")], f),
            "not Dependabot or the tag bot's update",
        )

    def test_dependabot_user_on_another_branch(self):
        p, c, f = pip_case()
        p["head"]["ref"] = "feat/x"
        self.assertRefused((p, c, f), "is not Dependabot's")

    def test_fork(self):
        p, c, f = pip_case()
        p["head"]["repo"] = {"full_name": "someone/haki"}
        self.assertRefused((p, c, f), "the branch is not in this repository")

    def test_fork_deleted(self):
        p, c, f = pip_case()
        p["head"]["repo"] = None
        self.assertRefused((p, c, f), "the branch is not in this repository")

    def test_draft(self):
        p, c, f = pip_case()
        p["draft"] = True
        self.assertRefused((p, c, f), "is a draft")

    def test_closed(self):
        p, c, f = pip_case()
        p["state"] = "closed"
        self.assertRefused((p, c, f), "is not open")

    def test_not_for_main(self):
        p, c, f = pip_case()
        p["base"]["ref"] = "release"
        self.assertRefused((p, c, f), "is not for main")

    def test_no_files(self):
        p, c, _ = pip_case()
        self.assertRefused((p, c, []), "changes no file")

    def test_too_many_files(self):
        p, c, _ = docs_case()
        files = [file(f"docs/{i}.md") for i in range(100)]
        self.assertRefused((p, c, files), "too many files")

    def test_someone_else(self):
        p, c, f = docs_case()
        p["user"] = {"login": "someone"}
        self.assertRefused((p, c, f), "pull requests by someone are not eligible")

    def test_the_tag_bots_own_pull_request(self):
        p, c, f = docs_case()
        p["user"] = {"login": "haki-tag-bot[bot]"}
        self.assertRefused((p, c, f), "are not eligible")

    def test_docs_with_claude_md(self):
        p, c, f = docs_case()
        f.append(file("CLAUDE.md", "@@ @@"))
        self.assertRefused((p, c, f), "CLAUDE.md is outside docs/")

    def test_docs_with_k8s_readme(self):
        p, c, f = docs_case()
        f.append(file("k8s/README.md", "@@ @@"))
        self.assertRefused((p, c, f), "k8s/README.md is outside docs/")

    def test_docs_rename_from_outside(self):
        p, c, _ = docs_case()
        files = [file("docs/x.sh", status="renamed", previous="scripts/x.sh")]
        self.assertRefused((p, c, files), "is outside docs/")

    def test_docs_look_alike_path(self):
        p, c, _ = docs_case()
        self.assertRefused((p, c, [file("docsx/a.md")]), "is outside docs/")

    def test_docs_commit_by_someone_else(self):
        p, c, f = docs_case()
        c.append(commit(sha="f" * 40, author="someone", committer="someone"))
        self.assertRefused((p, c, f), "is not by andrei-petrache")


class CommandLine(unittest.TestCase):
    def run_script(self, *data, args=None):
        with tempfile.TemporaryDirectory() as d:
            paths = []
            for i, obj in enumerate(data):
                path = os.path.join(d, f"{i}.json")
                with open(path, "w") as fh:
                    fh.write(obj if isinstance(obj, str) else json.dumps(obj))
                paths.append(path)
            return subprocess.run(
                [sys.executable, SCRIPT, *(args if args is not None else paths)],
                check=False,
                capture_output=True,
                text=True,
            )

    def test_eligible_exits_0(self):
        r = self.run_script(*pip_case())
        self.assertEqual((r.returncode, r.stdout.strip()), (0, "eligible deps pip"))

    def test_refused_exits_1(self):
        p, c, f = copy.deepcopy(pip_case())
        p["draft"] = True
        r = self.run_script(p, c, f)
        self.assertEqual(r.returncode, 1)
        self.assertTrue(r.stdout.startswith("not eligible: "))

    def test_unreadable_input_exits_2(self):
        r = self.run_script("{not json", "[]", "[]")
        self.assertEqual(r.returncode, 2)

    def test_wrong_arguments_exit_2(self):
        self.assertEqual(self.run_script(args=["only-one"]).returncode, 2)

    def test_unexpected_shape_is_refused(self):
        r = self.run_script({"state": "open"}, [], [])
        self.assertEqual(r.returncode, 1)
        self.assertIn("unexpected input", r.stdout)


if __name__ == "__main__":
    unittest.main()

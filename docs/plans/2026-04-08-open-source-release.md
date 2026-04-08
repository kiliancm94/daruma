# Open-Source Release Preparation

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Prepare Daruma for public release at github.com/kiliancm94/daruma with LICENSE, CONTRIBUTING, expanded README, GitHub templates, and scrubbed docs.

**Architecture:** File-only changes — no code modifications. Create missing project files, expand README for public audience, add GitHub community files, scrub personal paths from docs/plans.

**Tech Stack:** Markdown, Git

---

### Task 1: Create feature branch

**Step 1: Create and switch to branch**

Run: `git checkout -b chore/open-source-release`

**Step 2: Verify branch**

Run: `git branch --show-current`
Expected: `chore/open-source-release`

---

### Task 2: Add MIT LICENSE

**Files:**
- Create: `LICENSE`

**Step 1: Create LICENSE file**

Write `LICENSE` with the standard MIT License text. Copyright holder: `Kilian Canizares Mata`. Year: `2025`.

**Step 2: Commit**

```bash
git add LICENSE
git commit -m "chore: add MIT license"
```

---

### Task 3: Update pyproject.toml metadata

**Files:**
- Modify: `pyproject.toml`

**Step 1: Add project URLs, author, license, and classifiers**

Update the `[project]` section:
- `description` → "Task scheduler for Claude CLI automations with cron, pipelines, skills, and a web UI"
- Add `license = "MIT"`
- Add `authors = [{name = "Kilian Canizares Mata"}]`
- Add `readme = "README.md"`
- Add `classifiers` (Development Status :: 3 - Alpha, Framework :: FastAPI, License :: OSI Approved :: MIT License, Programming Language :: Python :: 3)
- Add `[project.urls]` section with Homepage, Repository, Issues pointing to `https://github.com/kiliancm94/daruma`

**Step 2: Commit**

```bash
git add pyproject.toml
git commit -m "chore: add project metadata for PyPI/GitHub"
```

---

### Task 4: Rewrite README.md

**Files:**
- Modify: `README.md`

**Step 1: Rewrite README for public audience**

Structure:
1. **Title + one-liner** — "Daruma — task scheduler for Claude CLI automations"
2. **Badges** — License (MIT), Python (3.11+), GitHub stars link
3. **What it does** — 3-4 bullet points: cron scheduling, pipelines, skills, web UI + CLI
4. **Screenshot placeholder** — `<!-- TODO: add screenshot -->`
5. **Quick Start** — Local (uv) + Docker, same as current but cleaner
6. **Configuration** — env vars table (keep current)
7. **Features** section with subsections:
   - **Tasks** — cron, manual, webhook triggers
   - **Skills** — global skills from `~/.claude/skills/`, attach to tasks
   - **Pipelines** — sequential steps, stdout chaining
   - **macOS Service** — launchd integration via `daruma service install`
8. **CLI Reference** — keep current examples, expand slightly
9. **API Reference** — keep current table, add skills and pipelines endpoints
10. **Architecture** — brief overview (FastAPI + SQLite + APScheduler + Claude CLI)
11. **Development** — setup, tests, lint, format, migrations
12. **Contributing** — link to CONTRIBUTING.md
13. **License** — MIT link

Keep it practical and scannable. No fluff. Tables where appropriate.

**Step 2: Commit**

```bash
git add README.md
git commit -m "docs: rewrite README for public release"
```

---

### Task 5: Add CONTRIBUTING.md

**Files:**
- Create: `CONTRIBUTING.md`

**Step 1: Write CONTRIBUTING.md**

Cover:
1. **Getting started** — fork, clone, `uv sync --all-extras`, run tests
2. **Development workflow** — branch from main, write tests, run lint/format
3. **Code style** — ruff for linting/formatting, follow existing patterns
4. **Commit messages** — conventional commits (feat/fix/docs/chore)
5. **Pull requests** — describe what and why, reference issues, keep scope small
6. **Architecture overview** — pointer to CLAUDE.md for code conventions
7. **Reporting bugs** — use GitHub Issues with reproduction steps

Keep it short — one page, not a novel.

**Step 2: Commit**

```bash
git add CONTRIBUTING.md
git commit -m "docs: add CONTRIBUTING.md"
```

---

### Task 6: Add GitHub community files

**Files:**
- Create: `.github/ISSUE_TEMPLATE/bug_report.md`
- Create: `.github/ISSUE_TEMPLATE/feature_request.md`
- Create: `.github/PULL_REQUEST_TEMPLATE.md`

**Step 1: Create bug report template**

YAML frontmatter with name, description, labels. Body sections: Describe the bug, Steps to reproduce, Expected behavior, Environment (OS, Python version, Claude CLI version).

**Step 2: Create feature request template**

YAML frontmatter. Body sections: Problem/motivation, Proposed solution, Alternatives considered.

**Step 3: Create PR template**

Sections: Summary (what and why), Test plan, Checklist (tests pass, lint clean, docs updated if needed).

**Step 4: Commit**

```bash
git add .github/
git commit -m "chore: add GitHub issue and PR templates"
```

---

### Task 7: Scrub personal paths from docs/plans

**Files:**
- Modify: `docs/plans/2026-04-01-claude-runner.md`
- Modify: `docs/plans/2026-04-02-daruma-cli.md`
- Modify: `docs/plans/2026-04-06-task-env-vars.md`

**Step 1: Replace all occurrences of personal paths**

In all three files:
- Replace `/Users/kcanizares/vf/automations/daruma` with `.` (current directory)
- Replace `/Users/kcanizares/vf/automations/calendar-api/.api-token` with `/path/to/your/api-token`

Use `replace_all` for efficiency.

**Step 2: Commit**

```bash
git add docs/plans/
git commit -m "docs: scrub personal paths from planning docs"
```

---

### Task 8: Clean up CLAUDE.md for public audience

**Files:**
- Modify: `CLAUDE.md`

**Step 1: Review and trim CLAUDE.md**

The current CLAUDE.md is already generic (about Daruma, not VF). Only changes needed:
- Remove the `macOS service` section reference to `daruma.localhost:9090` (that's a local convention)
- Update the hostname to be generic: "Runs as a launchd agent on the configured host/port"
- Ensure no personal paths or internal references remain

**Step 2: Commit**

```bash
git add CLAUDE.md
git commit -m "docs: clean CLAUDE.md for public release"
```

---

### Task 9: Final verification

**Step 1: Search for remaining personal references**

Run: `git grep -i "kcanizares\|visualfabriq\|vf/automations" -- ':!docs/plans/2026-04-08*'`
Expected: No output (no matches)

**Step 2: Run tests to ensure nothing broke**

Run: `source .venv/bin/activate && pytest -q`
Expected: All tests pass

**Step 3: Review the diff**

Run: `git log --oneline main..HEAD`
Expected: 7 commits (license, pyproject, readme, contributing, github templates, scrub paths, claude.md)

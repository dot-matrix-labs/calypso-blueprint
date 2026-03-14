# Calypso Scaffold Task (Agent Entrypoint)

<!-- last-edited: 2026-03-10 -->

CONTEXT MAP
this ──requires────────▶ index.md (read agent-context/ on session start)
this ──requires────────▶ blueprints/environment-blueprint.md (three-container app cluster)
this ──requires────────▶ development/product-owner-interview.md (Step 10)
this ◀──referenced by──── index.md

**Role:** You are an autonomous agent bootstrapping a new Calypso project from scratch. You are running directly on the cloud host — the user has already SSH'd in (or is connected via a remote IDE such as VS Code Remote SSH). Handle all steps autonomously. Only pause for human input when credentials or decisions are genuinely required.

---

## Step 1: Verify Host Tools

Confirm the following tools are installed on this host, installing any that are missing:

```bash
git --version
gh --version
bun --version
tmux -V
docker --version
kubectl version --client
```

Install missing tools via `apt` or official install scripts. Do not proceed until all tools are present.

---

## Step 2: Start tmux Session

All subsequent work runs inside a named tmux session so the operator can attach or detach without interrupting the agent:

```bash
tmux new-session -A -s main
```

If already inside a tmux session, continue. Surface the session name to the operator:

> **Agent is running in tmux session `main`.** To watch from another terminal:
>
> ```bash
> tmux attach -t main
> ```

---

## Step 3: Provision App Cluster

Run `scripts/provision-cluster.sh` to install k3s, apply all manifests, create secrets, and confirm health.

**Required environment variables:**

- `PROJECT` — lowercase project name (e.g. `invoice-processor`)
- `GITHUB_USER` — GitHub username or org
- `GITHUB_TOKEN` — GitHub PAT with `repo` + `packages:write` scopes

**Cluster target — one of:**

- No extra variables — installs k3s on this host (most common: agent is already on the cloud host)
- `HOST_IP` + `SSH_KEY` — provisions an existing remote host via SSH
- `DIGITALOCEAN_TOKEN` — creates a new DigitalOcean Droplet and provisions it

```bash
# Local (install k3s on this host):
PROJECT=<name> GITHUB_USER=<user> GITHUB_TOKEN=<pat> \
  ./scripts/provision-cluster.sh

# Remote existing host:
HOST_IP=<ip> SSH_KEY=~/.ssh/id_ed25519 PROJECT=<name> GITHUB_USER=<user> GITHUB_TOKEN=<pat> \
  ./scripts/provision-cluster.sh

# New DigitalOcean Droplet:
DIGITALOCEAN_TOKEN=<tok> PROJECT=<name> GITHUB_USER=<user> GITHUB_TOKEN=<pat> \
  ./scripts/provision-cluster.sh
```

The script handles:

- [ ] k3s installed and `kubectl` configured
- [ ] All `k8s/` manifests applied (frontend, worker, db)
- [ ] All secrets created (GHCR credentials, Postgres, worker)
- [ ] All three app containers running and healthy: `frontend`, `worker`, `db`
- [ ] Frontend responds HTTP 200 at the frontend NodePort `/health`

If the script fails, diagnose from the error output and fix before continuing.

---

## Step 4: Establish GitHub Credentials

```bash
echo "${GITHUB_TOKEN}" | gh auth login --with-token
gh auth status  # expected: Logged in to github.com as <username>

git config --global credential.helper store
git config --global user.name "$(gh api user --jq .login)"
git config --global user.email "$(gh api user --jq .email)"
```

If `GITHUB_TOKEN` is not set in the environment, ask the operator for a PAT with `repo` + `packages:write` scopes.

---

## Step 5: Create Project Repo

If `PROJECT_NAME` and `GITHUB_OWNER` are not already set in the environment, ask the operator. Then:

```bash
gh repo create "${GITHUB_OWNER}/${PROJECT_NAME}" --private --description "Built with Calypso" --confirm
gh repo view "${GITHUB_OWNER}/${PROJECT_NAME}"  # verify
```

---

## Step 6: Clone the Calypso Template

```bash
cd /workspace

git clone --depth=1 --branch=main --single-branch \
  https://github.com/dot-matrix-labs/calypso.git "${PROJECT_NAME}"

cd "${PROJECT_NAME}"

# Detach from template history and point at the new private repo
rm -rf .git
git init -b main
git remote add origin "https://${GITHUB_TOKEN}@github.com/${GITHUB_OWNER}/${PROJECT_NAME}.git"
```

Rename `AGENT.md` for the agent platform in use:

```bash
# Claude Code:
cp AGENT.md CLAUDE.md

# Gemini:
# mkdir -p .gemini && cp AGENT.md .gemini/style.md

# Codex:
# cp AGENT.md codex.md
```

Keep `AGENT.md` as the canonical copy. The platform-specific file is a copy that may diverge if the platform requires special syntax.

---

## Step 7: Initial Commit and Push

```bash
git add -A
git commit -m "init: bootstrap from calypso template"
git push -u origin main
```

---

## Step 8: Apply Branch Protection Ruleset

Apply the GitHub repository ruleset to protect main immediately after the first push. This step requires the repository to exist (Step 5) and your `GITHUB_TOKEN` to be authenticated (Step 4).

**Copy the pr-checklist workflow into the repository:**

```bash
mkdir -p .github/workflows
cp /path/to/calypso-blueprint/examples/github-workflows/pr-checklist.yml \
  .github/workflows/pr-checklist.yml
git add .github/workflows/pr-checklist.yml
git commit -m "ci: add pr-checklist workflow"
git push
```

**Apply the branch protection ruleset:**

```bash
# Substitute {owner} and {repo} with actual values, then:
cat > /tmp/ruleset.json <<'EOF'
{
  "name": "main-protection",
  "target": "branch",
  "enforcement": "active",
  "conditions": {
    "ref_name": {
      "include": ["~DEFAULT_BRANCH"],
      "exclude": []
    }
  },
  "bypass_actors": [],
  "rules": [
    {
      "type": "required_status_checks",
      "parameters": {
        "strict_required_status_checks_policy": true,
        "required_status_checks": [
          {"context": "build"},
          {"context": "clippy"},
          {"context": "format"},
          {"context": "unit"},
          {"context": "integration"},
          {"context": "e2e"},
          {"context": "coverage"},
          {"context": "checklist"}
        ]
      }
    },
    {
      "type": "pull_request",
      "parameters": {
        "dismiss_stale_reviews_on_push": false,
        "require_code_owner_review": false,
        "require_last_push_approval": false,
        "required_approving_review_count": 0,
        "required_review_thread_resolution": false
      }
    }
  ]
}
EOF

gh api --method POST "repos/${GITHUB_OWNER}/${PROJECT_NAME}/rulesets" \
  --input /tmp/ruleset.json
```

The canonical ruleset template lives at `examples/github-workflows/ruleset.json` in the calypso-blueprint repository.

**Pre-register the checklist check name:**

The `checklist` status check only appears as a known GitHub check name after the first PR that triggers `pr-checklist.yml`. Create a dummy PR to register it:

```bash
git checkout -b ci/register-checklist-check
git commit --allow-empty -m "ci: register checklist check name"
git push -u origin ci/register-checklist-check
gh pr create --title "ci: register checklist check name" \
  --body "Registering the checklist status check. All items complete:
- [x] checklist check registered" \
  --base main
# Wait for the checklist check to appear green, then close the PR
gh pr close ci/register-checklist-check --delete-branch
```

- [ ] `main-protection` ruleset confirmed active on the repository.
- [ ] `pr-checklist.yml` workflow present and passing on at least one PR.
- [ ] `checklist` check name registered; visible as a required check in the ruleset.

---

## Step 9: Set KUBE_CONFIG Secret

Extract the kubeconfig with the cluster's public IP and set it as a GitHub Actions secret so CI can deploy:

```bash
PUBLIC_IP=$(curl -s ifconfig.me)
kubectl config view --raw \
  | sed "s|https://127.0.0.1:6443|https://${PUBLIC_IP}:6443|g" \
  | base64 -w0 \
  | gh secret set KUBE_CONFIG -R "${GITHUB_OWNER}/${PROJECT_NAME}" --body -
```

- [ ] `KUBE_CONFIG` secret confirmed set. `GITHUB_TOKEN` is provided automatically by GitHub Actions.

---

## Step 10: Load Context

Read `AGENT.md` and `agent-context/index.md`. These define the curriculum and document graph. Do NOT read all blueprints upfront — follow the context escalation loop in `AGENT.md` to load documents as needed during subsequent steps.

---

## Step 11: Product Owner Interview

Conduct the product owner interview per `agent-context/development/product-owner-interview.md`. Do not skip or abbreviate it.

- [ ] Interview completed.
- [ ] Implementation Plan GitHub Issue created with phase structure.
- [ ] Feature Issues created (one per feature) with Motivation, Features, Test Plan, and Stage.
- [ ] External API test credentials collected and stored in `.env.test` (not committed).

---

## Step 12: Scaffold

Verify all foundational elements are present before moving to prototyping. Fix anything missing yourself before proceeding.

#### Architecture

- [ ] Monorepo structure established (`/apps/web`, `/apps/server`, `/packages/*`).
- [ ] All modules use TypeScript, Bun, React, and Tailwind CSS exclusively.
- [ ] `package.json` scripts use `bunx`, not globally installed binaries.
- [ ] Local monorepo dependencies are built in correct order before dependent modules.
- [ ] All modules pass `bun run build`.
- [ ] Linting and formatting are configured and pass cleanly.

#### Documentation

- [ ] `docs/` directory exists at repo root for code documentation and architecture guides (separate from planning, which lives in GitHub Issues).
- [ ] Code comments on every source file: module purpose, key types, and function definitions.
- [ ] `.git/hooks/pre-push` installed per `agent-context/development/documentation-standard.md`.

#### Testing

- [ ] Vitest and Playwright configured.
- [ ] No mocking libraries present (`jest.mock`, `msw`, etc.).
- [ ] Stub test files exist for all categories: server (unit, module, integration) and browser (unit, component, e2e).
- [ ] Full test suite passes.
- [ ] No lint or format warnings.
- [ ] E2e test starts the production `bun` server, which serves a stub HTML page, and Playwright drives it successfully.
- [ ] Playwright HTML reporter set to `open: 'never'`.

#### Deployment

- [ ] `.env` template files present.
- [ ] `k8s/` manifests updated to reference the project's own registry (`ghcr.io/<your-org>/<your-project>/*`). Once CI runs, it replaces the upstream base images via `kubectl set image`.
- [ ] GitHub Actions workflows adapted from `.github/workflows/` in the Calypso repo: build images on push to `main`, push to `ghcr.io/<your-org>/<your-project>`, deploy to cluster via `kubectl set image`.
- [ ] A test CI run completes successfully: image built, pushed to registry, and deployed to the cluster.

#### Final Check

- [ ] **No JS configs** — delete any `.js`/`.mjs` config files generated by scaffolding tools and rewrite in `.ts`.
- [ ] **No emit** — `"noEmit": true` in `tsconfig.json` for all `/packages/*`.
- [ ] **SPA routing** — Bun server checks `Bun.file.exists()` before falling back to `index.html`.
- [ ] **Blueprint compliance** — review all blueprint documents and confirm nothing was violated or skipped.

---

## Step 13: Confirm Ready

Tell the operator:

> **Bootstrap complete.**
>
> Repository: `https://github.com/<owner>/<project-name>`
>
> The agent is running in tmux session `main`. To watch: `tmux attach -t main`.
>
> Next: awaiting your command to begin the Prototype phase.

---

**Action Required:**
If all items above are verified, output:
`[VERIFIED] Scaffold successful. Awaiting command to begin Prototype phase.`

If anything fails, output the failing items, plan the fixes, and execute them immediately.

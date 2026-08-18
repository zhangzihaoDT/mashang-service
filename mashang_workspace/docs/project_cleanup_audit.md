# Project Cleanup Audit — mashang-service

> Generated: 2026-06-16
> Scope: Service layer, workspace layer, shared layer, runtime layer, config layer
> Constraint: Read-only audit — no files deleted, no structural changes made

---

## 1. Current Project Structure Overview

```
mashang-service/                          # Project root (service layer)
│
├── .env                                  # Shared environment variables (gitignored)
├── .venv/                                # Shared Python virtual env (gitignored)
├── requirements.txt                      # Shared dependencies
├── pyproject.toml                        # Project config (pytest, ruff)
├── Makefile                              # CI / Eval / Pipeline commands
│
├── opencode.jsonc                        # OpenCode config (MCP, agents)
├── .opencode/                            # OpenCode skills, plugins, node_modules
├── .local/                               # Local browser profiles, temp data (gitignored)
│
├── AGENTS.md                             # Service-level agent guide
├── README.md                             # Service-level README
│
├── dataset/                              # Shared data assets (gitignored)
│   ├── order_data.parquet                #   Core order data
│   ├── assign_data.csv                   #   Lead assignment data
│   ├── TP&MIX-ways/              #   TP&MIX-ways (parquet/registry/quality)
│   └── ...                               #   Other CSVs + parquets
│
├── shared/                               # Shared business logic (canonical)
│   ├── operators/                        #   14 canonical business operators
│   ├── schema/                           #   Metric registry, business definitions
│   └── loaders/                          #   Dataset loaders (TP&MIX-ways)
│
├── mashang_workspace/                    # AI-native analysis workspace (active dev)
│   ├── runtime_scripts/                  #   Core stable analysis scripts (6)
│   ├── research_scripts/                 #   Research / experimental scripts (7)
│   ├── utility_scripts/                  #   DataOps / SyncOps tools (9)
│   ├── legacy_scripts/                   #   Frozen historical scripts (1)
│   ├── eval/                             #   Eval framework (9 scripts)
│   ├── tests/                            #   Pytest smoke tests (13 files)
│   ├── docs/                             #   Business docs (21 files)
│   ├── outputs/                          #   Generated reports / tables / charts
│   ├── inputs/                           #   External input data
│   └── scratch/                          #   Temporary exploratory scripts
│
├── mashang_runtime/                      # Legacy Agentic BI Runtime (frozen)
│   ├── agent/                            #   Agent loop, planner, router
│   ├── operators/                        #   Legacy operator copies (same as shared/)
│   ├── tools/                            #   Query / statistics / comparison tools
│   └── schema/                           #   Legacy schema copies
│
├── mashang_runtime_v2/                   # Future Runtime V2 (in development)
│   ├── app/                              #   Application layer (service, dispatcher)
│   ├── eval/                             #   Runtime V2 eval
│   └── tests/                            #   Runtime V2 tests
│
├── scripts/                              # Service-level build/render scripts
│   ├── build_tp_and_mix_ways_dataset.py
│   ├── render_official_document.py
│   └── smoke_test_official_document_render.py
│
├── docs/                                 # Service-level docs
│   └── tp_and_mix_ways_dataset.md
│
├── tests/                                # Service-level tests
│   └── test_tp_and_mix_ways_dataset_build.py
│
├── outputs/                              # Service-level outputs
│   ├── assets/brand/                     #   Brand assets
│   ├── reports/                          #   Render outputs
│   ├── smoke/                            #   Smoke test outputs
│   └── submission/                       #   Formal submissions
│
├── skills/                               # OpenCode skill definitions
│   └── official_document_render/
│
├── HTML/                                 # MIIT new car filing HTML pages
│   └── 工信部新车/
│
├── test/                                 # Legacy temporary scripts (gitignored)
│   └── (6 legacy analysis scripts)
│
├── logs/                                 # Query logs, cached results (gitignored)
├── node_modules/                         # NPM dependencies (playwright)
├── package.json                          # NPM package file
│
├── main.py                               # Root CLI entry (thin wrapper → runtime)
└── feishu_bot.py                         # Root Feishu bot (thin wrapper → runtime)
```

---

## 2. Core Asset Inventory

### 2.1 Configuration Layer (Service Level)

| Path | Status | Notes |
|------|--------|-------|
| `pyproject.toml` | ✅ Current | Defines pytest config, ruff, pythonpath |
| `Makefile` | ✅ Current | 207 lines, organized into eval/build/pipeline sections |
| `opencode.jsonc` | ✅ Current | MCP playwright config, connected & verified |
| `.gitignore` | ✅ Current | Covers .venv, dataset, .local, logs, test/, node_modules |
| `package.json` | ✅ Current | Only dependency: playwright |

### 2.2 Shared Logic Layer

| Path | Files | Status | Notes |
|------|-------|--------|-------|
| `shared/operators/` | 14 .py + 2 json | ✅ Canonical | `shared/README.md` marks these as canonical |
| `shared/schema/` | 10 files | ✅ Canonical | Includes `TP&MIX-ways_schema.py` |
| `shared/loaders/` | 2 files | ✅ Current | Only `TP&MIX-ways_loader.py` |

### 2.3 Data Layer

| Path | Status | Notes |
|------|--------|-------|
| `dataset/` | ✅ Shared | Gitignored (should not commit raw data) |
| `dataset/TP&MIX-ways/` | ✅ Shared | Parquet + registry + quality — rebuilt by `make build-tp-and-mix-ways-dataset` |
| `dataset/updater/` | ✅ Shared | Pipeline scripts for data refresh |
| `dataset/wechat/` | 🤔 Specialized | WeChat sync pipeline |

### 2.4 Workspace Scripts

| Directory | Count | Status | Notes |
|-----------|-------|--------|-------|
| `runtime_scripts/` | 6 | ✅ Core | Lock/assign/ATP/attribute — stable with Contract |
| `research_scripts/` | 7 | ✅ Research | Forecast/backtest/release curve |
| `utility_scripts/` | 9 | ✅ Utility | DataOps/render/catalog/eval generation |
| `legacy_scripts/` | 1 | ✅ Frozen | `skills_atp_price.py` — replaced by `atp_price_report.py` |
| `eval/` | 9 | ✅ Eval | Context parser, followup runner, numeric eval |
| `tests/` | 13 | ✅ Test | Script smoke tests + eval tests |

### 2.5 Runtime Layer

| Path | Status | Notes |
|------|--------|-------|
| `mashang_runtime/` | 🟡 Frozen | 0 imports from workspace — truly frozen |
| `mashang_runtime_v2/` | ✅ Active dev | Service, dispatcher, session management |

---

## 3. Retain — Clear to Keep

All items below are correctly positioned and should be retained:

```
opencode.jsonc                            # Active OpenCode config
Makefile                                  # Active command hub
pyproject.toml                            # Active project config
.gitignore                                # Current coverage
package.json                              # Playwright dependency

shared/                                   # Canonical business logic — retain all
dataset/updater/                          # Active pipeline
dataset/wechat/                           # Active pipeline

mashang_workspace/                        # Primary development area — retain all

mashang_runtime_v2/                       # Active development — retain

scripts/build_tp_and_mix_ways_dataset.py   # Active build
scripts/render_official_document.py            # Active render

docs/tp_and_mix_ways_dataset.md            # Active doc

tests/test_tp_and_mix_ways_dataset_build.py  # Active test

.outputs/                                       # Root brand assets
```

---

## 4. Archive Candidates — Move to Legacy

These are clearly frozen, superseded, or no longer in active use:

| Path | Reason | Suggested Action |
|------|--------|------------------|
| `mashang_runtime/` | Fully frozen, 0 imports from workspace. Operators are duplicated in `shared/`. Schema duplicated in `shared/`. | 🟡 **Rename to `mashang_runtime.legacy/`** to signal frozen status. Keep in repo for reference. |
| `skills/` (root) | Duplicate of `.opencode/skills/`; the official document render assets have been consolidated into the repo-level OpenCode skill directory. | 🟢 **Completed** — root `skills/` removed; keep `.opencode/skills/official_document_render/`. |
| `test/` (6 files) | Gitignored, explicitly marked as "temporary analysis scripts". Already gitignored. Archival not urgent. | 🟢 **No action needed** — already gitignored. |
| `main.py` (root) | Thin wrapper: calls `mashang_runtime.main`. The runtime is frozen; this wrapper has no workspace consumers. | 🟡 **Add deprecation notice** but don't delete — may be used by external scripts. |
| `feishu_bot.py` (root) | Thin wrapper: calls `mashang_runtime.feishu_bot`. Same as `main.py`. | 🟡 **Add deprecation notice**. |
| `mashang_runtime/operators/` | 14 operators identical to `shared/operators/` (only diff: 1 README.md). | 🟢 **Already acknowledged** in shared/README.md as legacy. No action needed — frozen with runtime. |
| `mashang_runtime/schema/` | Same content as `shared/schema/`. Legacy copy. | 🟢 **Already acknowledged**. No action. |

---

## 5. Git-Ignore Candidates — Should Be in .gitignore

| Path | Currently Ignored? | Suggestion |
|------|-------------------|------------|
| `mashang_workspace/inputs/feishu/` | ❌ Not in .gitignore | ✅ **Recommend adding** — local downloaded files |
| `mashang_workspace/outputs/tables/*.csv` | ❌ Not in .gitignore | 🟡 **Consider adding** — regenerable data; but HTML reports might be worth tracking |
| `mashang_workspace/outputs/charts/*.png` | ❌ Not in .gitignore | 🟡 **Consider adding** — regenerable from scripts |
| `mashang_workspace/outputs/reports/*.html` | ❌ Not in .gitignore | 🟡 **Keep tracking** — useful as showcase artifacts |
| `mashang_workspace/scratch/` | ❌ Not in .gitignore | ✅ **Recommend adding** — temporary exploratory scripts |
| `mashang_workspace/schema/index_summary_daily_matrix.csv` | ❌ Not in .gitignore | 🟡 **Consider adding** — generated data |
| `node_modules/` | ❌ Not in .gitignore | ✅ **Recommend adding** — installable via `npm install` |
| `outputs/` (root) | ❌ Not in .gitignore | 🟡 **Consider partial ignore** — outputs/smoke and outputs/submission are regenerable; outputs/assets should be tracked. |
| `HTML/工信部新车/images/` | ✅ Already ignored | Correct |
| `logs/` | ✅ Already ignored | Correct |
| `.local/` | ✅ Already ignored | Correct |
| `test/` | ✅ Already ignored | Correct |

---

## 6. Suspect Duplicate / Outdated Files

### 6.1 Operator Duplication: shared/operators ↔ mashang_runtime/operators

**Finding**: All 14 operator `.py` files are byte-identical between `shared/operators/` and `mashang_runtime/operators/`. Only difference is `mashang_runtime/operators/READ ME.md` (which has no counterpart in `shared/`).

**Verdict**: Known and documented in `shared/README.md`. But the fact that `shared/operators/` was created as a copy means any update to operators must be applied to both directories. This is a maintenance burden.

**Recommendation**: After `mashang_runtime` is fully archived to `mashang_runtime.legacy/`, the duplication ceases to be an active concern — the legacy copy just sits there. Medium-term: ensure workspace scripts import from `shared/operators/` exclusively.

### 6.2 Schema Duplication: shared/schema ↔ mashang_runtime/schema

**Finding**: Same as operators — `mashang_runtime/schema/` was copied to `shared/schema/`. Identical content.

**Verdict**: Same as above. Acceptable while frozen.

### 6.3 Root-Level shim scripts

**Finding**: `main.py` (687 B) and `feishu_bot.py` (632 B) at root are thin wrappers:

```python
# main.py
from mashang_runtime.main import main as runtime_main
runtime_main()

# feishu_bot.py
from mashang_runtime.feishu_bot import bot_main
bot_main()
```

**Verdict**: These exist only for backwards compatibility with external scripts that call `python main.py`. The workspace never imports them.

### 6.4 Doc Confusion: root docs/ vs mashang_workspace/docs/

**Finding**: `docs/tp_and_mix_ways_dataset.md` exists at root level. `mashang_workspace/docs/tp_and_mix_ways_usage.md` duplicates some content.

**Verdict**: The root doc describes the dataset build process (service responsibility). The workspace doc describes consumption patterns. They serve different audiences but should cross-reference each other to avoid confusion.

---

## 7. Documentation Inconsistencies

### 7.1 README.md (root) — Stale

| Issue | Detail |
|-------|--------|
| Cluster illusion | Root `README.md` (11 KB) describes `mashang_runtime/` architecture in detail, but this runtime is now frozen |
| Missing TP&MIX-ways | No mention of the TP&MIX-ways dataset asset |
| Script list out of date | References `scripts/` directory layout that has changed |

### 7.2 AGENTS.md (root) — Needs Minor Update

| Issue | Detail |
|-------|--------|
| Missing TP&MIX-ways section | Only `mashang_workspace/AGENTS.md` has this section; root AGENTS.md should also reference it as a service-level asset |
| Runtime references | References `mashang_runtime` as if actively co-developed; should note it's frozen |

### 7.3 mashang_workspace/AGENTS.md — Generally Current

| Issue | Detail |
|-------|--------|
| ✅ Has TP&MIX-ways section | Added in recent update |
| ✅ Has MCP/Playwright info | Not yet added — could add a brief section |

### 7.4 mashang_workspace/docs/project_inventory.md — Stale

| Issue | Detail |
|-------|--------|
| Directory structure out of date | Shows `agent/`, `eval/`, `operators/` at root level — these have been moved/restructured |
| Script list incomplete | Lists scripts from `scripts/` and `test/` directories that no longer follow current layout |
| Missing TP&MIX-ways data | Should list TP&MIX-ways as a data asset |

### 7.5 Missing .gitattributes

**Finding**: No `.gitattributes` file exists. While not critical, adding one would help with line-ending normalization across macOS/Linux.

---

## 8. Recommended Target Structure

```
mashang-service/
├── .env                          # Shared (gitignored)
├── .venv/                        # Shared (gitignored)
├── requirements.txt              # Shared
├── pyproject.toml                # Service config
├── Makefile                      # Service commands
├── .gitignore                    # +node_modules, +scratch, +inputs/feishu
├── .gitattributes                # NEW — line ending normalization
│
├── opencode.jsonc                # OpenCode config
├── .opencode/                    # OpenCode settings (skills, node_modules)
│
├── AGENTS.md                     # Service-level agent guide
│
├── dataset/                      # Shared data (gitignored)
│   ├── order_data.parquet
│   ├── TP&MIX-ways/
│   └── ...
│
├── shared/                       # Canonical business logic
│   ├── operators/
│   ├── schema/
│   └── loaders/
│
├── scripts/                      # Service-level build scripts
│
├── docs/                         # Service-level docs
│
├── tests/                        # Service-level tests
│
├── mashang_workspace/            # Active development workspace
│   ├── runtime_scripts/
│   ├── research_scripts/
│   ├── utility_scripts/
│   ├── legacy_scripts/
│   ├── eval/
│   ├── tests/
│   ├── docs/
│   ├── outputs/
│   ├── inputs/
│   └── scratch/                  # NEW — add to .gitignore
│
├── mashang_runtime.legacy/       # RENAMED — frozen legacy
│   ├── agent/
│   ├── operators/
│   ├── tools/
│   └── schema/
│
├── mashang_runtime_v2/           # Active development
│   └── app/
│
├── HTML/                         # MIIT filing pages
│
├── .local/                       # Browser profiles (gitignored)
└── node_modules/                 # NPM deps (to be gitignored)
```

**Changes from current**:
1. `mashang_runtime/` → `mashang_runtime.legacy/` (rename)
2. `skills/` → merged into `.opencode/skills/` (move)
3. `node_modules/` added to `.gitignore`
4. `mashang_workspace/scratch/` added to `.gitignore`
5. `mashang_workspace/inputs/feishu/` added to `.gitignore`
6. `.gitattributes` created

---

## 9. Phased Cleanup Plan

### Phase 1 — Git-Ignore Only (Safe, Reversible)

| Step | Action | Risk |
|------|--------|------|
| 1.1 | Add `node_modules/` to `.gitignore` | 🟢 None — `package.json` tracks deps |
| 1.2 | Add `mashang_workspace/scratch/` to `.gitignore` | 🟢 None — scratch is ephemeral by definition |
| 1.3 | Add `mashang_workspace/inputs/feishu/` to `.gitignore` | 🟢 None — downloaded files, not source |
| 1.4 | Consider `mashang_workspace/outputs/tables/*.csv` to `.gitignore` | 🟡 Some files used for eval reference — audit first |

### Phase 2 — Doc Updates (Read-Only)

| Step | Action | Risk |
|------|--------|------|
| 2.1 | Update root `README.md` to mark `mashang_runtime` as frozen | 🟢 Doc only |
| 2.2 | Update `project_inventory.md` with current directory structure | 🟢 Doc only |
| 2.3 | Add TP&MIX-ways to root `README.md` and `AGENTS.md` | 🟢 Doc only |
| 2.4 | Cross-reference root `docs/tp_and_mix_ways_dataset.md` from `mashang_workspace/docs/tp_and_mix_ways_usage.md` | 🟢 Doc only |

### Phase 3 — Archive Frozen Components (Needs Confirmation)

| Step | Action | Risk |
|------|--------|------|
| 3.1 | Rename `mashang_runtime/` → `mashang_runtime.legacy/` | 🟡 May break scripts referencing the path. Check `make`, `main.py`, `feishu_bot.py` first |
| 3.2 | Update `main.py` and `feishu_bot.py` to import from new path | 🟡 Directly depends on 3.1 |
| 3.3 | Move `skills/official_document_render/` → `.opencode/skills/` | 🟢 Completed; renderer and smoke test now use the consolidated path |

### Phase 4 — Structural Optimization (Requires Testing)

| Step | Action | Risk |
|------|--------|------|
| 4.1 | Remove `mashang_workspace/schema/` (duplicate of `shared/schema/`) | 🔴 Must ensure 0 imports break — workspace may have files referencing local `schema/` |
| 4.2 | Remove `mashang_workspace/registry/` (capability_registry.json → shared slot?) | 🔴 Depends on where capability registry should live |
| 4.3 | Consolidate `outputs/` (root) into `mashang_workspace/outputs/` | 🟡 Brand assets (root outputs/assets/) serve both layers — may need shared location |

---

## 10. High-Risk Operations

The following operations carry elevated risk and should only be done after thorough testing:

| # | Operation | Risk Level | Why |
|---|-----------|------------|-----|
| H1 | Delete `test/` (lowercase, root) | 🟢 Low | Already gitignored. But files may be referenced in documentation |
| H2 | Remove `mashang_workspace/schema/` | 🔴 High | Workspace scripts may import `from schema import ...` — must audit all imports first |
| H3 | Remove `mashang_workspace/registry/` | 🟡 Medium | Only capability_registry.json; audit who reads it |
| H4 | Delete `mashang_runtime/` entirely | 🔴 High | The project has no dedicated archive branch. Rename rather than delete |
| H5 | Restructure root `outputs/` | 🟡 Medium | `outputs/assets/brand/` is referenced from template CSS — path may be hardcoded |
| H6 | Remove `skills/` (root) | 🟡 Medium | Must verify OpenCode does not scan root `skills/` for skills definitions |

---

## 11. Audit Summary

### 11.1 Structural Health Score

| Layer | Health | Issues |
|-------|--------|--------|
| Service config (root) | 🟢 90% | Minor: node_modules not gitignored |
| Shared logic | 🟢 100% | Clean separation |
| Data assets | 🟢 95% | TP&MIX-ways well-structured |
| Workspace | 🟢 90% | scratch/ not gitignored; schema/ and registry/ duplicate shared/ |
| Runtime legacy | 🟡 70% | Duplicates operators/schema; no active consumers; rename overdue |
| Runtime v2 | 🟢 95% | Clean, minimal |
| Documentation | 🟡 65% | README.md and project_inventory.md outdated |

### 11.2 Immediate Actions (Phase 1 — Should Do Now)

1. `git add .gitignore` with `node_modules/`, `mashang_workspace/scratch/`, `mashang_workspace/inputs/feishu/`
2. No structural changes needed — the project architecture is fundamentally sound

### 11.3 Short-Term Actions (Phase 2 — Next Week)

3. Update root `README.md` and `project_inventory.md`
4. Cross-reference TP&MIX-ways docs

### 11.4 Medium-Term Actions (Phase 3-4 — Next Month)

5. Rename `mashang_runtime/` → `mashang_runtime.legacy/`
6. Consolidate root `skills/` into `.opencode/skills/`
7. Clean up workspace duplicates (`schema/`, `registry/`)
8. Decide on output consolidation strategy

---

## 12. Suggested Next OpenCode Instructions

```bash
# Phase 1: Update .gitignore
# Edit .gitignore to add:
#   node_modules/
#   mashang_workspace/scratch/
#   mashang_workspace/inputs/feishu/

# Phase 2: Update docs
# Update root README.md to mark mashang_runtime as frozen
# Update mashang_workspace/docs/project_inventory.md
# Cross-reference TP&MIX-ways docs between root and workspace

# Phase 3: Archive runtime
# git mv mashang_runtime mashang_runtime.legacy
# Update main.py and feishu_bot.py import paths

# Phase 4: Consolidate skills
# Consolidated into .opencode/skills/official_document_render/
# git rm skills/

# Verify no breakage:
# make test
# make eval
# pytest mashang_workspace/tests -q
# pytest tests/test_tp_and_mix_ways_dataset_build.py -q
```

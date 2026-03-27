# Procstat Tool

## Purpose
Collects periodic snapshots of `/proc` filesystem files during benchmark execution and post-processes them into crucible metrics. Primary metric output is interrupt rates derived from interrupt count deltas.

## Languages
- Bash: collection scripts (`procstat-start`, `procstat-stop`, `procstat-collect`)
- Perl: post-processor (`procstat-post-process`)

## Key Files
| File | Purpose |
|------|---------|
| `procstat-start` | Validates collector, sets defaults, captures CPU topology, launches `procstat-collect` in background |
| `procstat-collect` | Reads configured /proc files at intervals, appends timestamped snapshots |
| `procstat-stop` | Kills collector, compresses output with xz |
| `procstat-post-process` | Derives interrupt-rate metrics from snapshots using 4 parallel processes (uses `toolbox::metrics`, `toolbox::json` from `$TOOLBOX_HOME/perl`) |
| `rickshaw.json` | Rickshaw integration: endpoint allow/block lists, file deployment, post-process script |
| `workshop.json` | Engine image build requirements (minimal) |

## Configuration
- `--files <list>` — Comma-separated /proc files to collect (default: `interrupts,vmstat,slabinfo,softirqs,meminfo,schedstat`)
- `--interval <seconds>` — Collection interval (default: `3`)

## Conventions
- Primary branch is `master`
- Runs as a profiler tool on master/worker/profiler roles, blocked on client/server
- Standard Bash/Perl modelines and 4-space indentation

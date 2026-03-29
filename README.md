# tool-procstat
[![CI Actions Status](https://github.com/perftool-incubator/tool-procstat/workflows/crucible-ci/badge.svg)](https://github.com/perftool-incubator/tool-procstat/actions)

Collects and post-processes files from the `/proc` filesystem for the [crucible](https://github.com/perftool-incubator/crucible) performance testing framework.

## Data Collected

Procstat periodically snapshots `/proc` files during test execution. The default set is:

| /proc File | Data |
|------------|------|
| interrupts | Per-CPU interrupt counts (post-processed into interrupt rates) |
| vmstat | Virtual memory statistics |
| slabinfo | Kernel slab allocator statistics |
| softirqs | Software interrupt counts |
| meminfo | System memory usage |
| schedstat | Scheduler statistics |

## Configuration

The start script accepts two parameters:
- `--files <list>` — Comma-separated list of /proc files to collect (default: `interrupts,vmstat,slabinfo,softirqs,meminfo,schedstat`)
- `--interval <seconds>` — Collection interval in seconds (default: `3`)

## Integration

Procstat runs as a profiler tool on endpoint nodes. It is allowed on profiler, master, and worker collector roles but blocked on client and server roles. The post-processor (`procstat-post-process`) derives interrupt-rate metrics from the raw snapshots using parallel processing.

### rickshaw.json
Defines how procstat integrates with rickshaw: which files to deploy to engines, which endpoint/collector-type combinations are allowed or blocked, and the post-processing script.

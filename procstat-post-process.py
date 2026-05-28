#!/usr/bin/env python3
# -*- mode: python; indent-tabs-mode: nil; python-indent-level: 4 -*-
# vim: autoindent tabstop=4 shiftwidth=4 expandtab softtabstop=4 filetype=python

import os
import re
import sys
import threading
from pathlib import Path

TOOLBOX_HOME = os.environ.get("TOOLBOX_HOME")
if TOOLBOX_HOME:
    sys.path.append(str(Path(TOOLBOX_HOME) / "python"))

from toolbox.cdm_metrics import CDMMetrics
from toolbox.fileio import open_read_text_file
from toolbox.system_cpu_topology import build_cpu_topology, get_cpu_topology


def process_interrupts(fork_idx, num_forks, log_file, cpu_topo):
    metrics = CDMMetrics()
    desc = {"class": "throughput", "source": "procstat", "type": "interrupts-sec"}
    curr_timestamp_ms = None
    prev_timestamp_ms = None
    cpu_ids = []
    curr_irq_counts = {}
    prev_irq_counts = {}
    first_cpu_idx = 0
    last_cpu_idx = 0

    try:
        fh, _ = open_read_text_file(log_file)
    except FileNotFoundError:
        print(f"ERROR: could not open {log_file}")
        return

    for line in fh:
        line = line.rstrip("\n")

        m = re.match(r'^\s+(CPU\d+\s+)+', line)
        if m:
            cpu_ids = [int(x) for x in re.findall(r'CPU(\d+)', line)]
            num_cpus = len(cpu_ids)
            first_cpu_idx = int(fork_idx * (num_cpus / num_forks))
            last_cpu_idx = int((fork_idx + 1) * (num_cpus / num_forks))
            if last_cpu_idx > num_cpus:
                last_cpu_idx = num_cpus
            continue

        m = re.match(r'^DATE:(\d+\.\d+)$', line)
        if m:
            if curr_timestamp_ms is not None:
                prev_timestamp_ms = curr_timestamp_ms
            curr_timestamp_ms = int(float(m.group(1)) * 1000)
            continue

        m = re.match(r'^\s*([A-Z]{3}|[0-9]+):([^a-z,A-Z]+)(.*)', line)
        if m:
            irq = m.group(1)
            counts_str = m.group(2)
            extra = m.group(3)
            counts = counts_str.split()
            parts = extra.split(None, 2)
            irq_type = parts[0] if len(parts) > 0 else ""
            irq_desc = parts[2] if len(parts) > 2 else ""

            for cpu_idx in range(first_cpu_idx, last_cpu_idx):
                if cpu_idx >= len(cpu_ids) or cpu_idx >= len(counts):
                    continue
                cpu = cpu_ids[cpu_idx]
                curr_count = int(counts[cpu_idx])

                if irq in prev_irq_counts and cpu in prev_irq_counts[irq]:
                    irq_diff = curr_count - prev_irq_counts[irq][cpu]
                    time_diff_sec = (curr_timestamp_ms - prev_timestamp_ms) / 1000
                    if time_diff_sec > 0:
                        ints_sec = irq_diff / time_diff_sec
                        package, die, core, thread = get_cpu_topology(cpu, cpu_topo)
                        names = {
                            "package": package, "die": die, "core": core,
                            "thread": thread, "cpu": cpu, "irq": irq,
                            "type": irq_type, "desc": irq_desc,
                        }
                        sample = {"value": ints_sec, "end": curr_timestamp_ms}
                        metrics.log_sample(str(fork_idx), desc, names, sample)

                prev_irq_counts.setdefault(irq, {})[cpu] = curr_count

    fh.close()
    metrics.finish_samples()


def process_softnet_stat(log_file, cpu_topo, file_id):
    metrics = CDMMetrics()
    curr_timestamp_ms = None
    prev_timestamp_ms = None
    prev_counts = {}

    metric_names = {
        0: "processed-sec",
        1: "dropped-sec",
        2: "time-squeeze-sec",
    }

    try:
        fh, _ = open_read_text_file(log_file)
    except FileNotFoundError:
        print(f"ERROR: could not open {log_file}")
        return

    for line in fh:
        line = line.rstrip("\n")

        m = re.match(r'^DATE:(\d+\.\d+)$', line)
        if m:
            if curr_timestamp_ms is not None:
                prev_timestamp_ms = curr_timestamp_ms
            curr_timestamp_ms = int(float(m.group(1)) * 1000)
            continue

        fields = line.split()
        if len(fields) < 13:
            continue
        try:
            cpu = int(fields[12], 16)
        except (ValueError, IndexError):
            continue

        for col_idx, metric_type in metric_names.items():
            try:
                curr_count = int(fields[col_idx], 16)
            except (ValueError, IndexError):
                continue

            key = (cpu, col_idx)
            if prev_timestamp_ms is not None and key in prev_counts:
                time_diff_sec = (curr_timestamp_ms - prev_timestamp_ms) / 1000
                if time_diff_sec > 0:
                    rate = (curr_count - prev_counts[key]) / time_diff_sec
                    package, die, core, thread = get_cpu_topology(cpu, cpu_topo)
                    desc = {
                        "class": "throughput",
                        "source": "procstat",
                        "type": metric_type,
                    }
                    names = {
                        "package": package, "die": die, "core": core,
                        "thread": thread, "num": cpu,
                    }
                    sample = {"value": rate, "end": curr_timestamp_ms}
                    metrics.log_sample(file_id, desc, names, sample)

            prev_counts[key] = curr_count

    fh.close()
    metrics.finish_samples()


def main():
    num_forks = 4
    data_dir = "proc"

    if not os.path.isdir(data_dir):
        print(f"ERROR: {data_dir} directory not found")
        return

    cpu_topo = build_cpu_topology("sys/devices/system/cpu")

    for entry in sorted(os.listdir(data_dir)):
        if entry in ("interrupts", "interrupts.xz"):
            log_file = os.path.join(data_dir, entry)
            threads = []
            for i in range(num_forks):
                t = threading.Thread(
                    target=process_interrupts,
                    args=(i, num_forks, log_file, cpu_topo),
                )
                t.start()
                threads.append(t)
            for t in threads:
                t.join()
            break

    softnet_dir = os.path.join(data_dir, "net")
    if os.path.isdir(softnet_dir):
        for entry in sorted(os.listdir(softnet_dir)):
            if entry.startswith("softnet_stat"):
                log_file = os.path.join(softnet_dir, entry)
                print(f"Processing softnet_stat from {log_file}")
                process_softnet_stat(log_file, cpu_topo, "softnet")
                break

    print("procstat post-processing complete")


if __name__ == "__main__":
    main()

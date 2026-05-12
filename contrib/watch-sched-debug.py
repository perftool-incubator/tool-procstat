#!/usr/bin/env python3
# -*- mode: python; indent-tabs-mode: nil; python-indent-level: 4 -*-
# vim: autoindent tabstop=4 shiftwidth=4 expandtab softtabstop=4 filetype=python
#
# Monitor the kernel scheduler debug file for changes by periodically
# reading it and displaying a unified diff of the per-CPU runnable task
# lists between consecutive samples. Useful for identifying unexpected
# task migration, pinning violations, or scheduling anomalies on
# isolated CPUs during benchmark runs.

import argparse
import os
import difflib
import queue
import signal
import sys
import threading
import time
from datetime import datetime


def parse_cpus(value):
    cpus = set()
    for element in value.split(","):
        if "-" in element:
            parts = element.split("-", 1)
            for i in range(int(parts[0]), int(parts[1]) + 1):
                cpus.add(i)
        else:
            cpus.add(int(element))
    return cpus


def default_sched_debug_file():
    for path in ["/sys/kernel/debug/sched/debug", "/proc/sched_debug"]:
        if os.path.exists(path):
            return path
    return "/sys/kernel/debug/sched/debug"


def parse_args():
    parser = argparse.ArgumentParser(description="Watch /sys/kernel/debug/sched/debug for changes")
    parser.add_argument("--interval", type=float, default=10, help="Sampling interval in seconds (default: 10)")
    parser.add_argument("--count", type=int, default=-1, help="Number of samples to collect (default: infinite)")
    parser.add_argument("--cpus", type=parse_cpus, default={0}, help="CPUs to monitor, e.g. 0,2,4-7 (default: 0)")
    parser.add_argument("--file", default=default_sched_debug_file(), help="Path to sched debug file (default: auto-detect)")
    return parser.parse_args()


def read_file(file_name):
    timestamp = time.time()
    with open(file_name, "r") as f:
        content = f.read()
    return (timestamp, content)


def parse_sample(timestamp, content, watched_cpus):
    sample = {"timestamp": timestamp}
    cpus = content.split("cpu#")

    for i in range(1, len(cpus)):
        match = cpus[i].split(",", 1)
        cpu_num = int(match[0])

        if cpu_num not in watched_cpus:
            continue

        parts = cpus[i].split("runnable tasks:", 1)
        if len(parts) > 1:
            sample[cpu_num] = parts[1]

    return sample


def format_timestamp(ts):
    dt = datetime.fromtimestamp(ts)
    return dt.strftime("%Y-%m-%d %H:%M:%S") + ".%03d" % (dt.microsecond / 1000)


def diff_samples(prev, cur, watched_cpus):
    print()
    print("Start: %s (%s)" % (format_timestamp(prev["timestamp"]), prev["timestamp"]))
    print("End:   %s (%s)" % (format_timestamp(cur["timestamp"]), cur["timestamp"]))

    for cpu in sorted(watched_cpus):
        if cpu not in prev or cpu not in cur:
            continue

        print("\nCPU: %d\n" % cpu)

        start_lines = prev[cpu].split("\n", 3)
        stop_lines = cur[cpu].split("\n", 3)

        if len(start_lines) > 1:
            print(start_lines[1])
        if len(start_lines) > 2:
            print(start_lines[2])

        if len(start_lines) > 3 and len(stop_lines) > 3:
            diff = difflib.unified_diff(
                start_lines[3].splitlines(keepends=True),
                stop_lines[3].splitlines(keepends=True),
                n=0,
            )
            for line in diff:
                if line.startswith("@@") or line.startswith("---") or line.startswith("+++"):
                    continue
                print(line, end="" if line.endswith("\n") else "\n")


def collector(data_queue, quit_event, args):
    counter = 0

    while not quit_event.is_set():
        timestamp, content = read_file(args.file)
        data_queue.put((timestamp, content))

        if args.count != -1:
            counter += 1
            if counter == args.count + 1:
                quit_event.set()
                return

        quit_event.wait(args.interval)


def reporter(data_queue, quit_event, args):
    prev_sample = None

    while not quit_event.is_set() or not data_queue.empty():
        try:
            timestamp, content = data_queue.get(timeout=args.interval / 2)
        except queue.Empty:
            continue

        cur_sample = parse_sample(timestamp, content, args.cpus)

        if prev_sample is not None:
            diff_samples(prev_sample, cur_sample, args.cpus)

        prev_sample = cur_sample


def main():
    args = parse_args()

    quit_event = threading.Event()

    signal.signal(signal.SIGINT, lambda *_: quit_event.set())

    data_queue = queue.Queue()

    collector_thread = threading.Thread(target=collector, args=(data_queue, quit_event, args), daemon=True)
    reporter_thread = threading.Thread(target=reporter, args=(data_queue, quit_event, args), daemon=True)

    collector_thread.start()
    reporter_thread.start()

    while not quit_event.is_set() and collector_thread.is_alive() and reporter_thread.is_alive():
        time.sleep(args.interval / 2)

    quit_event.set()

    collector_thread.join()
    reporter_thread.join()


if __name__ == "__main__":
    main()

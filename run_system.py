#!/usr/bin/env python3
"""Launch the complete local ColdChain Guardian demonstration."""

from __future__ import annotations

import argparse
from pathlib import Path
import signal
import subprocess
import sys
import time

from coldchain_guardian.config import PROJECT_ROOT, load_config
from coldchain_guardian.preflight import broker_is_reachable, run_preflight


PYTHON_COMPONENTS = (
    ("Data Manager", "coldchain_guardian.data_manager.manager"),
    ("Emulator Console", "coldchain_guardian.emulators.console"),
    ("Main GUI", "coldchain_guardian.gui.main_window"),
)


def _arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Launch the local ColdChain Guardian demonstration."
    )
    parser.add_argument(
        "--check",
        action="store_true",
        help="run dependency and broker checks without starting components",
    )
    parser.add_argument(
        "--no-start-broker",
        action="store_true",
        help="require an already-running broker instead of starting Mosquitto",
    )
    return parser.parse_args()


def _print_report(report) -> None:
    if report.missing_packages:
        print("Missing Python packages: " + ", ".join(report.missing_packages))
    else:
        print("Python dependencies: OK")
    print(
        "MQTT broker: "
        + ("REACHABLE" if report.broker_reachable else "NOT REACHABLE")
    )
    print(
        "Mosquitto executable: "
        + (report.mosquitto_executable or "NOT FOUND")
    )


def _start_broker(executable: str, config_path: Path) -> subprocess.Popen:
    print(f"Starting local Mosquitto broker using {config_path}")
    return subprocess.Popen(
        [executable, "-c", str(config_path)],
        cwd=PROJECT_ROOT,
    )


def _wait_for_broker(host: str, port: int, *, timeout: float = 5.0) -> bool:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if broker_is_reachable(host, port):
            return True
        time.sleep(0.1)
    return False


def _start_component(name: str, module: str) -> subprocess.Popen:
    print(f"Starting {name}")
    return subprocess.Popen(
        [sys.executable, "-m", module],
        cwd=PROJECT_ROOT,
    )


def _stop_process(process: subprocess.Popen, name: str) -> None:
    if process.poll() is not None:
        return
    print(f"Stopping {name}")
    process.terminate()
    try:
        process.wait(timeout=5)
    except subprocess.TimeoutExpired:
        process.kill()
        process.wait(timeout=2)


def main() -> int:
    args = _arguments()
    config = load_config()
    report = run_preflight(config)
    _print_report(report)

    if args.check:
        return 0 if report.can_launch else 2
    if report.missing_packages:
        print("Install the project requirements before launching:")
        print(f"  {sys.executable} -m pip install -r requirements.txt")
        return 2

    managed_processes: list[tuple[str, subprocess.Popen]] = []
    stop_requested = False

    def request_stop(signum: int, frame: object) -> None:
        nonlocal stop_requested
        del signum, frame
        stop_requested = True

    signal.signal(signal.SIGINT, request_stop)
    signal.signal(signal.SIGTERM, request_stop)

    try:
        if not report.broker_reachable:
            if args.no_start_broker:
                print("No MQTT broker is reachable and automatic startup is disabled.")
                return 2
            if report.mosquitto_executable is None:
                print("Mosquitto is not installed and no broker is running.")
                return 2
            broker = _start_broker(
                report.mosquitto_executable,
                PROJECT_ROOT / "config" / "mosquitto.conf",
            )
            managed_processes.append(("Mosquitto", broker))
            if not _wait_for_broker(config.mqtt.host, config.mqtt.port):
                print("Local MQTT broker did not become ready.")
                return 2

        for name, module in PYTHON_COMPONENTS:
            process = _start_component(name, module)
            managed_processes.append((name, process))
            time.sleep(0.6)
            if process.poll() is not None:
                print(f"{name} exited during startup with code {process.returncode}.")
                return process.returncode or 1

        print("ColdChain Guardian is running. Press Ctrl+C to stop.")
        while not stop_requested:
            for name, process in managed_processes:
                return_code = process.poll()
                if return_code is not None:
                    if name == "Main GUI" and return_code == 0:
                        return 0
                    print(f"{name} exited unexpectedly with code {return_code}.")
                    return return_code or 1
            time.sleep(0.5)
        return 0
    finally:
        for name, process in reversed(managed_processes):
            _stop_process(process, name)


if __name__ == "__main__":
    raise SystemExit(main())


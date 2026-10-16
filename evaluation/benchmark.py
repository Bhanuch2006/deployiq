"""Measure pip install time with an empty versus reused local download cache."""
import argparse
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import platform
import statistics
import subprocess
import sys
import tempfile
import time

ROOT = Path(__file__).resolve().parents[1]
REQUIREMENTS = Path(__file__).with_name("requirements-benchmark.txt")


def summarize(samples):
    baseline = [sample["install_seconds"] for sample in samples if sample["variant"] == "baseline"]
    warm = [sample["install_seconds"] for sample in samples if sample["variant"] == "cached" and sample["cache_state"] == "warm"]
    cold = [sample["install_seconds"] for sample in samples if sample["variant"] == "cached" and sample["cache_state"] == "cold"]
    if len(baseline) < 3 or len(warm) < 3 or len(cold) != 1:
        raise ValueError("At least 3 baseline, 3 warm-cache, and exactly 1 cold-cache sample are required")
    base = statistics.median(baseline)
    cached = statistics.median(warm)
    return {"baseline_median_seconds": round(base, 4), "warm_median_seconds": round(cached, 4), "cold_seconds": round(cold[0], 4), "improvement_percent": round((base - cached) / base * 100, 2), "baseline_samples": len(baseline), "warm_samples": len(warm)}


def markdown(report):
    summary = report["summary"]
    lines = ["## DeployIQ cache experiment", "", "Measured pip dependency installation only; not total build or deployment time.", "", "| Variant | Install time (seconds) |", "| --- | ---: |", f"| No-cache baseline, median of {summary['baseline_samples']} | {summary['baseline_median_seconds']:.2f} |", f"| Cold-cache fill, one run | {summary['cold_seconds']:.2f} |", f"| Warm cache, median of {summary['warm_samples']} | {summary['warm_median_seconds']:.2f} |", "", f"Warm-cache median: **{abs(summary['improvement_percent']):.2f}% {'faster' if summary['improvement_percent'] >= 0 else 'slower'}** than the no-cache baseline.", "", "### Every measurement", "", "| Order | Variant | Cache state | Seconds |", "| --- | --- | --- | ---: |"]
    lines += [f"| {i} | {s['variant']} | {s['cache_state']} | {s['install_seconds']:.4f} |" for i, s in enumerate(report["samples"], 1)]
    lines += ["", "Same runner, Python, pinned dependencies, and fresh virtual environment per sample. Variant order alternates between rounds. Network and shared-runner variability still apply. The cold-cache fill is excluded from the warm comparison. This experiment does not include GitHub cache restore/save overhead."]
    return "\n".join(lines) + "\n"


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    samples = []
    resolved = None
    with tempfile.TemporaryDirectory(prefix="deployiq-cache-") as temp:
        scratch = Path(temp)
        cache = scratch / "pip-cache"
        for round_index in range(4):
            variants = ["baseline", "cached"] if round_index % 2 == 0 else ["cached", "baseline"]
            for variant in variants:
                with tempfile.TemporaryDirectory(dir=scratch, prefix="venv-") as venv_dir:
                    subprocess.run([sys.executable, "-m", "venv", venv_dir], check=True)
                    python = str(Path(venv_dir) / "bin/python")
                    command = [python, "-m", "pip", "--isolated", "--disable-pip-version-check", "install", "--no-input", "--only-binary=:all:", "-r", str(REQUIREMENTS)]
                    command += ["--no-cache-dir"] if variant == "baseline" else ["--cache-dir", str(cache)]
                    started = time.perf_counter()
                    subprocess.run(command, check=True, timeout=180)
                    seconds = time.perf_counter() - started
                    subprocess.run([python, "-m", "pip", "check"], check=True)
                    # Validate the real app imports after each installation, outside the timed section.
                    subprocess.run([python, "-c", "import sys; sys.path.insert(0, sys.argv[1]); from app import app; assert app.title == 'DeployIQ Sample App'", str(ROOT / "sample-app")], check=True)
                    installed = subprocess.check_output([python, "-m", "pip", "freeze"], text=True)
                    if resolved is None:
                        resolved = installed
                    elif installed != resolved:
                        raise RuntimeError("Resolved dependencies differ between samples")
                    sample = {"variant": variant, "cache_state": "disabled" if variant == "baseline" else "cold" if round_index == 0 else "warm", "round": round_index + 1, "install_seconds": round(seconds, 4)}
                    samples.append(sample)
                    print(json.dumps(sample), flush=True)
    report = {"schema_version": 1, "metric": "pip_install_seconds", "repository": os.getenv("GITHUB_REPOSITORY", "local"), "run_id": os.getenv("GITHUB_RUN_ID", "local"), "run_attempt": os.getenv("GITHUB_RUN_ATTEMPT", "1"), "head_sha": os.getenv("GITHUB_SHA", "local"), "measured_at": datetime.now(timezone.utc).isoformat(), "python": platform.python_version(), "platform": platform.platform(), "requirements_sha256": hashlib.sha256(REQUIREMENTS.read_bytes()).hexdigest(), "resolved_dependencies": resolved.splitlines(), "samples": samples, "summary": summarize(samples), "scope": "Dependency installation only; excludes venv creation, validation, cache persistence/restore, and total job time."}
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2) + "\n")
    args.output.with_suffix(".md").write_text(markdown(report))
    if os.getenv("GITHUB_STEP_SUMMARY"):
        with open(os.environ["GITHUB_STEP_SUMMARY"], "a") as stream:
            stream.write(markdown(report))


if __name__ == "__main__":
    main()

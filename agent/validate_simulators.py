#!/usr/bin/env python3
"""
Validate simulators: wait for each simulator to fail, confirm isolator labeled the
deployment, confirm repairer cleared the label and pods recovered.

Usage:
  python agent/validate_simulators.py
"""
import subprocess
import time
import json
from typing import Optional

NAMESPACE = "autohealer"
POLL = 2
TIMEOUT = 180

SIMULATORS = [
    "bad-config-simulator",
    "bad-deploy-simulator",
    "crash-simulator",
    "liveness-fail-simulator",
    "oom-simulator",
    "readiness-fail-simulator",
]


def run(cmd: list[str]) -> tuple[str, str, int]:
    p = subprocess.run(cmd, capture_output=True, text=True)
    return p.stdout.strip(), p.stderr.strip(), p.returncode


def get_pods_for_app(app_label: str) -> list[dict]:
    out, err, code = run(["kubectl", "get", "pods", "-n", NAMESPACE, "-l", f"app={app_label}", "-o", "json"])
    if code != 0:
        return []
    data = json.loads(out)
    return data.get("items", [])


def get_deployment_label(deployment: str, label: str) -> Optional[str]:
    out, err, code = run(["kubectl", "get", "deployment", deployment, "-n", NAMESPACE, "-o", "jsonpath={.metadata.labels.%s}" % label])
    if code != 0:
        return None
    return out or None


def pod_unhealthy(pod: dict) -> bool:
    phase = pod.get("status", {}).get("phase", "")
    if phase in ("Failed", "Unknown"):
        return True
    # check container states
    for cs in pod.get("status", {}).get("containerStatuses", []):
        state = cs.get("state", {})
        waiting = state.get("waiting", {})
        if waiting.get("reason") in ("CrashLoopBackOff", "ImagePullBackOff", "ErrImagePull", "RunContainerError", "OOMKilled", "Error"):
            return True
        terminated = state.get("terminated", {})
        if terminated.get("reason"):
            return True
    for cond in pod.get("status", {}).get("conditions", []):
        if cond.get("type") == "Ready" and cond.get("status") == "False":
            return True
    return False


def wait_for_unhealthy(app: str, timeout: int = TIMEOUT) -> Optional[dict]:
    start = time.time()
    while time.time() - start < timeout:
        pods = get_pods_for_app(app)
        if pods:
            for p in pods:
                if pod_unhealthy(p):
                    return p
        time.sleep(POLL)
    return None


def wait_for_label(deployment: str, label: str, expect: str, timeout: int = TIMEOUT) -> bool:
    start = time.time()
    while time.time() - start < timeout:
        val = get_deployment_label(deployment, label)
        if (val or "") == expect:
            return True
        time.sleep(POLL)
    return False


def wait_for_pods_ready(app: str, timeout: int = TIMEOUT) -> bool:
    start = time.time()
    while time.time() - start < timeout:
        pods = get_pods_for_app(app)
        if pods and all(p.get("status", {}).get("phase") == "Running" and
                        any(c.get("ready") for c in p.get("status", {}).get("containerStatuses", []))
                        for p in pods):
            return True
        time.sleep(POLL)
    return False


def main():
    results = {}
    for sim in SIMULATORS:
        print(f"\n==> Validating simulator: {sim}")
        # deployment name is the simulator name
        deployment = sim
        app_label = sim

        print("Waiting for an unhealthy pod...")
        pod = wait_for_unhealthy(app_label)
        if not pod:
            print(f"FAIL: no unhealthy pod detected for {sim}")
            results[sim] = "no_unhealthy_pod"
            continue
        pod_name = pod["metadata"]["name"]
        reason = pod.get("status", {}).get("containerStatuses", [{}])[0].get("state", {})
        print(f"Detected unhealthy pod: {pod_name}")

        print("Waiting for isolator to label deployment with autohealer/repair-needed=true...")
        labeled = wait_for_label(deployment, "autohealer/repair-needed", "true", timeout=TIMEOUT)
        if not labeled:
            print(f"WARN: deployment {deployment} was not labeled for repair within timeout")
            results[sim] = "not_labeled"
            continue
        print("Label detected. Waiting for repairer to clear label and pods to recover...")

        cleared = wait_for_label(deployment, "autohealer/repair-needed", "", timeout=TIMEOUT)
        pods_ready = wait_for_pods_ready(app_label, timeout=TIMEOUT)

        if cleared and pods_ready:
            print(f"PASS: {sim} was repaired and pods are Ready")
            results[sim] = "repaired"
        else:
            print(f"FAIL: {sim} did not recover in time (cleared={cleared}, pods_ready={pods_ready})")
            results[sim] = f"failed(cleared={cleared},pods_ready={pods_ready})"

    print("\nSummary:")
    for k, v in results.items():
        print(f" - {k}: {v}")


if __name__ == "__main__":
    main()

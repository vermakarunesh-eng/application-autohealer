# Application Autohealer

This repository contains an automated Kubernetes self-healing demo.

## Overview

- `agent/` contains the auto-healer agents.
  - `agent_isolator.py`: detects unhealthy pods, restarts them, and marks the deployment for repair.
  - `agent_repairer.py`: watches for deployments marked for repair and attempts remediation.
- `backend/` and `frontend/` contain the application workloads.
- `k8s/` contains Kubernetes manifests for the namespace, app workloads, agents, and failure simulators.

## Auto-healing flow

When a recoverable app failure happens, the agents should do the following:

1. `autopilot-isolator` detects the unhealthy pod.
2. It restarts the unhealthy pod.
3. It labels the deployment with `autohealer/repair-needed=true` and `autohealer/failure-reason=...`.
4. `autopilot-repairer` sees the label and diagnoses the deployment.
5. If it decides the failure is due to a bad image or deployment regression, it runs `kubectl rollout undo`.
6. If repair succeeds, it clears the repair labels.

## How to test auto-repair

Use a recoverable failure in the `autohealer` namespace:

```bash
kubectl set image deployment/backend backend=gcr.io/auto-app-healer/autopilot-backend:invalidtag -n autohealer
```

Then watch the agents and workload:

```bash
kubectl get pods -n autohealer
kubectl logs -n autohealer -l app=autopilot-isolator --tail=30
kubectl logs -n autohealer -l app=autopilot-repairer --tail=30
```

## What should happen

- The backend pod fails with `ImagePullBackOff`.
- `autopilot-isolator` detects the unhealthy backend pod and restarts it.
- The backend deployment is labeled for repair.
- `autopilot-repairer` should detect the repair label and attempt a fix.
- A likely fix is `rollback_deployment` to the previously working revision.

## Notes

- The current simulator deployments (`crash-simulator`, `bad-deploy-simulator`) are intentionally failing test workloads.
- Those simulators are not useful for validating recoverable repair behavior, because they are designed to keep failing.
- Use the backend or frontend app deployments instead for a valid repair test.

## Useful commands

```bash
kubectl get pods -n autohealer
kubectl get deployments -n autohealer
kubectl describe pod <pod> -n autohealer
kubectl logs -n autohealer -l app=autopilot-isolator --tail=50
kubectl logs -n autohealer -l app=autopilot-repairer --tail=50
```

## Image registry

The manifests use `gcr.io/auto-app-healer/...` for image names. Ensure that the built images are pushed to this registry and accessible by your cluster.

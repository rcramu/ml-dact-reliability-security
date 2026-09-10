"""Pinned kubectl helpers for the Paper A local-EKS (kind) cluster.

HARD RULE: every kubectl invocation MUST pass ``--context kind-dact-local-eks``.
This machine's default kubecontext may be a production EKS cluster. Bare
``kubectl`` / ``kubectl apply`` / ``kubectl delete`` is forbidden here.
"""
from __future__ import annotations

import json
import os
import re
import subprocess
from typing import Sequence

KIND_CONTEXT = "kind-dact-local-eks"
KIND_CLUSTER = "dact-local-eks"
NAMESPACE = "dact"

BACKEND_URL = os.environ.get("DACT_BACKEND_URL", "http://127.0.0.1:8166")
MLFLOW_URL = os.environ.get("DACT_MLFLOW_URL", "http://127.0.0.1:5026")
MODEL = os.environ.get("DACT_MODEL", "churn-predictor")

_UUID_RE = re.compile(
    r"^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}$"
)


def require_uuid(value: str, label: str) -> str:
    if not _UUID_RE.match(value or ""):
        raise ValueError(f"{label} is not a UUID: {value!r}")
    return value


def kubectl(*args: str, check: bool = True, timeout: float = 60) -> subprocess.CompletedProcess:
    """Run kubectl against the kind cluster only."""
    cmd = ["kubectl", "--context", KIND_CONTEXT, *args]
    return subprocess.run(cmd, capture_output=True, text=True, check=check, timeout=timeout)


def assert_kind_context() -> None:
    """Refuse to proceed unless the named kind cluster is reachable."""
    proc = kubectl("config", "get-contexts", "-o", "name", check=False)
    names = {line.strip() for line in proc.stdout.splitlines() if line.strip()}
    if KIND_CONTEXT not in names:
        raise RuntimeError(
            f"Required kubecontext {KIND_CONTEXT!r} is not configured. "
            "Do not fall back to the current context."
        )
    info = kubectl("cluster-info", check=False)
    if info.returncode != 0:
        raise RuntimeError(
            f"Kind cluster {KIND_CLUSTER!r} is not reachable via {KIND_CONTEXT}: "
            f"{info.stderr.strip() or info.stdout.strip()}"
        )
    current = kubectl("config", "current-context", check=False)
    # Informational only — we never use current-context for mutations.
    _ = current.stdout.strip()


def ns_args() -> list[str]:
    return ["-n", NAMESPACE]


def pod_uids(app: str) -> list[str]:
    proc = kubectl(
        *ns_args(),
        "get",
        "pods",
        "-l",
        f"app={app}",
        "-o",
        "jsonpath={range .items[*]}{.metadata.uid}{'\\n'}{end}",
        check=False,
    )
    return [line.strip() for line in (proc.stdout or "").splitlines() if line.strip()]


def pod_ready_count(app: str) -> int:
    proc = kubectl(
        *ns_args(),
        "get",
        "pods",
        "-l",
        f"app={app}",
        "-o",
        "jsonpath={range .items[*]}{.status.containerStatuses[0].ready}{'\\n'}{end}",
        check=False,
    )
    return sum(1 for line in (proc.stdout or "").splitlines() if line.strip().lower() == "true")


def delete_pods_by_app(app: str) -> subprocess.CompletedProcess:
    """Delete pods for a Deployment so the ReplicaSet recreates them."""
    return kubectl(
        *ns_args(),
        "delete",
        "pod",
        "-l",
        f"app={app}",
        "--wait=false",
        "--ignore-not-found=true",
        check=False,
        timeout=30,
    )


def scale_deployment(name: str, replicas: int) -> subprocess.CompletedProcess:
    return kubectl(
        *ns_args(),
        "scale",
        f"deployment/{name}",
        f"--replicas={replicas}",
        check=False,
        timeout=30,
    )


def rollout_status(name: str, timeout_s: int = 180) -> subprocess.CompletedProcess:
    return kubectl(
        *ns_args(),
        "rollout",
        "status",
        f"deployment/{name}",
        f"--timeout={timeout_s}s",
        check=False,
        timeout=timeout_s + 15,
    )


def exec_in_deployment(deployment: str, command: Sequence[str], timeout: float = 60) -> subprocess.CompletedProcess:
    return kubectl(
        *ns_args(),
        "exec",
        f"deploy/{deployment}",
        "--",
        *command,
        check=False,
        timeout=timeout,
    )


def exec_python_in_backend(code: str, timeout: float = 180) -> subprocess.CompletedProcess:
    return exec_in_deployment("backend", ["python", "-c", code], timeout=timeout)


def psql(sql: str, timeout: float = 30) -> subprocess.CompletedProcess:
    """Run SQL inside the postgres pod using the pod's own env (no host secrets)."""
    cmd = [
        "kubectl", "--context", KIND_CONTEXT, *ns_args(),
        "exec", "-i", "deploy/postgres", "--",
        "sh", "-c", 'psql -U "$POSTGRES_USER" -d "$POSTGRES_DB" -v ON_ERROR_STOP=1',
    ]
    return subprocess.run(cmd, input=sql, capture_output=True, text=True, timeout=timeout)


def collect_environment() -> dict:
    """Host / cluster / image facts. Never includes secret values."""
    def _safe(args: list[str]) -> str:
        try:
            p = subprocess.run(args, capture_output=True, text=True, timeout=20)
            return (p.stdout or p.stderr).strip()[:4000]
        except Exception as exc:  # noqa: BLE001
            return f"{type(exc).__name__}: {exc}"

    pods = kubectl(*ns_args(), "get", "pods", "-o", "wide", check=False)
    deploys = kubectl(*ns_args(), "get", "deploy", "-o", "wide", check=False)
    images = kubectl(
        *ns_args(),
        "get",
        "deploy",
        "-o",
        "jsonpath={range .items[*]}{.metadata.name}={.spec.template.spec.containers[0].image}{'\\n'}{end}",
        check=False,
    )
    return {
        "kind_context": KIND_CONTEXT,
        "kind_cluster": KIND_CLUSTER,
        "namespace": NAMESPACE,
        "backend_url": BACKEND_URL,
        "mlflow_url": MLFLOW_URL,
        "model": MODEL,
        "uname": _safe(["uname", "-a"]),
        "sw_vers": _safe(["sw_vers"]),
        "docker_version": _safe(["docker", "version", "--format", "{{.Server.Version}}"]),
        "kubectl_client": _safe(["kubectl", "version", "--client", "--output", "yaml"]),
        "kind_version": _safe(["kind", "version"]),
        "pods": pods.stdout.strip() if pods.returncode == 0 else pods.stderr.strip(),
        "deployments": deploys.stdout.strip() if deploys.returncode == 0 else deploys.stderr.strip(),
        "images": images.stdout.strip() if images.returncode == 0 else images.stderr.strip(),
    }


def write_json(path, payload) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, default=str))

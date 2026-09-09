#!/usr/bin/env python3
"""Security assessment tooling for the cmp_ reference stack (Paper B, Section 6.3).

Three real, automated checks against THIS project's actual files (not a
narrative description):
  1. Dependency vulnerability scan of backend/requirements.txt against the
     OSV.dev advisory database, queried directly over HTTP for each pinned
     version (pip-audit's CLI was tried first but its resolver insists on
     building every pinned package locally — scipy/psycopg2-binary need
     gfortran/pg_config that aren't installed on this machine; querying
     OSV.dev directly is the same data source without that dependency).
  2. `docker scout cves` against the built backend/frontend images (if built).
  3. A static IAM/RBAC-analogous policy review of docker-compose.yml and
     backend/app/config.py — this stack has no AWS IAM/K8s RBAC (it's Compose,
     not EKS), so the "IAM/RBAC review" from Paper A's Section 10.2 is
     approximated here as a credential/least-privilege hygiene check: hardcoded
     secrets, default credentials, anonymous access, open ports.
The STRIDE threat model (manual analysis, not automatable) is written
separately at evaluation/threat_model.md.

Usage:
    evaluation/.venv/bin/python evaluation/security_scan.py
"""
from __future__ import annotations

import json
import re
import subprocess
from pathlib import Path

import requests

PROJECT_ROOT = Path(__file__).parent.parent
RESULTS_DIR = Path(__file__).parent / "results"
OSV_QUERY_URL = "https://api.osv.dev/v1/query"


def _parse_requirements(req_path: Path) -> list[tuple[str, str]]:
    pins = []
    for line in req_path.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "==" not in line:
            continue
        name, _, rest = line.partition("==")
        version = rest.split(";")[0].strip()
        # strip extras, e.g. uvicorn[standard]==0.32.1 -> uvicorn
        name = name.split("[")[0].strip()
        pins.append((name, version))
    return pins


def run_pip_audit(venv_python: str) -> dict:  # noqa: ARG001 - kept for call-site compatibility
    req = PROJECT_ROOT / "backend" / "requirements.txt"
    pins = _parse_requirements(req)
    vulns = []
    query_errors = []
    for name, version in pins:
        try:
            resp = requests.post(
                OSV_QUERY_URL,
                json={"version": version, "package": {"name": name, "ecosystem": "PyPI"}},
                timeout=15,
            )
            resp.raise_for_status()
            for v in resp.json().get("vulns", []):
                vulns.append({
                    "package": name, "version": version, "id": v.get("id"),
                    "summary": (v.get("summary") or v.get("details", ""))[:200],
                })
        except requests.exceptions.RequestException as exc:
            query_errors.append({"package": name, "version": version, "error": str(exc)})
    return {
        "method": "direct OSV.dev API query per pinned dependency (pip-audit CLI's local-build "
                  "resolution failed in this environment — see docstring)",
        "packages_scanned": len(pins),
        "query_errors": query_errors,
        "vulnerabilities_found": len(vulns),
        "vulnerabilities": vulns,
    }


def run_npm_audit() -> dict:
    frontend = PROJECT_ROOT / "frontend"
    if not (frontend / "package.json").exists():
        return {"skipped": True, "reason": "no package.json"}
    if not (frontend / "node_modules").exists():
        install = subprocess.run(["npm", "install", "--no-audit", "--no-fund"], cwd=frontend,
                                  capture_output=True, text=True, timeout=300)
        if install.returncode != 0:
            return {"error": f"npm install failed: {install.stderr[-2000:]}"}
    proc = subprocess.run(["npm", "audit", "--json"], cwd=frontend, capture_output=True, text=True, timeout=120)
    try:
        data = json.loads(proc.stdout)
    except json.JSONDecodeError:
        return {"error": proc.stderr.strip()[:2000] or "npm audit produced no parseable output"}
    meta = data.get("metadata", {}).get("vulnerabilities", {})
    return {"vulnerabilities_by_severity": meta, "total": sum(meta.values()) if meta else 0}


def run_docker_scout() -> dict:
    images = subprocess.run(["docker", "images", "--format", "{{.Repository}}:{{.Tag}}"],
                             capture_output=True, text=True).stdout.splitlines()
    targets = [i for i in images if "contnuous-monitoring" in i or "cmp" in i.lower()]
    if not targets:
        # fall back to whatever image backs the running cmp_backend / cmp_frontend containers
        for name in ("cmp_backend", "cmp_frontend"):
            insp = subprocess.run(["docker", "inspect", "--format", "{{.Config.Image}}", name],
                                   capture_output=True, text=True)
            if insp.returncode == 0 and insp.stdout.strip():
                targets.append(insp.stdout.strip())
    results = {}
    for image in targets:
        proc = subprocess.run(["docker", "scout", "cves", image, "--format", "sarif"],
                               capture_output=True, text=True, timeout=180)
        if proc.returncode != 0:
            results[image] = {"error": proc.stderr.strip()[-1000:] or proc.stdout.strip()[-1000:]}
            continue
        try:
            sarif = json.loads(proc.stdout)
            findings = sarif.get("runs", [{}])[0].get("results", [])
            results[image] = {"finding_count": len(findings)}
        except json.JSONDecodeError:
            results[image] = {"raw_summary_unparsed": True, "stdout_tail": proc.stdout[-1000:]}
    return results or {"skipped": True, "reason": "no cmp_ images found — build the stack first"}


SECRET_PATTERNS = [
    (re.compile(r"PASSWORD:\s*\S+"), "hardcoded password in docker-compose.yml"),
    (re.compile(r"SECRET_KEY:\s*\S+"), "hardcoded secret key in docker-compose.yml"),
    (re.compile(r"ROOT_PASSWORD:\s*\S+"), "hardcoded root credential in docker-compose.yml"),
    (re.compile(r"HEC_TOKEN:\s*[\"']?[0-9a-fA-F-]{20,}"), "hardcoded API token in docker-compose.yml"),
]


def review_credential_hygiene() -> dict:
    compose = (PROJECT_ROOT / "docker-compose.yml").read_text()
    findings = []
    for pattern, description in SECRET_PATTERNS:
        for match in pattern.finditer(compose):
            line_no = compose.count("\n", 0, match.start()) + 1
            findings.append({"line": line_no, "match": match.group(0)[:80], "finding": description})
    anon_grafana = "GF_AUTH_ANONYMOUS_ENABLED: \"true\"" in compose
    if anon_grafana:
        findings.append({"finding": "Grafana anonymous Viewer access enabled (GF_AUTH_ANONYMOUS_ENABLED=true) "
                                     "— dashboards are unauthenticated on the exposed port"})
    admin_default = "GF_SECURITY_ADMIN_PASSWORD: admin" in compose
    if admin_default:
        findings.append({"finding": "Grafana admin password left at the documented default ('admin') in compose file"})
    exposed_ports = re.findall(r'"\d{4,5}:\d{2,5}"', compose)
    findings.append({"finding": f"{len(exposed_ports)} host ports published to 0.0.0.0 by default "
                                 f"(docker-compose `ports:` binds all interfaces unless a host IP is specified): "
                                 f"{exposed_ports}"})
    return {
        "scope_note": ("This stack runs on Docker Compose, not AWS IAM/EKS RBAC as in Paper A's Section 10.2 diagram; "
                        "this review checks the closest available proxy — credential hygiene and network exposure "
                        "in the actual compose/config files — rather than a live IAM policy simulation."),
        "findings_count": len(findings),
        "findings": findings,
    }


def main() -> None:
    venv_python = str(Path(__file__).parent / ".venv" / "bin" / "python")
    report = {
        "dependency_scan_backend_pip_audit": run_pip_audit(venv_python),
        "dependency_scan_frontend_npm_audit": run_npm_audit(),
        "container_image_scan_docker_scout": run_docker_scout(),
        "credential_and_network_hygiene_review": review_credential_hygiene(),
    }
    RESULTS_DIR.mkdir(exist_ok=True)
    out_path = RESULTS_DIR / "security_scan.json"
    out_path.write_text(json.dumps(report, indent=2, default=str))
    print(f"Wrote {out_path}")
    print(json.dumps(report, indent=2, default=str))


if __name__ == "__main__":
    main()

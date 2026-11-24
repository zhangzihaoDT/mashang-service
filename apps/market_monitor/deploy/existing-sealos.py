"""Preflight or update the existing App Launchpad workload by immutable digest."""

import argparse
import json
import os
import re
import subprocess
from pathlib import Path

import yaml

WORKLOAD = "deployment/market-monitor"
IMAGE = re.compile(r"ghcr\.io/zhangzihaodt/mashang-market-monitor@sha256:[0-9a-f]{64}")
PULL_SECRET = "market-monitor-ghcr"
AUTH_SECRET = "market-monitor-auth"


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--kubeconfig", type=Path, required=True)
    parser.add_argument("--context", default=os.environ.get("MARKET_MONITOR_KUBE_CONTEXT"))
    parser.add_argument("--namespace", default=os.environ.get("MARKET_MONITOR_NAMESPACE"))
    parser.add_argument("--service", default=os.environ.get("MARKET_MONITOR_SERVICE"))
    parser.add_argument("--image", required=True, help="Verified GHCR image pinned by SHA-256 digest")
    parser.add_argument("--apply", action="store_true", help="Apply the validated update and wait for rollout")
    args = parser.parse_args()
    if not IMAGE.fullmatch(args.image):
        parser.error("--image must be the Market Monitor GHCR digest reference")
    if not (args.context and args.namespace and args.service):
        parser.error("specify context, namespace and the existing Sealos Service")
    command = [
        "kubectl", "--kubeconfig", str(args.kubeconfig.resolve()), "--context", args.context,
        "-n", args.namespace,
    ]

    def kubectl(*arguments, payload=None, timeout=20):
        result = subprocess.run(
            [*command, f"--request-timeout={timeout}s", *arguments],
            input=None if payload is None else json.dumps(payload),
            capture_output=True, text=True,
        )
        if result.returncode:
            raise SystemExit(result.stderr.strip())
        return result.stdout

    service = json.loads(kubectl("get", "service", args.service, "-o", "json"))
    deployment = json.loads(kubectl("get", WORKLOAD, "-o", "json"))
    if (service["metadata"]["labels"].get("cloud.sealos.io/app-deploy-manager") != "market-monitor"
            or service["spec"]["selector"] != {"app": "market-monitor"}
            or not any(port["port"] == 80 and port["targetPort"] == 80
                       and port.get("protocol", "TCP") == "TCP" for port in service["spec"]["ports"])):
        raise SystemExit("现有 Service 不再匹配已验证的路由契约。")
    if (deployment["metadata"]["labels"].get("cloud.sealos.io/app-deploy-manager") != "market-monitor"
            or deployment["spec"]["template"]["metadata"]["labels"].get("app") != "market-monitor"
            or deployment["spec"].get("replicas", 1) != 1):
        raise SystemExit("现有工作负载不再匹配已验证的单实例配置。")

    manifest = Path(__file__).with_name("sealos.yaml")
    resources = {item["kind"]: item for item in yaml.safe_load_all(manifest.read_text())}
    template = resources["Deployment"]["spec"]["template"]["spec"]
    claim = resources["PersistentVolumeClaim"]
    original = deployment["spec"]["template"]["spec"]
    previous = {c["name"]: c["image"] for c in original["containers"]}
    if set(previous) not in ({"market-monitor"}, {"market-monitor", "snapshot-writer"}):
        raise SystemExit("现有容器清单与已验证的部署不符。")

    template["containers"][0]["name"] = "market-monitor"
    for container in template["containers"]:
        container["image"] = args.image
    template["imagePullSecrets"] = [
        *[entry for entry in original.get("imagePullSecrets") or [] if entry["name"] != PULL_SECRET],
        {"name": PULL_SECRET},
    ]
    pod_patch = [
        {"op": "test", "path": "/metadata/resourceVersion", "value": deployment["metadata"]["resourceVersion"]},
        {"op": "add", "path": "/spec/strategy", "value": {"type": "Recreate"}},
    ]
    pod_patch.extend(
        {"op": "add", "path": f"/spec/template/spec/{key}", "value": value}
        for key, value in template.items()
    )
    patch_command = ("patch", WORKLOAD, "--type=json", "--patch-file=/dev/stdin")
    preview = json.loads(kubectl(*patch_command, "--dry-run=server", "-o", "json", payload=pod_patch))
    pod_template = preview["spec"]["template"]
    kubectl("create", "--dry-run=server", "-f", "-", "-o", "name", payload={
        "apiVersion": "v1",
        "kind": "Pod",
        "metadata": {"name": "market-monitor-preflight", "labels": pod_template["metadata"]["labels"]},
        "spec": pod_template["spec"],
    })

    claim_name = claim["metadata"]["name"]
    claim_exists = kubectl("get", "pvc", claim_name, "--ignore-not-found", "-o", "name").strip()
    if not claim_exists:
        kubectl("create", "--dry-run=server", "-f", "-", "-o", "name", payload=claim)
    print(f"服务端预检通过。当前镜像 {previous['market-monitor']}。目标镜像 {args.image}。")
    if not args.apply:
        return

    if kubectl("get", "secret", PULL_SECRET, "-o", "jsonpath={.type}").strip() != "kubernetes.io/dockerconfigjson":
        raise SystemExit("请先配置 GHCR 只读镜像拉取 Secret。")
    kubectl("get", "secret", AUTH_SECRET, "-o", "name")
    if not claim_exists:
        kubectl("create", "-f", "-", "-o", "name", payload=claim)
    kubectl(*patch_command, "-o", "name", payload=pod_patch)
    kubectl("rollout", "status", WORKLOAD, "--timeout=180s", timeout=190)
    pods = json.loads(kubectl("get", "pods", "-l", "app=market-monitor", "-o", "json"))["items"]
    for pod in pods:
        if pod["metadata"].get("deletionTimestamp"):
            continue
        statuses = pod["status"].get("containerStatuses", [])
        if (len(statuses) == 2 and all(status.get("ready") for status in statuses)
                and all(status.get("imageID", "").endswith(args.image.split("@", 1)[1]) for status in statuses)):
            print(f"镜像摘要、容器就绪及 TCP 80 探针验收通过。Pod {pod['metadata']['name']}。")
            return
    raise SystemExit("滚动部署已结束，需核对运行容器的镜像摘要和就绪状态。")


if __name__ == "__main__":
    main()

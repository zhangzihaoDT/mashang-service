# Market Monitor 私有 GHCR 发布

| 项目 | 固定值 |
| --- | --- |
| 源仓库 | `zhangzihaoDT/mashang-service` |
| 镜像 | `ghcr.io/zhangzihaodt/mashang-market-monitor:0.1.0` |
| 平台 | `linux/amd64` |
| 可见性 | Private |
| Sealos | 现有 App Launchpad 工作负载和 Service |
| 拉取 Secret | `market-monitor-ghcr` |

## 1. 验证 Package 权限并发布

在源仓库的 **Actions → Market Monitor GHCR** 选择 `main`。

1. 先运行 `operation=bootstrap`。这个镜像只含访问检查标记。工作流用 `GITHUB_TOKEN` 建立 Package，并验证 REST API 报告 `private`、匿名拉取被拒绝。
2. 在 [Package Settings](https://github.com/users/zhangzihaoDT/packages/container/package/mashang-market-monitor/settings) 确认 **Private**，关闭从公开源码仓库继承访问权限。保留仓库关联及 OCI 来源标签。在 **Manage Actions access** 直接给 `zhangzihaoDT/mashang-service` 授权写入。在 **Manage access** 仅给部署账号 Read。可见性与继承权限是单独的设置。[GitHub Package 可见性与权限](https://docs.github.com/en/packages/learn-github-packages/configuring-a-packages-access-control-and-visibility)
3. 用部署账号的只读 PAT 拉取 `access-bootstrap` 以验证 Read。用匿名身份和一个未获授权的 GitHub 账号重复拉取，预期均拒绝。仅在权属核验通过后运行 `operation=release`、`version=0.1.0`，勾选 `access_reviewed`。
4. 发布工作流检查构建内容、`linux/amd64`、版本标签和匿名拉取。记录运行摘要中仓库返回的 **digest reference**。后续部署使用摘要，回滚沿用历史摘要。使用已有版本标签的发布会被拒绝。

构建上下文限定为 `apps/market_monitor`。`.dockerignore` 只允许已列出的 Python、配置和静态文件。发布前再次检查镜像内的应用文件，TP&MIX、MIIT 快照、kubeconfig、认证文件和其他仓库文件通过部署端的独立通道提供。

## 2. 配置 Sealos 只读凭据

用获得 Package Read 权限的账号，在 [GitHub 生成 classic PAT](https://github.com/settings/tokens/new)，选择 **仅 `read:packages`**，设置合适的有效期。[GitHub 容器仓库认证](https://docs.github.com/en/packages/working-with-a-github-packages-registry/working-with-the-container-registry#authenticating-to-the-container-registry)

从仓库根目录，在可信终端运行以下命令。输入过程隐藏口令。脚本通过 GitHub API 核对发证账号、实际 OAuth scope 和 Package 可见性，随后直接经标准输入创建 Kubernetes Secret。保持终端关闭命令和输入记录，禁止在管道中加 `tee`。

```bash
export KUBECONFIG="$PWD/.local/market-monitor/kubeconfig.yaml"
export MARKET_MONITOR_KUBE_CONTEXT="填入实际 Sealos context"
export MARKET_MONITOR_NAMESPACE="填入实际 Sealos namespace"
export MARKET_MONITOR_SERVICE="填入实际 Sealos Service 名称"
export MARKET_MONITOR_GHCR_USER="填入已获 Package Read 权限的 GitHub 用户名"
set -o pipefail
.venv/bin/python -c '
import base64, getpass, json, os, urllib.request
username = os.environ["MARKET_MONITOR_GHCR_USER"]
token = getpass.getpass("GHCR classic PAT (only read:packages): ")
headers = {"Authorization": f"Bearer {token}", "Accept": "application/vnd.github+json"}
with urllib.request.urlopen(urllib.request.Request("https://api.github.com/user", headers=headers), timeout=15) as response:
    scopes = {item.strip() for item in response.headers.get("X-OAuth-Scopes", "").split(",") if item.strip()}
    if scopes != {"read:packages"} or json.load(response)["login"].casefold() != username.casefold():
        raise SystemExit("PAT 账号或授权范围不符")
package = "https://api.github.com/users/zhangzihaoDT/packages/container/mashang-market-monitor"
with urllib.request.urlopen(urllib.request.Request(package, headers=headers), timeout=15) as response:
    if json.load(response)["visibility"] != "private":
        raise SystemExit("Package 可见性不是 Private")
auth = base64.b64encode(f"{username}:{token}".encode()).decode()
print(json.dumps({"auths": {"ghcr.io": {"auth": auth}}}))
' | kubectl --context "$MARKET_MONITOR_KUBE_CONTEXT" -n "$MARKET_MONITOR_NAMESPACE" create secret generic market-monitor-ghcr \
  --type=kubernetes.io/dockerconfigjson --from-file=.dockerconfigjson=/dev/stdin \
  --dry-run=client -o json |
  kubectl --context "$MARKET_MONITOR_KUBE_CONTEXT" -n "$MARKET_MONITOR_NAMESPACE" apply --server-side -f -
```

在已启用系统凭据帮助程序的本机 Docker 上，可用 `docker login ghcr.io --username <用户名> --password-stdin` 和 `docker pull --platform linux/amd64 ghcr.io/zhangzihaodt/mashang-market-monitor:access-bootstrap` 验证授权账号。未授权账号使用其独立凭据验证，避免复用已登录的 Docker 配置。

另按 [部署说明](README.md#2-准备权限与-https-入口) 配置独立 Web 账号 Secret `market-monitor-auth`。拉取 PAT 只用于容器仓库。

## 3. 更新并验收现有 Sealos 应用

将 `MARKET_MONITOR_IMAGE` 设为发布工作流确认的摘要引用 `ghcr.io/zhangzihaodt/mashang-market-monitor@sha256:…`。默认执行服务端预检，增加 `--apply` 时替换现有 Deployment。命令复用 `MARKET_MONITOR_SERVICE` 指定的现有 Service，且只更新该应用的工作负载和快照 PVC。

```sh
.venv/bin/python apps/market_monitor/deploy/existing-sealos.py \
  --kubeconfig .local/market-monitor/kubeconfig.yaml --image "${MARKET_MONITOR_IMAGE:?}"
.venv/bin/python apps/market_monitor/deploy/existing-sealos.py \
  --kubeconfig .local/market-monitor/kubeconfig.yaml --image "${MARKET_MONITOR_IMAGE:?}" --apply
```

截至首次检查，现有 Service 可用并转发 TCP 80，工作区中尚无指向该 Service 的 Ingress。若 App Launchpad 已分配可用地址，沿用该设置。否则，在 `market-monitor` 的现有端口配置启用 HTTPS 公网访问，使用 Sealos 分配的 URL 或已确认的专属域名。[Sealos 公网访问](https://sealos.io/docs/guides/app-deploy/add-a-domain/)

```sh
export KUBECONFIG="$PWD/.local/market-monitor/kubeconfig.yaml"
sh apps/market_monitor/deploy/sync-sealos.sh
```

通过原 HTTPS 入口确认匿名请求 `/`、`/app.js`、`/api/v1/status`、`/api/v1/insurance/<month>` 和 `/api/v1/miit/<month>` 返回 401。使用独立 Web 账号验证页面与数据接口返回 200，并核对两路最新覆盖月及数据。查看 Service 的 EndpointSlice，确认就绪端点指向新 Pod。

## 4. 回滚

记录部署前的修订号及镜像摘要。用上一已验证的应用摘要重新运行部署命令，或按既有修订回退整个 Pod 模板：

```sh
kubectl --context "$MARKET_MONITOR_KUBE_CONTEXT" -n "$MARKET_MONITOR_NAMESPACE" rollout history deployment/market-monitor
kubectl --context "$MARKET_MONITOR_KUBE_CONTEXT" -n "$MARKET_MONITOR_NAMESPACE" rollout undo deployment/market-monitor --to-revision=<修订号>
kubectl --context "$MARKET_MONITOR_KUBE_CONTEXT" -n "$MARKET_MONITOR_NAMESPACE" rollout status deployment/market-monitor
```

首次上线前的修订为 Nginx 占位服务。回滚保留当前 Service、入口和快照 PVC。已验证的旧镜像摘要及其版本应保留在 GHCR。

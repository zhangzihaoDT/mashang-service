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

首次需要 Package 管理员初始化独立权限的 Private Package。试运行发现，从公开仓库首次用 `GITHUB_TOKEN` 推送的检查标记允许匿名拉取。正式发布工作流因此要求目标包已存在，并在推送前检查 Private 元数据和匿名拒绝。

1. Package 管理员先使用临时 classic PAT 的 `write:packages` 权限直接在 GHCR 初始化同名包。第一次只推中性的 `access-bootstrap` 标记，镜像构建时省略源码关联标签。使用系统凭据帮助程序和隐藏输入的 `docker login ghcr.io --username <包管理员账号> --password-stdin`。完成初始化后撤销临时写入 PAT。生产拉取另用下一节的只读 PAT。
2. 在 [Package Settings](https://github.com/users/zhangzihaoDT/packages/container/package/mashang-market-monitor/settings) 确认 **Private**，再手动关联 `zhangzihaoDT/mashang-service`。保持该公开仓库的访问权限继承关闭。通过 **Manage Actions access** 单独授予源仓库 Write，在 **Manage access** 仅给部署账号 Read。可见性与继承权限是单独的设置。[GitHub Package 可见性与权限](https://docs.github.com/en/packages/learn-github-packages/configuring-a-packages-access-control-and-visibility)
3. 在源仓库的 **Actions → Market Monitor GHCR** 选择 `main`，运行 `operation=verify`。工作流核验 Private、匿名拒绝、固定平台以及 `GITHUB_TOKEN` 的实际拉取权限。另用部署账号的只读 PAT 拉取 `access-bootstrap`，用未获授权账号核对拉取拒绝。
4. 权限核验通过后运行 `operation=release`、`version=0.1.0`，勾选 `access_reviewed`。工作流用 `GITHUB_TOKEN` 发布正式镜像，并再次核验匿名拒绝。
5. 保存运行摘要中的 **digest reference**。部署和回滚使用历史摘要。已有版本标签的发布会被拒绝。

管理员准备标记镜像的命令如下。使用终端中已安全登录的临时写入凭据执行最后一行。

```sh
bootstrap_dir=$(mktemp -d)
printf '%s\n' 'FROM scratch' 'COPY marker /market-monitor-ghcr-bootstrap' > "$bootstrap_dir/Dockerfile"
printf '%s\n' 'GHCR access check only' > "$bootstrap_dir/marker"
docker buildx build --load --platform linux/amd64 \
  -t ghcr.io/zhangzihaodt/mashang-market-monitor:access-bootstrap "$bootstrap_dir"
docker push ghcr.io/zhangzihaodt/mashang-market-monitor:access-bootstrap
```

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

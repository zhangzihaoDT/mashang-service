# Sealos 部署

应用独立部署在 Sealos。镜像只有 Web、API 和快照安装入口。月度生成任务在有权读取两路资产的数据宿主运行，部署通过 Kubernetes API 把看板投影交给写入容器。Sealos Web 容器只读挂载快照卷；两端都复用 `schema_version=1`。数据刷新无需重新构建镜像或重启看板。

## 1. 构建独立镜像

在仓库根目录执行。使用 Sealos 可以拉取的私有镜像仓库，并为每次发布使用唯一标签或镜像摘要。

```sh
docker buildx build --platform linux/amd64 --push \
  -t "$MARKET_MONITOR_IMAGE" \
  -f apps/market_monitor/deploy/Dockerfile apps/market_monitor
```

构建上下文仅需应用代码。在运行过本地预览的目录构建时，`.dockerignore` 会排除 `var/` 等运行产物。

## 2. 准备权限与 HTTPS 入口

使用该应用独立的 Sealos workspace/namespace，并设置 `MARKET_MONITOR_KUBE_CONTEXT` 与 `MARKET_MONITOR_NAMESPACE`。

- 在该命名空间预建 `market-monitor-ghcr` 拉取 Secret。详见 [私有 GHCR 发布与验收](ghcr.md)。
- 在可信终端为每位只读用户生成独立的高熵口令，例如 `secrets.token_urlsafe(32)`。保存口令的 SHA-256 十六进制摘要，文件内容形如 `{"reader":"<64 位小写十六进制摘要>"}`。口令通过私密渠道交付给用户。
- 以该文件建立门禁。应用启动时读入账号，变更后对实际工作负载执行 `kubectl rollout restart`。下文的 context 和 namespace 参数同样适用于该命令。
- 使用该 Sealos 工作区分配的独立域名或自有域名，并配置该域名对应的 Ingress class 和 TLS Secret。域名绑定和证书流程见 [Sealos 的域名文档](https://sealos.io/docs/guides/app-deploy/add-a-domain/) 与 [证书文档](https://sealos.io/docs/guides/app-deploy/custom-certificates/)。

```sh
kubectl --context "$MARKET_MONITOR_KUBE_CONTEXT" -n "$MARKET_MONITOR_NAMESPACE" \
  create secret generic market-monitor-auth --from-file=accounts.json="$MARKET_MONITOR_AUTH_FILE"
```

## 3. 应用部署配置

### 复用已建的 App Launchpad 入口

现有 Service 以 `app=market-monitor` 选中工作负载，转发 `80 → 80`。继续使用 Sealos 管理的 Service、端口名和对应的 HTTPS 入口。先确认当前工作负载和端点：

```sh
kubectl --context "$MARKET_MONITOR_KUBE_CONTEXT" -n "$MARKET_MONITOR_NAMESPACE" \
  get deployment,statefulset,pod -l app=market-monitor
kubectl --context "$MARKET_MONITOR_KUBE_CONTEXT" -n "$MARKET_MONITOR_NAMESPACE" \
  get endpointslices -l "kubernetes.io/service-name=$MARKET_MONITOR_SERVICE"
```

在原工作负载上更新镜像，并参考 `sealos.yaml` 中的 Pod 模板配置认证 Secret、快照卷和 `snapshot-writer`。新版镜像默认监听 `0.0.0.0:80`，Web 容器以非 root 用户运行，Pod 模板通过独立网络命名空间的 `net.ipv4.ip_unprivileged_port_start=80` 允许绑定此端口。复用 App Launchpad 入口时，仅更新实际工作负载及其依赖，跳过下面创建独立 Service 和 Ingress 的步骤。[Sealos 更新应用](https://sealos.io/docs/guides/app-deploy/update-apps/) · [Kubernetes Pod 安全标准](https://kubernetes.io/docs/concepts/security/pod-security-standards/#restricted)

### 新建独立入口

设置以下变量后执行。YAML 声明独立的 Deployment、Service、Ingress 与快照 PVC。若工作区没有默认 StorageClass，在 PVC 中指定工作区提供的 StorageClass。

```sh
sed -e "s|__IMAGE__|${MARKET_MONITOR_IMAGE:?}|g" \
    -e "s|__HOST__|${MARKET_MONITOR_HOST:?}|g" \
    -e "s|__INGRESS_CLASS__|${MARKET_MONITOR_INGRESS_CLASS:?}|g" \
    -e "s|__TLS_SECRET__|${MARKET_MONITOR_TLS_SECRET:?}|g" \
    apps/market_monitor/deploy/sealos.yaml |
  kubectl --context "${MARKET_MONITOR_KUBE_CONTEXT:?}" \
    -n "${MARKET_MONITOR_NAMESPACE:?}" apply -f -

kubectl --context "$MARKET_MONITOR_KUBE_CONTEXT" -n "$MARKET_MONITOR_NAMESPACE" \
  rollout status deployment/market-monitor
```

## 4. 填充和月度更新

在有 TP&MIX Parquet、registry 和 MIIT canonical 产物的数据宿主上执行：

```sh
sh apps/market_monitor/deploy/sync-sealos.sh
```

脚本默认面向 `deployment/market-monitor`。复用已有工作负载时，将 `MARKET_MONITOR_WORKLOAD` 设为实际对象，例如 `statefulset/market-monitor`。

两路数据以月度交付为触发点。将上面的命令接在每月上游产物已发布且可读之后，也可以为两路各自调用 `sync-sealos.sh insurance` 或 `sync-sealos.sh miit`。调度用户需要目标应用的 Kubernetes exec 权限。刷新或上传单路失败即返回非零，其他成功来源可照常更新；线上保留该路上一份成功快照。重试会重新读取上游并原子替换通过验证的投影。

验收时打开 `https://$MARKET_MONITOR_HOST/`，验证无凭据的页面及 API 返回 401，账号可登录，`/api/v1/status` 两路显示各自的覆盖时间。对一次快照刷新验证 URL 无变化且看板读取到更新后的覆盖。Web 用户只具备 HTTP 只读权限，快照写入走目标 namespace 的 Kubernetes 权限。

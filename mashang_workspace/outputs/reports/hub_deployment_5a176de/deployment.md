# Hub 镜像更新验收

日期：2026-10-10，Asia/Shanghai。

- 源码提交：`5a176de1989af000d4d072d8edeb90cfbe3ff607`。
- 镜像：`docker.io/byte1717712/mashang-hub:0.3.2-5a176de`，平台 `linux/amd64`。
- 远端 manifest：`sha256:afb293d445f032ca3b96b21af5cf8d84de47a078a4a40f2487da7be273f4c2f8`。
- Sealos：Beijing / `ns-m8unek1g` / `mashang-hub`，Pod `mashang-hub-0` running，restart count 0。
- 原镜像：`docker.io/byte1717712/mashang-hub:0.3.2-b6ccec3`。
- 保留单实例、200m CPU、256Mi 内存、端口 3000、原 HTTPS 域名及 `/data` 1Gi 卷。
- 新增 `TASK_EXECUTION_DEADLINE_MS=900000`、`TASK_VERIFIED_EXECUTION_DEADLINE_MS=1800000`、`TASK_PROGRESS_TIMEOUT_MS=180000`；旧 `TASK_TIMEOUT_MS=180000` 由优先级更高的 execution 配置覆盖。原认证与签名配置保持原值。
- Pod 内 server.mjs SHA-256：`386de89ec837f88dc0671122f11a7126a91a67cf53701760856f1d36790da6be`，与本地构建源码一致。
- Pod 内 executionPolicy 实测：query 900000ms / verified 1800000ms / progress notification 180000ms。
- 线上无工具调用探测返回 `HUB_TIMEOUT_FIX_5A176DE_OK`，5.9 秒完成；task `task_96e086ba-e9e6-490f-9016-9710072f3778` 为 COMPLETED，保存的 policy 为 query / executionDeadlineMs 900000。
- Mac Worker Online，模型列表正常。
- SQLite integrity_check = ok；原任务 `task_ede35ce5-b63d-499c-a558-b0358572105d` 记录保留为 FAILED（历史 TIMEOUT 的通用存储状态），未重放该业务任务。
- 更新后数据库一致性快照：Pod `/data/tasks-5a176de-acceptance-20261010.sqlite`，通过官方 task-backup 入口生成，权限 0600。
- 本次线上仅验证无工具调用请求；取消、断线恢复、重启恢复和自动预算提升已在部署前本地集成测试通过，未在线上故意触发超时。

截图：`verification.jpg`（Pod 验证与数据库快照）、`online.jpg`（Worker Online 与完成探测）。不包含认证凭据。

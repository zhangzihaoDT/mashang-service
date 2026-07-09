# Auto Launch — MOVED

此目录已迁移至 `auto_launch/`。

迁移原因：auto_launch 从 workspace 能力模块升级为独立 service 架构。

- **新路径**: `auto_launch/`
- **新 CLI**: `python -m auto_launch.cli daily`
- **测试**: `pytest auto_launch/tests/`
- **配置**: `auto_launch/configs/`
- **Python 源码**: `auto_launch/src/`

本目录已冻结，不再维护。所有功能请通过新路径使用。

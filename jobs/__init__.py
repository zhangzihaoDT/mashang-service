"""jobs — 确定性执行契约层。

Service 侧唯一的 Research Application job 执行边界：声明式 job 定义 +
参数白名单 + 固定 argv 执行 + 状态/摘要/artifact 契约。

Hub（Control Plane）负责调度，Worker（Execution Gateway）负责调用；
本层只负责「校验并确定性执行」，不承担自然语言路由或会话管理。
"""

from jobs.adapter import load_jobs, run_job, validate_params  # noqa: F401

__all__ = ["load_jobs", "run_job", "validate_params"]

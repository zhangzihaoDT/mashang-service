import datetime
import subprocess
import sys
from pathlib import Path

from .report_generator import ReportGenerator

REPO_ROOT = Path(__file__).resolve().parents[1]
UPDATER_DIR = REPO_ROOT / "dataset" / "updater"
UPDATER_SCRIPT = UPDATER_DIR / "update_all_datasets.py"
SYNC_SCRIPT = REPO_ROOT / "scripts" / "skills_order_observation_daily.py"


class FastPathTool:
    def run(
        self,
        config: dict,
        user_query: str,
        memory_context: dict | None = None,
    ) -> dict:
        kind = str((config or {}).get("type") or "")
        if kind == "small_talk_contextual":
            ctx = memory_context if isinstance(memory_context, dict) else {}
            facts = ctx.get("facts") if isinstance(ctx.get("facts"), dict) else {}
            working = ctx.get("working_memory") if isinstance(ctx.get("working_memory"), dict) else {}
            logs = ctx.get("execution_log") if isinstance(ctx.get("execution_log"), list) else []
            recent_queries: list[str] = []
            for item in logs[-3:]:
                if not isinstance(item, dict):
                    continue
                q = str(item.get("query") or "").strip()
                if q:
                    recent_queries.append(q)
            memory_preview = "；".join(recent_queries) if recent_queries else ""
            fact_keys = [str(k) for k in list(facts.keys())[:3]]
            fact_preview = "、".join(fact_keys)
            focus_dimension = str(working.get("focus_dimension") or "").strip()
            if memory_preview and fact_preview and focus_dimension:
                answer = (
                    f"收到，干得漂亮！你最近在关注：{memory_preview}。"
                    f"我们当前焦点是 {focus_dimension}，已沉淀结论包括：{fact_preview}。要继续深入吗？"
                )
            elif memory_preview and fact_preview:
                answer = f"收到，干得漂亮！你最近在关注：{memory_preview}。已沉淀结论包括：{fact_preview}。要继续深入吗？"
            elif memory_preview:
                answer = f"收到，干得漂亮！我记得你最近在关注：{memory_preview}。需要我继续沿这个方向分析吗？"
            elif fact_preview:
                answer = f"收到，干得漂亮！当前已沉淀结论包括：{fact_preview}。要不要继续深入下一层？"
            else:
                answer = "收到，干得漂亮！如果你愿意，我可以继续帮你做下一步分析。"
            return {
                "type": "fast_path",
                "kind": "small_talk_contextual",
                "recent_queries": recent_queries,
                "facts_snapshot": facts,
                "working_memory_snapshot": working,
                "answer": answer,
                "question": str(user_query or ""),
            }
        if kind == "current_iso_week":
            today = datetime.date.today()
            iso = today.isocalendar()
            return {
                "type": "fast_path",
                "kind": "current_iso_week",
                "date": today.isoformat(),
                "iso_year": int(iso.year),
                "iso_week": int(iso.week),
                "iso_weekday": int(iso.weekday),
                "answer": f"今天是 {today.isoformat()}，ISO 周数为 {int(iso.year)}-W{int(iso.week):02d}。",
                "question": str(user_query or ""),
            }
        if kind == "data_update":
            scope = (config.get("scope") or "all").strip().lower()
            return self._run_data_update(scope, user_query)
        if kind == "data_sync":
            scope = (config.get("scope") or "all").strip().lower()
            return self._run_data_sync(scope, user_query)
        if kind == "generate_report":
            rg = ReportGenerator()
            logs_dir = Path(__file__).resolve().parents[1] / "logs"
            saved_path = logs_dir / "last_result.parquet"
            ctx = memory_context if isinstance(memory_context, dict) else {}
            raw_facts = ctx.get("facts")
            facts = list(raw_facts) if isinstance(raw_facts, list) else []

            if saved_path.exists():
                try:
                    import pandas as pd
                    df = pd.read_parquet(saved_path)
                    title = "完整数据报告"
                    caption = f"共 {len(df)} 行 | 来源: last_result.parquet"
                    out_path = rg.generate_from_dataframe(df, title=title, caption=caption, save=True)
                    return {
                        "type": "fast_path",
                        "kind": "generate_report",
                        "report_path": out_path,
                        "answer": f"报告已生成: {out_path}",
                        "question": str(user_query or ""),
                    }
                except Exception as e:
                    return {
                        "type": "fast_path",
                        "kind": "generate_report",
                        "report_path": "",
                        "answer": f"读取保存的数据失败: {e}",
                        "question": str(user_query or ""),
                    }

            if facts:
                out_path = rg.generate_from_facts(facts, title="数据分析报告", save=True)
                return {
                    "type": "fast_path",
                    "kind": "generate_report",
                    "report_path": out_path,
                    "answer": f"报告已生成(基于内存事实): {out_path}",
                    "question": str(user_query or ""),
                }

            return {
                "type": "fast_path",
                "kind": "generate_report",
                "report_path": "",
                "answer": "暂无可输出的数据，请先执行分析查询。",
                "question": str(user_query or ""),
            }
        if kind != "numeric_ratio":
            return {"type": "fast_path", "error": "unsupported_type", "message": f"不支持的 fast_path 类型: {kind}"}
        try:
            current = float(config.get("current"))
            base = float(config.get("base"))
        except Exception:
            return {"type": "fast_path", "error": "invalid_config", "message": "fast_path 参数无效"}

        delta = current - base
        ratio = None if base == 0 else (delta / base)
        direction = "提升" if delta >= 0 else "下降"
        ratio_pct = None if ratio is None else round(ratio * 100, 2)
        return {
            "type": "fast_path",
            "kind": "numeric_ratio",
            "current": current,
            "base": base,
            "delta": round(delta, 6),
            "direction": direction,
            "ratio": ratio,
            "ratio_pct": ratio_pct,
            "answer": (
                f"{current:g} 相比 {base:g}{direction}"
                + ("无法计算百分比（基数为0）。" if ratio_pct is None else f" {abs(ratio_pct):g}%")
            ),
            "question": str(user_query or ""),
        }

    def _run_data_update(self, scope: str, user_query: str) -> dict:
        steps: list[dict] = []
        success = True

        order_max_date = None
        config_updated = False

        if scope == "order" or scope == "all":
            steps.append({"step": "order_data", "status": "running"})
            try:
                r = subprocess.run(
                    [sys.executable, str(UPDATER_DIR / "order_data_to_parquet.py"),
                     "--timeout", "600"],
                    cwd=str(REPO_ROOT), text=True, timeout=900,
                )
                if r.returncode != 0:
                    steps[-1]["status"] = "failed"
                else:
                    steps[-1]["status"] = "done"
                    try:
                        import pandas as pd
                        odf = pd.read_parquet(str(REPO_ROOT / "dataset" / "order_data.parquet"))
                        for col in ["lock_time", "delivery_date", "order_create_date"]:
                            if col in odf.columns:
                                mx = pd.to_datetime(odf[col].dropna(), errors="coerce").max()
                                if pd.notna(mx):
                                    order_max_date = mx.strftime("%Y-%m-%d")
                                    break
                    except Exception:
                        pass
            except subprocess.TimeoutExpired:
                steps[-1]["status"] = "timeout"
                success = False
            except Exception as e:
                steps[-1]["status"] = "failed"
                steps[-1]["error"] = str(e)
                success = False

        if scope == "config" or scope == "all":
            steps.append({"step": "config_attribute", "status": "running"})
            try:
                r = subprocess.run(
                    [sys.executable, str(UPDATER_DIR / "order_config_to_parquet.py"),
                     "--force", "--timeout", "600"],
                    cwd=str(REPO_ROOT), text=True, timeout=900,
                )
                if r.returncode == 0:
                    steps[-1]["status"] = "done"
                    config_updated = True
                else:
                    steps[-1]["status"] = "failed"
            except Exception as e:
                steps[-1]["status"] = "failed"
                steps[-1]["error"] = str(e)

        if scope == "lock" or scope == "all":
            steps.append({"step": "lock_attribution", "status": "running"})
            try:
                r = subprocess.run(
                    [sys.executable, str(UPDATER_DIR / "lock_attribution_data_to_parquet.py"),
                     "--timeout", "600"],
                    cwd=str(REPO_ROOT), text=True, timeout=900,
                )
                steps[-1]["status"] = "done" if r.returncode == 0 else "failed"
            except Exception as e:
                steps[-1]["status"] = "failed"
                steps[-1]["error"] = str(e)

        done_steps = [s for s in steps if s["status"] == "done"]
        failed_steps = [s for s in steps if s["status"] != "done"]

        parts = []
        if order_max_date:
            parts.append(f"订单数据已更新至 {order_max_date}")
        elif any(s["step"] == "order_data" and s["status"] == "done" for s in steps):
            parts.append("订单数据已更新")
        if config_updated:
            parts.append("选配数据已更新")
        if any(s["step"] == "lock_attribution" and s["status"] == "done" for s in steps):
            parts.append("锁单归因数据已更新")

        if not parts:
            parts.append("无数据更新")

        summary = "；".join(parts)
        if failed_steps:
            summary += "。" + "；".join(f"{s['step']}失败({s['status']})" for s in failed_steps)
        else:
            summary += "。"
        return {
            "type": "fast_path",
            "kind": "data_update",
            "scope": scope,
            "steps": steps,
            "success": success,
            "_order_max_date": order_max_date,
            "_config_updated": config_updated,
            "answer": summary,
            "question": str(user_query or ""),
        }

    def _run_data_sync(self, scope: str, user_query: str) -> dict:
        result = self._run_data_update(scope, user_query)
        steps: list[dict] = result["steps"]
        success: bool = result["success"]
        order_max_date = result.get("_order_max_date")
        config_updated = result.get("_config_updated", False)

        q = str(user_query or "")
        push_requested = (
            any(k in q for k in ["推送", "发送", "通知"])
            and not any(k in q for k in ["不推送", "不发送", "不通知", "dry-run", "dry run"])
        )

        order_done = any(
            s["step"] == "order_data" and s["status"] == "done" for s in steps
        )
        if order_done:
            steps.append({"step": "sync_observation", "status": "running"})
            try:
                r = subprocess.run(
                    [sys.executable, str(SYNC_SCRIPT)],
                    cwd=str(REPO_ROOT), text=True, timeout=120,
                )
                steps[-1]["status"] = "done" if r.returncode == 0 else "failed"
            except Exception as e:
                steps[-1]["status"] = "failed"
                steps[-1]["error"] = str(e)

        if success:
            steps.append({"step": "sync_observation_mtd", "status": "running"})
            try:
                mtd_args = [sys.executable, str(SYNC_SCRIPT), "--mtd"]
                if not push_requested:
                    mtd_args.append("--dry-run")
                r = subprocess.run(
                    mtd_args,
                    cwd=str(REPO_ROOT), capture_output=True, text=True, timeout=120,
                )
                steps[-1]["status"] = "done" if r.returncode == 0 else "failed"
                if r.returncode != 0:
                    steps[-1]["error"] = r.stderr[-200:] if r.stderr else "exit code != 0"
            except Exception as e:
                steps[-1]["status"] = "failed"
                steps[-1]["error"] = str(e)

        done_steps = [s for s in steps if s["status"] == "done"]
        failed_steps = [s for s in steps if s["status"] != "done"]

        parts = []
        if order_max_date:
            parts.append(f"订单数据已更新至 {order_max_date}")
        elif any(s["step"] == "order_data" and s["status"] == "done" for s in steps):
            parts.append("订单数据已更新")
        if config_updated:
            parts.append("选配数据已更新")
        if any(s["step"] == "lock_attribution" and s["status"] == "done" for s in steps):
            parts.append("锁单归因数据已更新")
        if any(s["step"] == "sync_observation" and s["status"] == "done" for s in steps):
            parts.append("同步观察已执行")
        if any(s["step"] == "sync_observation_mtd" and s["status"] == "done" for s in steps):
            parts.append("MTD月累计观察已执行")

        if not parts:
            parts.append("无数据更新")

        summary = "；".join(parts)
        if failed_steps:
            summary += "。" + "；".join(f"{s['step']}失败({s['status']})" for s in failed_steps)
        else:
            summary += "。"
        return {
            "type": "fast_path",
            "kind": "data_sync",
            "scope": scope,
            "steps": steps,
            "success": success and all(
                s["status"] == "done"
                for s in steps
                if s["step"].startswith("sync_observation")
            ),
            "answer": summary,
            "question": str(user_query or ""),
        }


FAST_PATH_TOOL_SCHEMA = {
    "type": "function",
    "function": {
        "name": "run_fast_path",
        "description": "执行轻量 Fast Path 计算（如数字环比提升、数据更新、获取当前日期 ISO 周数）。",
        "parameters": {
            "type": "object",
            "properties": {
                "config": {
                    "type": "object",
                    "properties": {
                        "type": {"type": "string", "enum": ["numeric_ratio", "current_iso_week", "small_talk_contextual", "data_update", "data_sync"]},
                        "scope": {"type": "string", "description": "更新范围：all / order / config / lock"},
                        "current": {"type": "number"},
                        "base": {"type": "number"},
                    },
                    "required": ["type"],
                },
                "user_query": {"type": "string"},
            },
            "required": ["config"],
        },
    },
}

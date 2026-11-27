#!/usr/bin/env python3
"""Prepare, render, or review the fixed CPCA market retail poster."""

import argparse
import hashlib
import json
import math
import os
import re
import shutil
import sys
from datetime import date
from decimal import Decimal
from pathlib import Path
from uuid import uuid4

from PIL import Image

ROOT = Path(__file__).resolve().parents[2]
SKILL = ROOT / ".opencode/skills/cpca-market-retail-poster"
sys.path[:0] = [str(ROOT), str(SKILL / "scripts")]

import generation  # noqa: E402
import poster as drawing  # noqa: E402
from jobs.production import JobBusy, JobLock, LOG_DIR, _append_event, _atomic_json, utc_now  # noqa: E402
from shared.loaders import cpca_briefing_loader as cpca  # noqa: E402

JOB = "cpca-market-retail-poster"
SCRIPT = "workspace/business_scripts/cpca_market_retail_poster.py"
OUTPUT = ROOT / "workspace/outputs/charts/cpca_market_retail_poster"
LOGS = ROOT / LOG_DIR / JOB
PROMPT_VERSION = "V1.1"
REFERENCE_VERSION = "2026-10-31"
MODEL = "opencode/gemini-nano-banana-2.1"
SIZE = (896, 1200)
SECTIONS = dict(zip(cpca.SECTION_KEYS, ("最新区间", "当月累计", "当年累计"), strict=True))
METRICS = dict(zip(cpca.METRIC_KEYS, ("乘用车市场零售", "新能源市场零售"), strict=True))


class JobFailure(ValueError):
    def __init__(self, code, message):
        super().__init__(message)
        self.code = code


def read_json(path):
    return json.loads(path.read_text(encoding="utf-8"))


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def validate_period(period, cutoff):
    start = date.fromisoformat(period["start"])
    end = date.fromisoformat(period["end"])
    if end.isoformat() != cutoff or period["days"] != (end - start).days + 1 or start > end:
        raise ValueError("统计区间与期次或天数不一致")


def period_text(period, *, include_year=False):
    start = date.fromisoformat(period["start"])
    end = date.fromisoformat(period["end"])
    prefix = f"{start.year}年" if include_year or start.year != end.year else ""
    if start.year != end.year:
        return f"{prefix}{start.month}月{start.day}日至{end.year}年{end.month}月{end.day}日"
    if start.month != end.month:
        return f"{prefix}{start.month}月{start.day}日-{end.month}月{end.day}日"
    if start == end:
        return f"{prefix}{start.month}月{start.day}日"
    return f"{prefix}{start.month}月{start.day}-{end.day}日"


def number(metric, key):
    value = metric.get(key)
    if value is not None and (type(value) not in (int, float) or not math.isfinite(value)):
        raise ValueError(f"CPCA {key} 不是有限数值")
    return value


def display_metric(metric):
    value = number(metric, "value")
    yoy = number(metric, "yoy_pct")
    if value is None and yoy is None:
        return None
    value_text = None
    if value is not None:
        if value < 0 or metric.get("unit") != "万辆":
            raise ValueError("CPCA 销量或单位不符合简报契约")
        value_text = format(Decimal(str(value)), ",f")
        if "." not in value_text:
            value_text += ".0"
    if type(metric.get("estimated")) is not bool:
        raise ValueError("可用指标缺少有效的 estimated 标记")
    if yoy:
        yoy_text = format(Decimal(str(yoy)).normalize(), "+f") + "%"
        trend = "绿色向下箭头，数字为绿色" if yoy < 0 else "红色向上箭头，数字为红色"
    else:
        yoy_text = None if yoy is None else "0%"
        trend = None if yoy is None else "中性色数字，无箭头"
    return {
        "value": value,
        "value_text": value_text,
        "yoy_pct": yoy,
        "yoy_text": yoy_text,
        "trend": trend,
        "estimated": metric["estimated"],
        "basis": metric.get("basis"),
    }


def prepare_layout(edition, sections):
    first_week = sections["week"]["period"]["start"] == edition["edition"][:7] + "-01"
    rows = []
    for key, label in SECTIONS.items():
        if key not in sections or (first_week and key != "week"):
            continue
        section = sections[key]
        metrics = {}
        for metric_key, name in METRICS.items():
            raw = section["metrics"].get(metric_key)
            display = display_metric(raw) if raw is not None else None
            if display is not None:
                metrics[metric_key] = {"label": name, **display}
        if metrics:
            rows.append({
                "key": key, "label": label, "period": section["period"],
                "period_text": period_text(section["period"]), "metrics": metrics,
            })
    if not rows:
        raise ValueError("当前期无可绘制的零售指标")

    estimated = [
        f'{row["label"]}（{row["period_text"]}）' for row in rows
        if any(metric["estimated"] for metric in row["metrics"].values())
    ]
    date_strip = f'数据统计：{period_text(edition["period"], include_year=True)}'
    footer = ["数据来源：乘联会（CPCA）｜单位：万辆。"]
    if edition["report_status"] == "preliminary":
        date_strip += "（初步统计）"
        footer.append("注：本简报为初步统计数据。")
    if estimated:
        footer.append(f'{"、".join(estimated)}的估算销量和同比由相邻两期累计数据反推。')
    return {"date_strip": date_strip, "sections": rows, "footer": footer}


def prepare(selection):
    export_path = cpca.get_briefing_path()
    export = cpca.load_cpca_briefing(export_path)
    if selection == "latest":
        edition = export["editions"][0]
    else:
        edition = next(
            (item for item in export["editions"]
             if isinstance(item, dict) and item.get("edition") == selection),
            None,
        )
    if edition is None:
        raise ValueError(f"CPCA 出口无此统计截止日：{selection}")

    cutoff = edition["edition"]
    validate_period(edition["period"], cutoff)
    report_status = edition["report_status"]
    if not isinstance(report_status, str) or not report_status or edition["source"]["publisher"] != "CPCA":
        raise ValueError("缺少统计状态或 CPCA 来源")
    sections = {}
    for section in edition["sections"]:
        key = section["key"]
        if key not in SECTIONS or key in sections:
            raise ValueError(f"无效或重复的统计段：{key}")
        sections[key] = section
        validate_period(section["period"], cutoff)
        metrics = section["metrics"]
        if not isinstance(metrics, dict):
            raise ValueError(f"无效的指标对象：{key}")
        for metric_key, metric in metrics.items():
            if metric_key not in METRICS or (metric is not None and not isinstance(metric, dict)):
                raise ValueError(f"无效的零售指标：{metric_key}")
    if "week" not in sections:
        raise ValueError("缺少 v1 必需的最新区间")

    layout = prepare_layout(edition, sections)
    try:
        baseline, template, reference = drawing.load_assets(PROMPT_VERSION)
    except (ValueError, KeyError, TypeError, OSError) as error:
        raise JobFailure("baseline_invalid", str(error)) from error
    if baseline["version"] != PROMPT_VERSION or generation.MODEL != MODEL or generation.EXPECTED_SIZE != SIZE:
        raise JobFailure("baseline_invalid", "Prompt、模型或原生尺寸偏离正式基线")
    snapshot = {
        "business": edition,
        "export": {
            "path": str(export_path),
            "contract": export["contract"],
            "schema_version": export["schema_version"],
            "generated_at": export["generated_at"],
            "source": export["source"],
        },
        "layout": layout,
        "execution": {
            "requested_model": MODEL,
            "actual_model": None,
            "prompt_version": PROMPT_VERSION,
            "prompt_sha256": baseline["prompt_sha256"],
            "reference_version": REFERENCE_VERSION,
            "reference_sha256": baseline["reference_sha256"],
            "native_size": list(SIZE),
            "generation_seconds": None,
            "cost_usd": None,
            "acceptance_status": "preflight_passed",
        },
    }
    return snapshot, template, reference


def result(outcome, message, *, edition=None, artifacts=None, **details):
    error = outcome in {
        "busy", "invalid_parameters", "preflight_failed", "baseline_invalid", "model_unavailable",
        "submission_uncertain", "attempt_superseded", "generation_failed", "validation_failed", "job_error",
    }
    return {
        "status": "error" if error else "partial_success" if outcome == "pending_review" else "success",
        "script": SCRIPT,
        "generated_at": utc_now(),
        "scope": {
            "data_source": str(cpca.get_briefing_path()),
            "time_window": {"date": edition},
            "filters": {},
            "metric_definition": "CPCA 乘用车及新能源市场零售（万辆）和同比",
        },
        "result": {"outcome": outcome, "summary": message, "edition": edition, **details},
        "artifacts": artifacts or {},
        "followup_context": {"date": edition},
        "warnings": [],
        "errors": [{"code": outcome, "message": message}] if error else [],
    }


def save_png(source, target):
    # Replace atomically after confirming the full image decodes. No geometric changes.
    temporary = target.with_name(f".{target.name}.{uuid4().hex}.tmp")
    try:
        with Image.open(source) as image:
            if image.size != SIZE:
                raise ValueError(f"图片尺寸应为 {SIZE[0]}×{SIZE[1]}")
            image.load()
            if image.format == "PNG":
                shutil.copyfile(source, temporary)
            elif image.format == "JPEG":
                image.convert("RGB").save(temporary, format="PNG")
            else:
                image.save(temporary, format="PNG")
        os.replace(temporary, target)
    finally:
        temporary.unlink(missing_ok=True)


class EditionOutput:
    def __init__(self, edition):
        self.edition = edition
        self.formal = OUTPUT / edition
        self.briefing = self.formal / "briefing.json"
        self.image = self.formal / "poster.png"
        self.log = LOGS / edition
        self.pointer = self.log / "latest.json"

    def latest(self):
        return self.log / read_json(self.pointer)["attempt"] if self.pointer.is_file() else None

    def snapshot(self, attempt):
        return read_json(attempt / "briefing.json")

    def formal_artifacts(self, *, approved=False):
        paths = {"json": str(self.briefing)} if self.briefing.is_file() else {}
        if approved:
            paths["png"] = str(self.image)
        return paths

    def write_briefing(self, snapshot):
        staging = self.log / "formal-briefing.json"
        _atomic_json(staging, snapshot)
        self.formal.mkdir(parents=True, exist_ok=True)
        os.replace(staging, self.briefing)

    def check_published(self, *, recover):
        latest = self.latest()
        saved = read_json(self.briefing) if self.briefing.is_file() else {}
        expected = None
        if latest:
            snapshot = self.snapshot(latest)
            if snapshot["execution"]["acceptance_status"] == "approved":
                expected = snapshot
        execution = saved.get("execution", {})
        if (
            execution.get("acceptance_status") == "approved"
            and (expected is None or saved == expected)
            and self.image.is_file()
            and digest(self.image) == execution.get("image_sha256")
        ):
            return True
        if recover and expected:
            self.publish(latest, expected)
            return True
        if self.image.exists() or execution.get("acceptance_status") == "approved" or expected:
            raise JobFailure("validation_failed", "正式产物与验收记录不一致，请用 render 恢复或核对日志")
        return False

    def publish(self, attempt, snapshot):
        source = attempt / "candidate.png"
        if digest(source) != snapshot["execution"]["image_sha256"]:
            raise JobFailure("validation_failed", "已验收图片与记录的 SHA-256 不一致")
        self.formal.mkdir(parents=True, exist_ok=True)
        staging = self.log / "formal-poster.png"
        save_png(source, staging)
        os.replace(staging, self.image)
        self.write_briefing(snapshot)

    def report_attempt(self, attempt, *, published):
        snapshot = self.snapshot(attempt)
        execution = snapshot["execution"]
        status = execution["acceptance_status"]
        candidate = attempt / "candidate.png"
        if status == "preflight_passed":
            record = attempt / "generation.json"
            try:
                generation_record = read_json(record)
            except (OSError, ValueError) as error:
                raise JobFailure("submission_uncertain", "提交状态未确认，请核对运行日志及账单") from error
            if generation_record.get("status") not in {"pending_visual_review", "failed"}:
                raise JobFailure("submission_uncertain", "提交状态未确认，请核对运行日志及账单")
            execution.update(
                actual_model=generation_record.get("actual_model_version"),
                generation_seconds=generation_record.get("seconds"),
                cost_usd=generation_record.get("cost_usd"),
                response_id=generation_record.get("response_id"),
                usage=generation_record.get("usage"),
                model_requests=1 if "http_status" in generation_record else None,
            )
            if "request_sha256" in generation_record:
                execution["request_sha256"] = generation_record["request_sha256"]
            if generation_record["status"] == "pending_visual_review":
                raw = Path(generation_record["image_path"])
                model_version = generation_record.get("actual_model_version")
                if raw.parent != attempt or not isinstance(model_version, str) or (
                    model_version.removeprefix("models/") != generation.MODEL_ID
                ):
                    raise JobFailure("validation_failed", "模型回包与本次尝试不一致")
                try:
                    save_png(raw, candidate)
                except (ValueError, OSError) as error:
                    raise JobFailure("validation_failed", f"候选图片无法通过文件校验：{error}") from error
                execution.update(acceptance_status="pending_review", image_sha256=digest(candidate))
            else:
                unavailable = {401, 402, 403, 404, 429, 503}
                code = "model_unavailable" if generation_record.get("http_status") in unavailable else "generation_failed"
                if generation_record.get("image_path"):
                    code = "validation_failed"
                execution.update(acceptance_status="failed", failure_code=code,
                                 failure_reason=generation_record.get("error", "图片生成失败"))
            _atomic_json(attempt / "briefing.json", snapshot)
            status = execution["acceptance_status"]

        if not published:
            self.write_briefing(snapshot)
        options = {
            "edition": self.edition,
            "artifacts": self.formal_artifacts(approved=published),
            "attempt": attempt.name,
            "generation": {key: execution.get(key) for key in (
                "model_requests", "actual_model", "generation_seconds", "cost_usd",
                "usage", "response_id", "request_sha256",
            )},
        }
        if status == "pending_review":
            if not candidate.is_file() or digest(candidate) != execution["image_sha256"]:
                raise JobFailure("validation_failed", "待验收图片与记录的 SHA-256 不一致")
            return result(
                "pending_review", "成图待人工核对数据及视觉质量", **options,
                candidate_path=str(candidate), candidate_sha256=execution["image_sha256"],
                review_briefing_path=str(attempt / "briefing.json"),
            )
        if status == "approved":
            return result("reused", "复用已验收海报", **options)
        if status == "rejected":
            return result("validation_failed", execution["review_note"], **options)
        return result(execution["failure_code"], execution["failure_reason"], **options)

    def render(self, snapshot, template, reference, redraw, *, published):
        if published and redraw == "none":
            return result("reused", "复用已验收海报", edition=self.edition,
                          artifacts=self.formal_artifacts(approved=True))
        latest = self.latest()
        attempt = self.log / ("initial" if redraw == "none" else redraw)
        if redraw == "none" and latest:
            attempt = latest
        if attempt.is_dir():
            if attempt != latest:
                raise JobFailure("attempt_superseded", "该尝试编号已使用，且已有更新的尝试")
            return self.report_attempt(attempt, published=published)

        try:
            generation.api_key()
        except ValueError as error:
            if not published:
                snapshot["execution"].update(
                    acceptance_status="failed", failure_code="model_unavailable", failure_reason=str(error)
                )
                self.write_briefing(snapshot)
            return result("model_unavailable", str(error), edition=self.edition,
                          artifacts=self.formal_artifacts(approved=published))
        attempt.mkdir(mode=0o700, parents=True)
        snapshot["execution"]["attempt"] = attempt.name
        briefing_path = attempt / "briefing.json"
        _atomic_json(briefing_path, snapshot)
        _atomic_json(self.pointer, {"attempt": attempt.name})
        if not published:
            self.write_briefing(snapshot)
        drawing.render(briefing_path, template, reference, attempt)
        return self.report_attempt(attempt, published=published)

    def review(self, args, service_run_id, dsh_child_run_id):
        attempt = self.latest()
        if attempt is None or attempt.name != args.attempt:
            raise JobFailure("invalid_parameters", "只能验收当前期次最新的付费尝试")
        snapshot = self.snapshot(attempt)
        execution = snapshot["execution"]
        candidate = attempt / "candidate.png"
        if not candidate.is_file() or digest(candidate) != args.sha256 or args.sha256 != execution.get("image_sha256"):
            raise JobFailure("validation_failed", "验收指纹与待验收图片不一致")

        published = self.check_published(recover=True)
        decision = "approved" if args.review == "approve" else "rejected"
        current = execution["acceptance_status"]
        if current != "pending_review" and current != decision:
            raise JobFailure("invalid_parameters", "该图片已记录验收结果")
        if current == "pending_review":
            execution.update(acceptance_status=decision, reviewed_at=utc_now(),
                             review_method="manual", review_note=args.note,
                             review_service_run_id=service_run_id, review_dsh_child_run_id=dsh_child_run_id)
            # Journal the decision first, so a later render can finish an interrupted publication.
            _atomic_json(attempt / "briefing.json", snapshot)
            if decision == "approved":
                self.publish(attempt, snapshot)
                published = True
        if decision == "approved":
            return result("approved", "图片通过人工数据及视觉验收", edition=self.edition,
                          artifacts=self.formal_artifacts(approved=True), attempt=attempt.name)
        return self.report_attempt(attempt, published=published)


def run(args):
    edition = None if args.date == "latest" else args.date
    run_id = uuid4().hex
    child_id = os.environ.get("DSH_CPCA_CHILD_RUN_ID")
    if child_id is not None and not re.fullmatch(r"[0-9a-f]{32}", child_id):
        raise ValueError("DSH_CPCA_CHILD_RUN_ID 须为 32 位小写十六进制")
    correlation = {"service_run_id": run_id}
    if child_id:
        correlation["dsh_child_run_id"] = child_id
    try:
        with JobLock(ROOT, run_id, "local-review" if args.review else JOB, job=JOB):
            _append_event(LOGS / "events.jsonl", {
                "at": utc_now(), "run_id": run_id, "event": "started", "date": args.date,
                "mode": args.review or args.mode, "redraw": args.redraw, **correlation,
            })
            if args.review:
                summary = EditionOutput(edition).review(args, run_id, child_id)
            else:
                try:
                    snapshot, template, reference = prepare(args.date)
                except (cpca.CpcaBriefingError, ValueError, KeyError, TypeError, OSError) as error:
                    raise JobFailure(getattr(error, "code", "preflight_failed"), str(error)) from error
                edition = snapshot["business"]["edition"]
                output = EditionOutput(edition)
                published = output.check_published(recover=args.mode == "render")
                if args.mode == "dry-run":
                    if not published:
                        previous = read_json(output.briefing) if output.briefing.is_file() else {}
                        inputs = ("business", "export", "layout")
                        if any(previous.get(key) != snapshot[key] for key in inputs):
                            output.write_briefing(snapshot)
                    summary = result("preflight_passed", "绘图输入已预检", edition=edition,
                                     artifacts=output.formal_artifacts(), existing_approved=published)
                else:
                    summary = output.render(snapshot, template, reference, args.redraw, published=published)
    except JobBusy as error:
        summary = result("busy", str(error), edition=edition)
    except (ValueError, TypeError, KeyError, OSError) as error:
        summary = result(getattr(error, "code", "job_error"), str(error), edition=edition)
    summary["result"].update(correlation)
    _append_event(LOGS / "events.jsonl", {"at": utc_now(), "run_id": run_id, **summary["result"]})
    return summary


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--date", default="latest", help="latest 或统计截止日 YYYY-MM-DD")
    parser.add_argument("--mode", choices=("dry-run", "render"), default="dry-run")
    parser.add_argument("--redraw", default="none", help="32 位小写十六进制幂等编号")
    parser.add_argument("--review", choices=("approve", "reject"), help="本地人工验收")
    parser.add_argument("--attempt", help="待验收尝试编号")
    parser.add_argument("--sha256", help="实际核对的候选 PNG 的 SHA-256")
    parser.add_argument("--note", help="数据及视觉核验记录，或驳回原因")
    args = parser.parse_args(argv)
    try:
        if args.date != "latest" and date.fromisoformat(args.date).isoformat() != args.date:
            raise ValueError("日期须为 YYYY-MM-DD")
        if args.redraw != "none" and (
            not re.fullmatch(r"[0-9a-f]{32}", args.redraw)
            or args.mode != "render" or args.date == "latest" or args.review
        ):
            raise ValueError("重绘须指定统计日期、render 模式及 32 位小写十六进制编号")
        if args.review:
            if args.date == "latest" or args.mode == "render" or not (
                args.attempt and re.fullmatch(r"initial|[0-9a-f]{32}", args.attempt)
                and args.sha256 and re.fullmatch(r"[0-9a-f]{64}", args.sha256)
                and args.note and args.note.strip()
            ):
                raise ValueError("验收须指定统计日期、尝试编号、候选图 SHA-256 和验收记录")
        elif any(value is not None for value in (args.attempt, args.sha256, args.note)):
            raise ValueError("验收参数须与 --review 一起使用")
    except ValueError as error:
        summary = result("invalid_parameters", str(error))
    else:
        summary = run(args)
    print(json.dumps(summary, ensure_ascii=False))
    return 1 if summary["status"] == "error" else 0


if __name__ == "__main__":
    raise SystemExit(main())

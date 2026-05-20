#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
每日锁单数据观察脚本
功能：
1. 读取 order_data.parquet 数据
2. 计算昨日（T-1）的锁单数
3. 统计指定车型（CM2, DM1, LS8, LS9）的锁单情况
4. 发送飞书通知
"""

import os
import sys
import json
import argparse
import time
import re
import pandas as pd
from datetime import datetime, timedelta
import requests
from dotenv import load_dotenv
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))

from operators.mature_lock_prediction import run_mature_lock_prediction_operator
from operators.assign_conversion import _parse_cn_date
load_dotenv(REPO_ROOT / ".env")

# 配置常量
PARQUET_FILE = str(REPO_ROOT / "dataset" / "order_data.parquet")
BUSINESS_DEF_FILE = REPO_ROOT / "schema" / "business_definition.json"
# 适配新数据集的 series 值：CM2->LS6, DM1->L6
TARGET_MODELS = ["LS6", "L6", "LS8", "LS9"]
WEBHOOK_URL = os.getenv("FS_WEBHOOK_URL")

def parse_arguments():
    """解析命令行参数"""
    parser = argparse.ArgumentParser(description='每日锁单数据观察脚本')
    parser.add_argument('--start', type=str, help='开始日期 (YYYY-MM-DD)')
    parser.add_argument('--end', type=str, help='结束日期 (YYYY-MM-DD)')
    parser.add_argument('--mtd', action='store_true', help='当月1日累计至今')
    parser.add_argument('--dry-run', action='store_true', help='仅输出统计结果，不发送飞书通知')
    
    # 预处理 sys.argv 以支持 -N 这种非标准参数
    days_back = 1  # 默认昨天
    
    # 检查是否有负数参数 (如 -1, -2, -7)
    args_to_remove = []
    for arg in sys.argv[1:]:
        if arg.startswith('-') and len(arg) > 1 and arg[1:].isdigit():
            days_back = int(arg[1:])
            args_to_remove.append(arg)
    
    # 从 sys.argv 中移除这些参数，以免 argparse 报错
    for arg in args_to_remove:
        sys.argv.remove(arg)
        
    args = parser.parse_args()
    
    end_date = datetime.now().date() - timedelta(days=1)
    start_date = end_date
    
    if args.start and args.end:
        try:
            start_date = datetime.strptime(args.start, '%Y-%m-%d').date()
            end_date = datetime.strptime(args.end, '%Y-%m-%d').date()
        except ValueError:
            print("❌ 日期格式错误，请使用 YYYY-MM-DD")
            sys.exit(1)
    elif args.mtd:
        # 如果使用了 --mtd 参数
        end_date = datetime.now().date() - timedelta(days=1)
        start_date = end_date.replace(day=1)
    elif args_to_remove:
        # 如果使用了 -N 参数
        start_date = datetime.now().date() - timedelta(days=days_back)
        end_date = datetime.now().date() - timedelta(days=1)
    
    return start_date, end_date, args.dry_run

def load_business_definition(file_path):
    """加载业务定义文件"""
    if not os.path.exists(file_path):
        print(f"❌ 错误: 业务定义文件不存在 - {file_path}")
        return None
    
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            return json.load(f)
    except Exception as e:
        print(f"❌ 加载业务定义失败: {e}")
        return None

def load_data(file_path):
    """加载 Parquet 数据"""
    if not os.path.exists(file_path):
        print(f"❌ 错误: 文件不存在 - {file_path}")
        return None
    
    try:
        print(f"正在加载数据: {file_path}")
        df = pd.read_parquet(file_path)
        print(f"✅ 数据加载成功，共 {len(df)} 行")
        return df
    except Exception as e:
        print(f"❌ 数据加载失败: {e}")
        return None

def analyze_daily_lock_orders(df, start_date, end_date):
    """
    分析锁单数据 (支持时间范围)
    """
    print(f"正在分析 {start_date} 至 {end_date} 的锁单数据...")
    
    # 加载业务定义以获取电池容量映射
    business_def = load_business_definition(BUSINESS_DEF_FILE)
    battery_capacity_logic = (business_def or {}).get("battery_capacity_logic") or {}
    product_to_capacity = {}
    if business_def and "battery_capacity" in business_def:
        for capacity, products in business_def["battery_capacity"].items():
            for product in products:
                product_to_capacity[product] = capacity
    
    seat_count_labels = ["五座", "六座"]
    if business_def and "seat_count_logic" in business_def:
        seat_count_labels = [label for label in seat_count_labels if label in business_def["seat_count_logic"]] or seat_count_labels

    def _like(value, pattern):
        if value is None:
            return False
        pattern = pattern[1:-1] if len(pattern) >= 2 and pattern[0] == "'" and pattern[-1] == "'" else pattern
        regex_parts = []
        for ch in pattern:
            if ch == "%":
                regex_parts.append(".*")
            elif ch == "_":
                regex_parts.append(".")
            else:
                regex_parts.append(re.escape(ch))
        regex = "^" + "".join(regex_parts) + "$"
        return re.fullmatch(regex, str(value)) is not None

    def _tokenize(expr):
        tokens = []
        i = 0
        n = len(expr)
        while i < n:
            ch = expr[i]
            if ch.isspace():
                i += 1
                continue
            if ch in ("(", ")"):
                tokens.append(ch)
                i += 1
                continue
            if ch == "'":
                j = i + 1
                while j < n and expr[j] != "'":
                    j += 1
                tokens.append(expr[i : j + 1] if j < n else expr[i:])
                i = j + 1 if j < n else n
                continue
            j = i
            while j < n and (expr[j].isalnum() or expr[j] in ("_",)):
                j += 1
            tokens.append(expr[i:j])
            i = j
        return [t for t in tokens if t]

    def _parse_logic(expr):
        tokens = _tokenize(expr)
        idx = 0

        def peek():
            return tokens[idx] if idx < len(tokens) else None

        def take():
            nonlocal idx
            tok = tokens[idx] if idx < len(tokens) else None
            idx += 1
            return tok

        def parse_expr():
            node = parse_term()
            while True:
                tok = peek()
                if tok and tok.upper() == "OR":
                    take()
                    rhs = parse_term()
                    node = ("OR", node, rhs)
                else:
                    break
            return node

        def parse_term():
            node = parse_factor()
            while True:
                tok = peek()
                if tok and tok.upper() == "AND":
                    take()
                    rhs = parse_factor()
                    node = ("AND", node, rhs)
                else:
                    break
            return node

        def parse_factor():
            tok = peek()
            if tok and tok.upper() == "NOT":
                take()
                inner = parse_factor()
                return ("NOT", inner)
            return parse_atom()

        def parse_atom():
            tok = peek()
            if tok == "(":
                take()
                inner = parse_expr()
                if peek() == ")":
                    take()
                return inner
            left = take()
            if not left:
                return ("LIT", False)
            not_flag = False
            tok2 = peek()
            if tok2 and tok2.upper() == "NOT":
                take()
                not_flag = True
            tok3 = peek()
            if tok3 and tok3.upper() == "LIKE":
                take()
            pattern = take()
            return ("COND", not_flag, left, pattern)

        return parse_expr()

    def _eval_ast(ast, product_name):
        op = ast[0]
        if op == "OR":
            return _eval_ast(ast[1], product_name) or _eval_ast(ast[2], product_name)
        if op == "AND":
            return _eval_ast(ast[1], product_name) and _eval_ast(ast[2], product_name)
        if op == "NOT":
            return not _eval_ast(ast[1], product_name)
        if op == "COND":
            not_flag, left, pattern = ast[1], ast[2], ast[3]
            if not left or str(left) != "product_name":
                return False
            res = _like(product_name, pattern or "")
            return (not res) if not_flag else res
        if op == "LIT":
            return bool(ast[1])
        return False

    # 确保必要的列存在
    # 更新为新数据集的列名
    required_columns = ['lock_time', 'order_number', 'series', 'product_name']
    for col in required_columns:
        if col not in df.columns:
            print(f"❌ 错误: 数据缺失列 {col}")
            return None

    # 数据预处理
    df_copy = df.copy()
    df_copy['lock_time'] = pd.to_datetime(df_copy['lock_time'], errors='coerce').dt.date
    
    # 筛选目标日期范围的锁单数据
    daily_orders = df_copy[
        (df_copy['lock_time'] >= start_date) & 
        (df_copy['lock_time'] <= end_date)
    ]
    
    # 1. 计算总锁单数 (基于 order_number 去重)
    total_lock_count = daily_orders['order_number'].nunique()
    
    # 2. 分车型统计
    model_stats = {}
    for model in TARGET_MODELS:
        model_df = daily_orders[daily_orders['series'] == model]
        count = model_df['order_number'].nunique()
        
        stats = {"count": count}
        
        # 对 LS6 (原CM2) 和 LS9 进行电池容量细分
        if model in ["LS6", "LS9"]:
            capacity_counts = {}
            if battery_capacity_logic:
                capacity_asts = {k: _parse_logic(v) for k, v in battery_capacity_logic.items()}
                if model == "LS9":
                    allowed_caps = [k for k in ["52kwh", "66kwh"] if k in battery_capacity_logic]
                else:
                    allowed_caps = list(battery_capacity_logic.keys())

                capacity_counts = {k: 0 for k in allowed_caps}
                unique_orders = model_df[['order_number', 'product_name']].drop_duplicates('order_number')
                for _, row in unique_orders.iterrows():
                    p_name = row['product_name']
                    if pd.isna(p_name):
                        continue
                    p_name = str(p_name)
                    for cap in allowed_caps:
                        ast = capacity_asts[cap]
                        if _eval_ast(ast, p_name):
                            capacity_counts[cap] += 1
                            break
            elif product_to_capacity:
                capacity_counts = {"52kwh": 0, "66kwh": 0}
                unique_orders = model_df[['order_number', 'product_name']].drop_duplicates('order_number')
                for _, row in unique_orders.iterrows():
                    p_name = row['product_name']
                    cap = product_to_capacity.get(p_name)
                    if cap in ["52kwh", "66kwh"]:
                        capacity_counts[cap] += 1

            if capacity_counts:
                stats["details"] = capacity_counts

        if model == "LS8":
            seat_counts = {label: 0 for label in seat_count_labels}
            unique_orders = model_df[['order_number', 'product_name']].drop_duplicates('order_number')
            for _, row in unique_orders.iterrows():
                p_name = row['product_name']
                if pd.isna(p_name):
                    continue
                p_name = str(p_name)
                for label in seat_count_labels:
                    if label in p_name:
                        seat_counts[label] += 1
                        break
            stats["seat_details"] = seat_counts
            
        model_stats[model] = stats
        
    return {
        "start_date": start_date,
        "end_date": end_date,
        "total": total_lock_count,
        "models": model_stats
    }

def analyze_daily_invoice_orders(df, start_date, end_date):
    """
    分析开票数据 (基于 Invoice_Upload_Time)
    定义：有 Invoice_Upload_Time 且有 Lock_Time 的 Order Number 数
    """
    print(f"正在分析 {start_date} 至 {end_date} 的开票数据...")
    
    # 确保必要的列存在
    # 更新为新数据集的列名
    required_columns = ['invoice_upload_time', 'lock_time', 'order_number', 'series', 'invoice_amount', 'order_type']
    for col in required_columns:
        if col not in df.columns:
            print(f"❌ 错误: 数据缺失列 {col}")
            return None

    # 数据预处理
    df_copy = df.copy()
    df_copy['invoice_upload_time'] = pd.to_datetime(df_copy['invoice_upload_time'], errors='coerce').dt.date
    
    # 筛选条件：
    # 1. invoice_upload_time 在目标日期范围内
    # 2. lock_time 不为空 (题目要求：有 invoice_upload_time 且有 lock_time)
    invoice_orders = df_copy[
        (df_copy['invoice_upload_time'] >= start_date) & 
        (df_copy['invoice_upload_time'] <= end_date) &
        (df_copy['lock_time'].notna())
    ]
    
    # 1. 计算总开票数 (基于 order_number 去重)
    total_invoice_count = invoice_orders['order_number'].nunique()
    
    # 计算用户车开票数
    user_car_orders = invoice_orders[invoice_orders['order_type'] == '用户车']
    total_user_car_count = user_car_orders['order_number'].nunique()
    
    # 2. 分车型统计
    model_invoice_stats = {}
    for model in TARGET_MODELS:
        model_df = invoice_orders[invoice_orders['series'] == model]
        count = model_df['order_number'].nunique()
        
        # 用户车数量
        model_user_car_df = model_df[model_df['order_type'] == '用户车']
        user_car_count = model_user_car_df['order_number'].nunique()
        
        # 计算该车型的平均开票价格 (仅计算用户车)
        model_valid_prices = model_user_car_df[
            (model_user_car_df['invoice_amount'].notna()) & 
            (model_user_car_df['invoice_amount'] > 0)
        ]['invoice_amount']
        avg_price = model_valid_prices.mean() if not model_valid_prices.empty else 0
        
        model_invoice_stats[model] = {
            "count": count,
            "user_car_count": user_car_count,
            "avg_price": avg_price
        }
        
    return {
        "start_date": start_date,
        "end_date": end_date,
        "total": total_invoice_count,
        "total_user_car": total_user_car_count,
        "models": model_invoice_stats
    }

def get_predicted_lock(assign_date_str: str) -> tuple[float | None, float | None, str | None]:
    """
    获取指定日期的预测锁单数。
    returns (pred30, actual_locks_on_date, warning)
    """
    csv_path = REPO_ROOT / "dataset" / "assign_data.csv"
    if not csv_path.exists():
        return None, None, None
    try:
        df = pd.read_csv(str(csv_path))
        end_dt = pd.Timestamp(assign_date_str) + pd.Timedelta(days=1)
        result = run_mature_lock_prediction_operator(df, assign_date_str, end_dt.strftime("%Y-%m-%d"))
        rows = result.get("daily_rows", [])
        if not rows:
            return None, None, None
        r = rows[0]
        pred = r.get("预测30日锁单数")
        return pred, None, None
    except Exception as e:
        return None, None, str(e)


def send_feishu_notification(lock_stats, invoice_stats, pred_lock=None):
    """发送飞书通知"""
    if not WEBHOOK_URL:
        print("❌ 错误: 未设置 FS_WEBHOOK_URL 环境变量，跳过发送消息")
        return

    # 构建标题日期字符串
    start_date = lock_stats['start_date']
    end_date = lock_stats['end_date']
    if start_date == end_date:
        date_str = str(start_date)
        title_prefix = "每日"
        lock_label = "昨日锁单数"
        invoice_label = "昨日开票数"
    else:
        date_str = f"{start_date} ~ {end_date}"
        title_prefix = "阶段性"
        lock_label = "期间锁单数"
        invoice_label = "期间开票数"

    # 构建锁单明细文本
    lock_model_details = []
    for model, stats in lock_stats['models'].items():
        count = stats["count"]
        detail_parts = []
        if "details" in stats:
            d = stats["details"]
            for cap, cap_count in d.items():
                cap_label = str(cap).replace("kwh", "kw")
                detail_parts.append(f"{cap_label}：{cap_count}")
        if "seat_details" in stats:
            d = stats["seat_details"]
            if "五座" in d:
                detail_parts.append(f"五座：{d['五座']}")
            if "六座" in d:
                detail_parts.append(f"六座：{d['六座']}")
        detail_str = "｜" + "，".join(detail_parts) if detail_parts else ""
        lock_model_details.append(f"- {model}: {count} 单{detail_str}")
    lock_model_text = "\n".join(lock_model_details)

    # 构建开票明细文本
    invoice_model_details = []
    for model, info in invoice_stats['models'].items():
        price_str = f"{info['avg_price']/10000:.1f}w" if info['avg_price'] > 0 else "N/A"
        # 格式：- Model: Total (User) 台｜平均开票价格：XXw
        invoice_model_details.append(f"- {model}: {info['count']} ({info['user_car_count']}) 台｜平均开票价格：{price_str}")
    invoice_model_text = "\n".join(invoice_model_details)

    # 构建预测锁单与达成率
    pred_line = ""
    warn_line = ""
    is_warning = False
    if pred_lock is not None and pred_lock > 0:
        actual = lock_stats['total']
        rate = actual / pred_lock
        pred_line = f"预测锁单数：{pred_lock:.0f}"
        if rate < 0.8:
            is_warning = True
            warn_line = (
                f"\n\n⚠️ **达成率预警**\n"
                f"达成率：{rate:.1%} < 80%\n"
                f"实际锁单({actual}) 低于预测({pred_lock:.0f})，"
                f"建议排查转化链路是否存在异常。"
            )
        else:
            warn_line = f"\n达成率：{rate:.1%}（正常）"

    card_content = {
        "msg_type": "interactive",
        "card": {
            "header": {
                "title": {
                    "tag": "plain_text",
                    "content": f"📊 {title_prefix}业务数据观察 ({date_str})"
                },
                "template": "red" if is_warning else "blue"
            },
            "elements": [
                {
                    "tag": "div",
                    "text": {
                        "tag": "lark_md",
                        "content": f"**{lock_label}：** {lock_stats['total']}\n{lock_model_text}\n{pred_line}{warn_line}"
                    }
                },
                {
                    "tag": "hr"
                },
                {
                    "tag": "div",
                    "text": {
                        "tag": "lark_md",
                        "content": f"**{invoice_label}：** {invoice_stats['total']} ({invoice_stats['total_user_car']}) 台\n{invoice_model_text}"
                    }
                },
                {
                    "tag": "hr"
                },
                {
                    "tag": "note",
                    "elements": [
                        {
                            "tag": "plain_text",
                            "content": f"统计时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"
                        }
                    ]
                }
            ]
        }
    }

    max_retries = 3
    for attempt in range(max_retries):
        try:
            response = requests.post(WEBHOOK_URL, json=card_content)
            response.raise_for_status()
            result = response.json()
            
            # 兼容不同的成功状态码字段 (StatusCode 或 code)
            # 飞书自定义机器人通常返回 StatusCode, 但开放平台接口可能返回 code
            code = result.get("StatusCode")
            if code is None:
                code = result.get("code")
            
            if code == 0:
                print("✅ 飞书消息发送成功")
                return
            elif code == 11232: # Frequency limited
                wait_time = 2 * (attempt + 1)
                print(f"⚠️ 飞书消息发送频率限制 (11232)，等待 {wait_time} 秒后重试 ({attempt + 1}/{max_retries})...")
                time.sleep(wait_time)
                continue
            else:
                print(f"❌ 飞书消息发送异常: {result}")
                return
        except Exception as e:
            print(f"❌ 发送飞书消息失败: {e}")
            if attempt < max_retries - 1:
                time.sleep(2)
            else:
                print("❌ 重试次数耗尽，发送失败")

def main():
    # 0. 解析参数
    start_date, end_date, dry_run = parse_arguments()
    
    # 1. 加载数据
    df = load_data(PARQUET_FILE)
    if df is None:
        return

    # 2. 分析数据
    lock_stats = analyze_daily_lock_orders(df, start_date, end_date)
    invoice_stats = analyze_daily_invoice_orders(df, start_date, end_date)
    
    # 3. 获取预测锁单数
    pred_lock = None
    if start_date == end_date:
        pred_lock, _, pred_err = get_predicted_lock(str(start_date))
        if pred_err:
            print(f"⚠️ 预测锁单计算失败: {pred_err}")

    if lock_stats and invoice_stats:
        # 打印结果到控制台
        print("\n" + "="*30)
        if start_date == end_date:
            print(f"📅 日期: {start_date}")
        else:
            print(f"📅 日期范围: {start_date} ~ {end_date}")

        print(f" 总锁单数: {lock_stats['total']}")
        print("   车型分布:")
        for model, stats in lock_stats['models'].items():
            count = stats["count"]
            detail_parts = []
            if "details" in stats:
                d = stats["details"]
                for cap, cap_count in d.items():
                    cap_label = str(cap).replace("kwh", "kw")
                    detail_parts.append(f"{cap_label}：{cap_count}")
            if "seat_details" in stats:
                d = stats["seat_details"]
                if "五座" in d:
                    detail_parts.append(f"五座：{d['五座']}")
                if "六座" in d:
                    detail_parts.append(f"六座：{d['六座']}")
            detail_str = "｜" + "，".join(detail_parts) if detail_parts else ""
            print(f"   - {model}: {count}{detail_str}")
        if pred_lock is not None and pred_lock > 0:
            rate = lock_stats['total'] / pred_lock
            warn = " ⚠️ 低于80%" if rate < 0.8 else ""
            print(f" 预测锁单数: {pred_lock:.0f}")
            print(f" 达成率: {rate:.1%}{warn}")
            
        print("-" * 30)
        
        print(f"🚚 总开票数: {invoice_stats['total']} ({invoice_stats['total_user_car']}) 台")
        print("   车型分布 (开票):")
        for model, info in invoice_stats['models'].items():
            price_display = f"{info['avg_price']/10000:.1f}w" if info['avg_price'] > 0 else "N/A"
            print(f"   - {model}: {info['count']} ({info['user_car_count']}) 台｜平均开票价格：{price_display}")
        print("="*30 + "\n")

        if dry_run:
            print("🧪 dry-run: 已跳过飞书通知发送")
            return
        send_feishu_notification(lock_stats, invoice_stats, pred_lock)

if __name__ == "__main__":
    main()

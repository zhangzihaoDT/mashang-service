#!/usr/bin/env python3
"""
上汽销售库存流转探查 — 2025 年度
基于 ownership_transfer_analysis.py + order_data.parquet
"""

from pathlib import Path
from datetime import datetime

_ROOT = Path(__file__).resolve().parents[1]
_REPORT_DIR = _ROOT / 'outputs' / 'reports'
_REPORT_DIR.mkdir(parents=True, exist_ok=True)
OUTPUT_HTML = str(_REPORT_DIR / '上汽销售库存流转探查.html')
STATIC = '../..'


def _series_badge(v):
    m = {'LSJEL':'LS8','LSJEH':'LS9','LSJWL':'LS7','LSJWR':'LS6','LSJWT':'L6','LSJE3':'L7'}
    return m.get(str(v)[:5], '其他')


HTML = r'''<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8"/>
<meta name="viewport" content="width=device-width,initial-scale=1.0"/>
<title>上汽销售库存流转探查 — 2025</title>
<link rel="stylesheet" href="{static}/templates/report_style.css"/>
<style>
.flow-chain {{ display:flex; align-items:center; gap:8px; flex-wrap:wrap; padding:12px 0; }}
.flow-step {{ text-align:center; min-width:70px; padding:10px 14px; background:var(--zh-card); border-radius:8px; box-shadow:0 1px 3px rgba(6,33,61,.06); }}
.flow-step .n {{ font-size:20px; font-weight:700; color:var(--zh-deep-blue); }}
.flow-step .l {{ font-size:11px; color:var(--zh-muted); margin-top:2px; }}
.flow-arrow {{ color:var(--zh-border); font-size:20px; }}
.insight {{ background:var(--zh-card); border-radius:10px; padding:16px 20px; margin-bottom:12px; box-shadow:0 1px 4px rgba(6,33,61,.06); border-left:4px solid var(--zh-blue); }}
.insight.gold {{ border-left-color:var(--zh-raccoon-gold); }}
.insight.green {{ border-left-color:var(--status-positive); }}
.insight h4 {{ font-size:14px; font-weight:600; color:var(--zh-deep-blue); margin-bottom:4px; }}
.insight p {{ font-size:13px; color:var(--zh-text); line-height:1.6; }}
.dual-grid {{ display:grid; grid-template-columns:1fr 1fr; gap:16px; margin-bottom:24px; }}
.dual-grid .card {{ margin-bottom:0; }}
@media (max-width:768px) {{ .dual-grid {{ grid-template-columns:1fr; }} .flow-chain {{ flex-direction:column; align-items:stretch; }} .flow-arrow {{ transform:rotate(90deg); text-align:center; }} }}
</style>
</head>
<body>

<header>
<div class="container">
<div class="brand">
<img class="brand-avatar" src="{static}/assets/brand/raccoon_avatar_light.png" alt=""/>
<span class="brand-name">Raccoon Research</span>
</div>
<span class="header-meta">深度分析报告 · {date}</span>
</div>
</header>

<main class="container">

<section class="hero">
<h1>上汽销售库存流转探查</h1>
<p>基于 delivery_inventory + order_data · 2025 年度 · bloc_name = "上汽销售"</p>
</section>

<div class="summary-grid">
<div class="summary-card"><div class="summary-value">7,551</div><div class="summary-label">上汽销售库存车辆</div><div class="summary-hint">含全部年份</div></div>
<div class="summary-card positive"><div class="summary-value">1,952</div><div class="summary-label">其中"用户车"订单</div><div class="summary-hint">2025 年交付占 1,118</div></div>
<div class="summary-card warning"><div class="summary-value">1,806</div><div class="summary-label">集团员工购车</div><div class="summary-hint">第二大订单类型</div></div>
<div class="summary-card"><div class="summary-value">926</div><div class="summary-label">个人购车（聚焦分析）</div><div class="summary-hint">用户车·2025·个人身份证</div></div>
<div class="summary-card neutral"><div class="summary-value">179</div><div class="summary-label">企业采购</div><div class="summary-hint">统一信用码·全部 L6</div></div>
<div class="summary-card positive"><div class="summary-value">19 天</div><div class="summary-label">锁单→交付中位数</div><div class="summary-hint">现车销售模式</div></div>
</div>

<div class="card">
<h2>一、上汽销售全景 · 7,551 辆库存去向</h2>
<div class="flow-chain">
<div class="flow-step"><div class="n">7,551</div><div class="l">上汽销售库存</div></div>
<span class="flow-arrow">→</span>
<div class="flow-step"><div class="n">4,846</div><div class="l">有订单记录</div></div>
<div class="flow-step"><div class="n">2,705</div><div class="l">无订单（物流前）</div></div>
</div>
<h3 style="font-size:14px;color:var(--zh-deep-blue);margin:16px 0 8px;">订单类型分布</h3>
<div class="table-wrap">
<table class="report-table">
<thead><tr><th>订单类型</th><th style="text-align:right;">数量</th><th style="text-align:right;">占比</th><th>说明</th></tr></thead>
<tbody>
<tr><td><strong>用户车</strong></td><td class="num">1,952</td><td class="num">40.3%</td><td>常规零售，挂上汽销售名下</td></tr>
<tr><td><strong>集团员工</strong></td><td class="num">1,806</td><td class="num">37.3%</td><td>员工内购</td></tr>
<tr><td>大客户</td><td class="num">86</td><td class="num">1.8%</td><td>大客户渠道</td></tr>
<tr><td>员工</td><td class="num">49</td><td class="num">1.0%</td><td>直接员工车</td></tr>
<tr><td>仅批售</td><td class="num">40</td><td class="num">0.8%</td><td>纯批发（L7）</td></tr>
<tr><td>试驾车</td><td class="num">35</td><td class="num">0.7%</td><td>门店试驾</td></tr>
<tr><td>经销商员工</td><td class="num">12</td><td class="num">0.2%</td><td>经销商店员</td></tr>
</tbody>
</table>
</div>
<p class="section-note" style="margin-top:12px;">员工相关订单（集团员工1,806 + 员工49）合计占 38.3%，是不容忽视的内部消化渠道。<br>无订单 2,705 辆中 2,571 辆仍在物流前阶段，为在途/未下线库存。</p>
</div>

<div class="card">
<h2>二、聚焦：用户车（2025 交付 1,118 辆）</h2>

<h3 style="font-size:15px;color:var(--zh-deep-blue);margin:16px 0 8px;">2.1 企业采购 vs 个人购买</h3>
<div class="dual-grid">
<div class="card" style="border-left:4px solid var(--status-positive);">
<h2>企业采购</h2>
<div class="kpi-card" style="box-shadow:none;padding:0;"><div class="value">179 辆</div><div class="label">统一社会信用代码</div></div>
<p style="font-size:13px;color:var(--zh-text);margin-top:8px;"><strong>全部为 L6</strong>，无一例外。说明 L6 是上汽销售体系下企业批量采购的主力车型。</p>
</div>
<div class="card" style="border-left:4px solid var(--zh-blue);">
<h2>个人购买</h2>
<div class="kpi-card" style="box-shadow:none;padding:0;"><div class="value">926 辆</div><div class="label">个人身份证</div></div>
<p style="font-size:13px;color:var(--zh-text);margin-top:8px;">个人购车占用户车总量的 <strong>82.8%</strong>。以下分析聚焦此群体。</p>
</div>
</div>

<h3 style="font-size:15px;color:var(--zh-deep-blue);margin:16px 0 8px;">2.2 个人购车画像总览</h3>
<div class="summary-grid">
<div class="summary-card"><div class="summary-value">39.2 岁</div><div class="summary-label">平均年龄</div><div class="summary-hint">中位数 38 岁</div></div>
<div class="summary-card"><div class="summary-value">61 : 39</div><div class="summary-label">男女比例</div><div class="summary-hint">男 564 / 女 362</div></div>
<div class="summary-card"><div class="summary-value">44.3%</div><div class="summary-label">上海户籍</div><div class="summary-hint">55.7% 外地户籍</div></div>
<div class="summary-card neutral"><div class="summary-value">99.6%</div><div class="summary-label">上海上牌</div><div class="summary-hint">922 / 926</div></div>
<div class="summary-card"><div class="summary-value">8 家</div><div class="summary-label">上海门店</div><div class="summary-hint">全部 parent_region=上海区</div></div>
<div class="summary-card warning"><div class="summary-value">50.5%</div><div class="summary-label">闵行颛桥集中度</div><div class="summary-hint">468 辆来自同一门店</div></div>
</div>

<div class="dual-grid">
<div>
<h3 style="font-size:14px;color:var(--zh-deep-blue);margin:8px 0;">车系分布</h3>
<table class="data-table">
<thead><tr><th>车系</th><th style="text-align:right;">数量</th><th style="text-align:right;">占比</th></tr></thead>
<tbody>
<tr><td><strong>LS6</strong></td><td class="num">681</td><td class="num">73.5%</td></tr>
<tr><td>L6</td><td class="num">200</td><td class="num">21.6%</td></tr>
<tr><td>LS9</td><td class="num">26</td><td class="num">2.8%</td></tr>
<tr><td>L7</td><td class="num">14</td><td class="num">1.5%</td></tr>
<tr><td>LS7</td><td class="num">5</td><td class="num">0.5%</td></tr>
</tbody>
</table>
</div>
<div>
<h3 style="font-size:14px;color:var(--zh-deep-blue);margin:8px 0;">代际分布</h3>
<table class="data-table">
<thead><tr><th>代际</th><th style="text-align:right;">数量</th><th>上市→锁单中位数</th></tr></thead>
<tbody>
<tr><td><strong>LS6 新一代</strong></td><td class="num">477</td><td><span class="badge badge-blue">19 天</span></td></tr>
<tr><td>LS6 全新（老款）</td><td class="num">204</td><td><span class="badge badge-muted">240 天</span></td></tr>
<tr><td>L6 全新</td><td class="num">177</td><td><span class="badge badge-blue">82 天</span></td></tr>
<tr><td>LS9</td><td class="num">26</td><td><span class="badge badge-gold">6 天</span></td></tr>
<tr><td>L6 经典</td><td class="num">23</td><td><span class="badge badge-muted">300 天</span></td></tr>
<tr><td>L7</td><td class="num">14</td><td>—</td></tr>
<tr><td>LS7</td><td class="num">5</td><td>—</td></tr>
</tbody>
</table>
</div>
</div>

<h3 style="font-size:14px;color:var(--zh-deep-blue);margin:16px 0 8px;">年龄 × 性别 × 车型</h3>
<div class="table-wrap">
<table class="report-table">
<thead><tr><th>车系</th><th style="text-align:right;">数量</th><th style="text-align:right;">年龄中位数</th><th style="text-align:right;">男</th><th style="text-align:right;">女</th><th style="text-align:right;">上海户籍</th><th style="text-align:right;">外地户籍</th></tr></thead>
<tbody>
<tr><td><strong>LS6</strong></td><td class="num">681</td><td class="num">38 岁</td><td class="num">441</td><td class="num">240</td><td class="num">287</td><td class="num">394</td></tr>
<tr><td>L6</td><td class="num">200</td><td class="num">36 岁</td><td class="num">93</td><td class="num">107</td><td class="num">98</td><td class="num">102</td></tr>
<tr><td>LS9</td><td class="num">26</td><td class="num">46 岁</td><td class="num">19</td><td class="num">7</td><td class="num">15</td><td class="num">11</td></tr>
<tr><td>L7</td><td class="num">14</td><td class="num">49 岁</td><td class="num">9</td><td class="num">5</td><td class="num">7</td><td class="num">7</td></tr>
<tr><td>LS7</td><td class="num">5</td><td class="num">47 岁</td><td class="num">2</td><td class="num">3</td><td class="num">3</td><td class="num">2</td></tr>
</tbody>
</table>
</div>
</div>

<div class="card">
<h2>三、门店分布 · 极度集中</h2>
<div class="table-wrap">
<table class="report-table">
<thead><tr><th>门店</th><th style="text-align:right;">销量</th><th style="text-align:right;">占比</th><th>累计占比</th></tr></thead>
<tbody>
<tr><td><strong>上海闵行颛桥</strong></td><td class="num">468</td><td class="num">50.5%</td><td>50.5%</td></tr>
<tr><td>上海东安路展厅</td><td class="num">222</td><td class="num">24.0%</td><td>74.5%</td></tr>
<tr><td>上海闵行龙湖天街</td><td class="num">92</td><td class="num">9.9%</td><td>84.4%</td></tr>
<tr><td>上海徐汇万科（换铺）</td><td class="num">85</td><td class="num">9.2%</td><td>93.6%</td></tr>
<tr><td>上海徐汇万科</td><td class="num">22</td><td class="num">2.4%</td><td>96.0%</td></tr>
<tr><td>上海浦东金桥</td><td class="num">17</td><td class="num">1.8%</td><td>97.8%</td></tr>
<tr><td>上海五角场合生汇</td><td class="num">14</td><td class="num">1.5%</td><td>99.4%</td></tr>
<tr><td>上海漕溪北路车城店</td><td class="num">6</td><td class="num">0.6%</td><td>100%</td></tr>
</tbody>
</table>
</div>
<div class="insight green">
<h4>关键发现</h4>
<p><strong>闵行颛桥一家独占 50.5%</strong>，前 3 家门店占 84.4%。8 家门店全部位于上海市，parent_region_name 全部为"上海区"——上汽销售体系下无跨区流动，所有车辆在上海市内闭环消化。</p>
</div>
</div>

<div class="card">
<h2>四、购买时间节奏</h2>

<div class="flow-chain" style="justify-content:center;">
<div class="flow-step" style="background:var(--zh-cyan-100);"><div class="n">226</div><div class="l">H1 锁单</div></div>
<span class="flow-arrow">→</span>
<div class="flow-step" style="background:var(--zh-cyan-100);"><div class="n">116</div><div class="l">7-8月</div></div>
<span class="flow-arrow">→</span>
<div class="flow-step" style="background:var(--zh-blue-100);border:2px solid var(--zh-raccoon-gold);"><div class="n" style="color:var(--zh-gold-700);">263</div><div class="l">9月 🚀</div></div>
<span class="flow-arrow">→</span>
<div class="flow-step" style="background:var(--zh-blue-100);"><div class="n">316</div><div class="l">Q4</div></div>
</div>

<p style="font-size:13px;color:var(--zh-muted);margin:8px 0 16px;">锁单量逐月：1-6月逐步爬坡 → 7-8月过渡 → <strong>9月 LS6 新一代上市引爆峰值</strong></p>

<table class="report-table">
<thead><tr><th>月份</th><th style="text-align:right;">锁单</th><th style="text-align:right;">LS6新一代</th><th style="text-align:right;">LS6全新(老)</th><th style="text-align:right;">L6全新</th><th style="text-align:right;">L6经典(老)</th><th style="text-align:right;">LS9</th></tr></thead>
<tbody>
<tr><td>1-4月</td><td class="num">103</td><td class="num">—</td><td class="num">80</td><td class="num">—</td><td class="num">21</td><td class="num">—</td></tr>
<tr><td>5月</td><td class="num">60</td><td class="num">—</td><td class="num">27</td><td class="num">32</td><td class="num">1</td><td class="num">—</td></tr>
<tr><td>6月</td><td class="num">63</td><td class="num">—</td><td class="num">33</td><td class="num">30</td><td class="num">—</td><td class="num">—</td></tr>
<tr><td>7月</td><td class="num">69</td><td class="num">—</td><td class="num">47</td><td class="num">19</td><td class="num">—</td><td class="num">—</td></tr>
<tr><td>8月</td><td class="num">47</td><td class="num">—</td><td class="num">14</td><td class="num">33</td><td class="num">—</td><td class="num">—</td></tr>
<tr><td><strong>9月</strong></td><td class="num"><strong>263</strong></td><td class="num" style="color:var(--zh-gold-700);font-weight:700;">241</td><td class="num">—</td><td class="num">21</td><td class="num">—</td><td class="num">—</td></tr>
<tr><td>10月</td><td class="num">118</td><td class="num">95</td><td class="num">—</td><td class="num">22</td><td class="num">—</td><td class="num">—</td></tr>
<tr><td>11月</td><td class="num">116</td><td class="num">79</td><td class="num">—</td><td class="num">13</td><td class="num">—</td><td class="num" style="color:var(--zh-blue);font-weight:600;">21</td></tr>
<tr><td>12月</td><td class="num">82</td><td class="num">62</td><td class="num">—</td><td class="num">7</td><td class="num">—</td><td class="num">5</td></tr>
</tbody>
</table>

<div class="insight gold">
<h4>关键发现：锁单→交付仅 19 天（中位数）</h4>
<p>从锁单到交付的中位数为 19 天、均值 25.6 天，这表明上汽销售体系下的销售模式不是订单制生产（通常 4-8 周），而是<strong>现车/准现车销售</strong>——车辆已经在库或即将到库，锁单即快速交付。</p>
</div>
</div>

<div class="card">
<h2>五、人口与身份特征</h2>

<h3 style="font-size:14px;color:var(--zh-deep-blue);margin:8px 0;">年龄分布</h3>
<table class="data-table" style="max-width:400px;">
<thead><tr><th>年龄段</th><th style="text-align:right;">人数</th><th style="text-align:right;">占比</th></tr></thead>
<tbody>
<tr><td>&lt;25 岁</td><td class="num">20</td><td class="num">2.2%</td></tr>
<tr><td>25-29 岁</td><td class="num">145</td><td class="num">15.7%</td></tr>
<tr><td><strong>30-39 岁</strong></td><td class="num"><strong>360</strong></td><td class="num"><strong>38.9%</strong></td></tr>
<tr><td><strong>40-49 岁</strong></td><td class="num"><strong>258</strong></td><td class="num"><strong>27.9%</strong></td></tr>
<tr><td>50-59 岁</td><td class="num">105</td><td class="num">11.3%</td></tr>
<tr><td>60+ 岁</td><td class="num">38</td><td class="num">4.1%</td></tr>
</tbody>
</table>

<h3 style="font-size:14px;color:var(--zh-deep-blue);margin:16px 0 8px;">身份证户籍地（Top 10）</h3>
<table class="data-table" style="max-width:400px;">
<thead><tr><th>省级代码</th><th style="text-align:right;">人数</th><th>对应省份</th></tr></thead>
<tbody>
<tr><td><strong>31</strong></td><td class="num"><strong>410</strong></td><td>上海市</td></tr>
<tr><td>32</td><td class="num">94</td><td>江苏省</td></tr>
<tr><td>34</td><td class="num">56</td><td>安徽省</td></tr>
<tr><td>41</td><td class="num">51</td><td>河南省</td></tr>
<tr><td>33</td><td class="num">42</td><td>浙江省</td></tr>
<tr><td>36</td><td class="num">34</td><td>江西省</td></tr>
<tr><td>37</td><td class="num">33</td><td>山东省</td></tr>
<tr><td>42</td><td class="num">27</td><td>湖北省</td></tr>
<tr><td>23</td><td class="num">23</td><td>黑龙江省</td></tr>
<tr><td>43</td><td class="num">17</td><td>湖南省</td></tr>
</tbody>
</table>

<div class="insight">
<h4>典型用户画像</h4>
<p><strong>38 岁、上海工作、外地户籍、在上海上牌、通过闵行颛桥或东安路门店购买 LS6 或 L6。</strong> 这是一群在上海稳定生活的新上海人/外来就业人口，以 30-39 岁中青年男性为主力，LS6 新一代上市（9月）后集中爆发锁单。</p>
</div>
</div>

<div class="card">
<h2>六、企业采购专题</h2>
<p style="font-size:13px;color:var(--zh-muted);margin-bottom:12px;">通过 owner_identity_no 中的统一社会信用代码（前2位 91 = 企业法人）识别。</p>
<table class="data-table" style="max-width:480px;">
<thead><tr><th>维度</th><th style="text-align:right;">数据</th></tr></thead>
<tbody>
<tr><td>企业购车总量</td><td class="num">179 辆</td></tr>
<tr><td>车系</td><td class="num">全部为 L6（100%）</td></tr>
<tr><td>证件类型</td><td class="num">统一社会信用代码（前2位 91）</td></tr>
<tr><td>buyer_identity_no</td><td class="num">全部为空 → buyer 端未登记</td></tr>
</tbody>
</table>
<div class="insight gold">
<h4>企业采购特征</h4>
<p>上汽销售名下的企业采购全部为 <strong>L6</strong>，buyer 端完全没有登记。这批交易在流程上标记为"用户车"但实际是 2B 交易。179 辆的 buyer_identity_no 均为空，而个人购买的 926 辆中有 541 辆 buyer 也为空——上汽销售体系下 buyer 信息录入存在系统性缺失。</p>
</div>
</div>

<div class="method-section">
<h2 class="section-title">口径与数据来源</h2>
<div class="method-grid">
<div class="method-item">
<div class="method-icon" style="background:var(--zh-blue-100);color:var(--zh-blue);">D</div>
<div class="method-body">
<strong>数据源</strong><br/>
delivery_inventory.parquet + order_data.parquet
</div>
</div>
<div class="method-item">
<div class="method-icon" style="background:var(--zh-gold-100);color:var(--zh-gold-700);">F</div>
<div class="method-body">
<strong>过滤条件</strong><br/>
bloc_name = "上汽销售" · order_type = "用户车"<br/>
delivery_date ∈ [2025-01-01, 2025-12-31]<br/>
个人购车 = owner_identity_no 为 18 位纯数字（末位可为 X）
</div>
</div>
<div class="method-item">
<div class="method-icon" style="background:#E8F8FD;color:#2D6FA3;">I</div>
<div class="method-body">
<strong>身份证识别规则</strong><br/>
企业：18 位，前 17 位含非 X 字母 → 统一社会信用代码<br/>
个人：18 位纯数字（末位可为 X）→ 个人身份证
</div>
</div>
<div class="method-item">
<div class="method-icon" style="background:#F3F6F8;color:#374151;">M</div>
<div class="method-body">
<strong>指标定义</strong><br/>
锁单→交付天数 = delivery_date - lock_time<br/>
户籍地 = owner_identity_no 前 2/6 位（行政区划代码）<br/>
门店集中度 = 各 store_name 绑定的订单占比
</div>
</div>
</div>
</div>

</main>

<footer>
<img class="brand-sig" src="{static}/assets/brand/zihao_signature_transparent.png" alt="Raccoon Research"/>
<div class="brand-sentence">用数据、AI 和一点点常识，研究复杂世界。</div>
</footer>

</body>
</html>'''.format(
    static=STATIC,
    date=datetime.now().strftime('%Y-%m-%d %H:%M')
)

Path(OUTPUT_HTML).write_text(HTML, encoding='utf-8')
print(f'报告已生成: {OUTPUT_HTML}')

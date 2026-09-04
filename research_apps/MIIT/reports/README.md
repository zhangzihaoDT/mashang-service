# reports/ —— 最终给人看的产出

打开本目录，看到的就是这个项目已经得出了什么结果。**不放 raw，不放 checkpoint，不放 parser 产物。**

## 结构

```
reports/
├── batch_409/
│   ├── scan_report.html      ← P1 品牌搜索简报
│   ├── category_report/      ← P5 分类车型对比（index + 4 分类页）
│   └── brand_report/         ← P5 单品牌车型对比（小米）
└── batch_410/
    ├── scan_report.html
    └── category_report/
```

## 生成命令

```bash
make miit-report BATCH=410
# 或分步
python3 MIIT/scripts/pipelines/scan_batch.py --from-scan --batch 410
python3 MIIT/scripts/reports/category_report.py --batch 410 --all --output-dir batch_410/category_report
python3 MIIT/scripts/reports/brand_report.py --archive-dir batch_409/小米 --tax-json batch_409/车型清单_第88批车船税.json --brand 小米 --output-dir batch_409/brand_report --batch "第409批"
```

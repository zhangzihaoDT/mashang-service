# Holdout Topics — 冻结代码泛化验证

**日期**：2026-08-18
**代码冻结**：commit `672c6b0`（v3 benchmark-driven capability closure），本次全程不修改代码。
**协议**：先定义题 → 冻结代码 → Agent 用既有 CLI 独立跑。

三个 Holdout 均未参与任何开发迭代（v1/v2/v3 从未用这些变量做过研究问题）。

---

## H1｜收入 × 产品魅力

- **研究问题**：家庭收入是否对应不同的产品魅力评价？
- **假设 H-001**：收入与 APEAL 存在非线性关系（中高收入带爬升/饱和）。
- **主要检验能力**：
  - ordinal segmentation（CN_INCOME 是有序 7 档）
  - **非线性**（是否存在收入档位跳升/饱和，而非单调线性）
  - **measurement artifact**（98=Prefer not to answer 必须被自动排除，不能成为 segment）
  - **confounder**（收入 vs 价格/品牌结构，收入效应是否独立）
- **变量**：CN_INCOME（7 档有序 + 98 拒答）
- **通过标准**：98 不进入 segment；能区分"非线性档位结构"与"被品牌/价格吸收"；confounder 检查后给出明确结论。

## H2｜品牌形象 × APEAL（perceptual / scale7）

- **研究问题**：用户对品牌的感知形象（如创新感、豪华感、可靠性、口碑）与产品魅力是什么关系？
- **假设 H-001**：创新/豪华/可靠/口碑等品牌形象维度与 APEAL 正相关。
- **主要检验能力**：
  - **scale7 语义差异量表**正确处理（不是普通连续变量/分类变量误读）
  - **correlation ≠ mechanism**（形象感知与 APEAL 相关 ≠ 形象驱动 APEAL；必须区分方向/机制，不能写成因果）
  - confounder / 结构解释（品牌形象与品牌本身、价格、车型结构高度内生）
- **变量**：YNV_CN_6_1..14（品牌形象 scale7：创新/豪华/可靠/口碑等）
- **通过标准**：量表按 7 点语义处理；相关矩阵输出；不把相关写成机制；对品牌内生性诚实降级。

## H3｜体验模块 → 总体魅力（driver analysis）

- **研究问题**：哪个体验模块（外观/驾驶/座舱/性能/舒适/安全/补能…）对总体 APEAL 贡献最大？
- **假设 H-001**：存在少数模块主导 APEAL（driver），其余为辅助。
- **主要检验能力**：
  - **correlation / regression**（模块指数 → APEAL）
  - **item drilldown**（driver 模块内部哪些题项贡献最大）
  - **collinearity**（模块之间高度相关，不能单独看单变量相关；需回归/标准化系数识别相对贡献）
- **变量**：APEAL_Index（因变量）+ 10 个模块指数 + 模块内 rating items
- **通过标准**：识别 driver 模块；控制共线性后的相对贡献；driver 内部 item 级下钻；明确这是"关联驱动"非"因果"。

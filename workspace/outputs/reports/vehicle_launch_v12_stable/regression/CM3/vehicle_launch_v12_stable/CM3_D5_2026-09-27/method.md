# vehicle-launch-deep-dive v1.2 稳定版口径

对象：CM3；对标：LS8、LS9；截止：2026-09-27；N=5。

数据源：dataset/order_data.parquet。上市日与归属：shared/schema/business_definition.json。

锁单：用户车，剔测试单、总部主理店及非零售，order_number 唯一。

小订池：允许空订单类型；intention_payment_time < 上市日，含配置预售起日前记录。

事件截止：各代际 lock_time / intention_refund_time < 上市日+N；锁与退可重叠。

来源：上市前小订、上市当日小订、无小订记录、上市日后残余，四项互斥完备。

分解：(P主-P标)×r标 + P主×(r主-r标) = 池锁单事件差。仅算术，不代表因果。

窗口：{'CM3': {'launch': '2026-09-23', 'window_end_exclusive': '2026-09-28', 'presale_start': '2026-09-10'}, 'LS8': {'launch': '2026-04-16', 'window_end_exclusive': '2026-04-21', 'presale_start': '2026-03-26'}, 'LS9': {'launch': '2025-11-12', 'window_end_exclusive': '2025-11-17', 'presale_start': '2025-11-04'}}

输入 SHA256：{'dataset/order_data.parquet': 'ce17aec76813ac8c9ca3f04c15d202e31a67a0827f376cfaee75d1ecdfc6e103', 'shared/schema/business_definition.json': 'c1310c398aa03882e29549fc1855c6885b91b3910a8d6416cd4c431102763d6f'}

限制：
- 历史重建使用当前订单快照与事件时间；代际、订单类型及退款等字段可能被事后回填，不等于历史冻结快照。
- 上市前小订池含早于配置预售开始日的记录，非严格预售期 cohort；预售天数不同，不据此判断需求强弱。
- 小订退款为日期粒度，只能按日比较；锁单与小订退款事件可重叠；不提供待转化、封盘剩余池、订单质量或后续潜力判断。
- 无小订记录只表示字段缺失，不能证明下单链路一致或直接需求强弱。
- 分解是指定基准下的算术恒等式，不是因果归因；不提供贡献占比或经营主次判断。

本次不提供：
- 区域与渠道专题：UNVERIFIED；未完成独立的计算、结论、呈现联合验收
- 网络与单店专题：UNVERIFIED；原始描述与归因未分离；舍入后网络分解及主次判断已判 FAIL
- 产品配置与客群：UNVERIFIED；局部数字核验不等于跨代际完整能力验证
- 同档客群：UNVERIFIED；相同电量不足以证明产品与客群可比，旧崩溃修复仅证明可运行
- 座椅及跨代际六座：UNVERIFIED；CM3 缺字段，未形成两个案例的有效比较证据
- 版本缺口解释差额：FAIL；把同电量存在性当版本可比依据，固定缺口及贡献占比判断不成立
- 订单质量与交付兑现：UNVERIFIED；历史快照回填与事件语义未完成独立验证
- 待转化、封盘剩余池与未来潜力：FAIL；锁单与小订退款事件重叠，直接相减重复扣除；流出速度混入非池锁单
- 竞争 PK：UNVERIFIED；series 粒度与代际粒度不一致，观察周可越过截止日
- 延长曲线与 PNG 导出：UNVERIFIED；不属于本次已验证的正式交付范围
- 经营主因、需求与购买力判断：FAIL；量纲混比、由占比推断流程、历史固定文案均缺乏成立依据

"""兼容入口，公共实现位于 utils.orders.classification。"""

from utils.orders.classification import (
    DEFAULT_GROUP as DEFAULT_GROUP,
    apply_series_group_logic as apply_series_group_logic,
    eval_series_group_logic_expr as eval_series_group_logic_expr,
    rule_condition as rule_condition,
    rule_priority as rule_priority,
)

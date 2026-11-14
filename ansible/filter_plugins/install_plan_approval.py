"""Filter for the global OLM approval switch (`zuno_operator_install_plan_approval`).

The operator Subscriptions are rendered by a vendored `operator` sub-chart, so the approval mode sits at a different
depth in each chart's values.yaml (`operator.subscription.operator.installPlanApproval`,
`operator.subscription.installPlanApproval`, ...). `install_plan_approval_overrides` walks a chart's default values
and returns only the nested dict that sets every `installPlanApproval` key to one value, ready to be merged into the
Application's Helm values. Nothing else of the chart is touched.
"""
from __future__ import annotations

KEY = "installPlanApproval"
ALLOWED = ("Automatic", "Manual")


def _walk(node):
    if not isinstance(node, dict):
        return {}
    out = {}
    for key, value in node.items():
        if key == KEY and isinstance(value, str):
            out[key] = True
        elif isinstance(value, dict):
            sub = _walk(value)
            if sub:
                out[key] = sub
    return out


def _fill(tree, approval):
    return {k: (approval if v is True else _fill(v, approval)) for k, v in tree.items()}


def install_plan_approval_overrides(chart_values, approval):
    """The minimal nested dict that sets each `installPlanApproval` of `chart_values` to `approval`."""
    if approval not in ALLOWED:
        raise ValueError(f"zuno_operator_install_plan_approval must be one of {ALLOWED}, got {approval!r}")
    return _fill(_walk(chart_values or {}), approval)


class FilterModule:
    def filters(self):
        return {"install_plan_approval_overrides": install_plan_approval_overrides}

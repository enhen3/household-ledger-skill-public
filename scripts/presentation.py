"""Additive, evidence-limited CLI feedback; never infer accounting state."""


def processing_summary(operation, *, read_rows=None, pending=None,
                       candidate_included=None, failure_reason=None,
                       source_detail=None):
    # Counts describe this command only. Source rows and candidate transactions
    # are different units; repeated commands must not be added together.
    show = lambda value: "未知" if value is None else str(value)
    failed = 1 if failure_reason is not None else 0
    return {
        "schema_version": 1,
        "operation": operation,
        "scope": "current_command_only",
        "read_rows": read_rows,
        "suspected_duplicate_rows": None,
        "confirmed_duplicate_rows": None,
        "pending_items": pending,
        "candidate_transactions": candidate_included,
        "failed_operations": failed,
        "failed_rows": None,
        "failure_reason": failure_reason,
        "source_detail": source_detail,
        "production_published": False,
        "text": (
            f"读入：{show(read_rows)} 行；疑似重复：未知（未独立计数）；"
            f"待确认：{show(pending)} 项；候选已包含：{show(candidate_included)} 笔；"
            f"失败：{failed} 次操作（失败行数未知）。正式入账：未执行。"
            + (f" 原因：{failure_reason}；来源行：{source_detail or '未知，按原错误核查'}。"
               if failed else " 各阶段计数不可相加；银行与平台关联不等于确认重复。")
        ),
    }

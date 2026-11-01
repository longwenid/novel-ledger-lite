"""Declared shape of the frozen task material shared by compiler and delivery.

lite 版：从完整版裁剪——去掉开书门/修订/返修链的 payload 键，登记差量信封自己的键
（组级共享包、锚句、显式告警）。两条规则不变：信封不得静默长字段；payload 的键
也必须在表里声明后才允许出现在冻结输入中。
"""
from __future__ import annotations

from .contracts import require

# Fields the freeze compiler always produces. The brief is optional.
WORK_FIELDS = ('schema', 'stage', 'chapter', 'scope', 'first', 'last', 'payload', 'branch',
               'revision', 'records', 'required', 'narrative_tracking',
               'capabilities', 'policy')
# `warnings` 是差量信封的显式告警通道（报告第三刀：conservative 回退不静默裁剪）——
# 告警随冻结输入走，Worker 与主控都能看见，不另发消息。
WORK_OPTIONAL = ('brief', 'build', 'warnings', 'group')

# `payload` is the one work field whose contents a stage decides on, so its keys are declared too.
WORK_PAYLOAD_FIELDS = (
    'mode',                                                      # redesign / bounded outline repair
    'volume', 'from_chapter', 'volume_outline', 'chapter_outline',
    'design_drift',                                              # drift rows the chapter must absorb
    'hooks', 'style', 'word_budget', 'editorial', 'worker_batch',
    'group_pack',                                                # 组级共享包指针（每组一份）
    'anchor',                                                    # 前情/场景锚句引用的记录名
)

TASK_FIELDS = ('schema', 'task_id', 'input_hash', 'stage', 'chapter', 'scope',
               'task_path', 'result_path', 'project_path',
               'process', 'requires_new_worker', 'version', 'claim', 'baseline',
               'commands', 'stages', 'note', 'redispatch_count', 'material_bytes')
TASK_OPTIONAL = ('brief', 'guides', 'input_path', 'template_path',
                 'records', 'required', 'brief_path', 'warnings', 'group')


def _validate(value, fields, optional, code, label):
    require(isinstance(value, dict), code, label + '必须是对象。')
    unknown = sorted(set(value) - set(fields) - set(optional))
    require(not unknown, code, label + '出现未声明字段，需先登记再使用。',
            {'unknown_fields': unknown})
    missing = sorted(set(fields) - set(value))
    require(not missing, code, label + '缺少必需字段。', {'missing_fields': missing})
    return value


def validate_work(value):
    """The frozen input a task is dispatched with."""
    _validate(value, WORK_FIELDS, WORK_OPTIONAL, 'envelope_input', '冻结输入')
    payload = value['payload']
    require(isinstance(payload, dict), 'envelope_input', '冻结输入的 payload 必须是对象。')
    unknown = sorted(set(payload) - set(WORK_PAYLOAD_FIELDS))
    require(not unknown, 'envelope_input', '冻结输入的 payload 出现未声明字段，需先登记再使用。',
            {'unknown_fields': unknown})
    return value

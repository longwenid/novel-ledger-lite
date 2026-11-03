"""Declared wire shape of frozen writing tasks.

信封与 payload 字段均须登记；未知字段不能静默进入冻结材料。"""
from __future__ import annotations

from .contracts import TASK, require

# Fields the freeze compiler always produces. The brief is optional.
WORK_FIELDS = ('schema', 'stage', 'chapter', 'scope', 'first', 'last', 'payload', 'branch',
               'revision', 'records', 'required', 'narrative_tracking',
               'capabilities', 'policy', 'delivery')
WORK_OPTIONAL = ('brief', 'warnings', 'group')

# Writing tasks carry a chapter-outline record reference and the batch flag.
WORK_PAYLOAD_FIELDS = ('chapter_outline', 'worker_batch')


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
    require(isinstance(value, dict) and value.get('schema') == TASK, 'envelope_schema',
            '仅支持当前派工格式。', {'expected': TASK})
    _validate(value, WORK_FIELDS, WORK_OPTIONAL, 'envelope_input', '冻结输入')
    payload = value['payload']
    _validate(payload, WORK_PAYLOAD_FIELDS, (), 'envelope_input', '冻结输入的 payload')
    require(isinstance(value['records'], dict) and isinstance(value['required'], list)
            and all(name in value['records'] for name in value['required']),
            'envelope_input', '必读清单须全部指向已有记录。')
    ref = payload.get('chapter_outline')
    require(isinstance(ref, str) and ref in value['required'],
            'envelope_input', '章纲 payload 须引用唯一的必读章纲记录。')
    require(all(name in value['required'] for name in (
        'core_context', 'chapter_outline', 'state', 'dependencies', 'recall_manifest', 'style')),
        'envelope_input', '每章核心约束、章纲、状态、依赖、补读目录与文风须必读。')
    delivery = value['delivery']
    require(isinstance(delivery, dict) and set(delivery) == {'context_id', 'cached', 'mode'},
            'envelope_input', '交付元数据须符合当前格式。')
    cached = delivery['cached']
    require(isinstance(cached, dict)
            and delivery['mode'] == ('acknowledged_cache' if cached else 'self_contained')
            and (not cached or isinstance(delivery.get('context_id'), str) and delivery['context_id'].strip())
            and all(name in value['records'] and key == value['records'][name]
                    and name not in value['required'] for name, key in cached.items()),
            'envelope_input', '缓存省略必须对应当前会话确认的准确文档版本。')
    return value

"""独立的长篇小说写作执行引擎：冻结章纲、差量上下文、逐章核账与全量验收。

所有运行模块随本包提供；使用方式与约束见技能目录的 SKILL.md。"""
from .contracts import VERSION, SCHEMA, Error, require, digest, han_count

__all__ = ['VERSION', 'SCHEMA', 'Error', 'require', 'digest', 'han_count']

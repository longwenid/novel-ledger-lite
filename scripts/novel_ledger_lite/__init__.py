"""novel-ledger-lite：五层账本＋差量信封的精简引擎（「章纲资源冻结→快速执笔」最小完整闭环）。

模块分层（与完整版 novel_ledger 的分工见 SKILL.md / references/boundary.md）：
- contracts/planning/envelope     线契约、档位、信封形状（lite 裁剪版）
- entities/evidence/facts/narrative/spatial/continuity/craft
                                  判定底盘（完整版逐字同源，一字未改）
- story_memory                    章纲登记制（bind 协议水位索引化）
- drift/drift_simulation/drift_validation/drift_reconcile
                                  机械漂移防线（完整版逐字同源）
- lint/style                      8 章重复窗＋文风代理（完整版逐字同源）
- world                           世界登记表（lite 裁剪版）
- store                           lite 存储（内容寻址＋有界 headers）
- delta/anchors/compose           五层账本 L3/L4 与差量信封（lite 新逻辑）
- pipeline                        最小完整闭环编排
- book_state                      lite 形状不变式（含漂移行登记校验）
"""
from .contracts import VERSION, SCHEMA, Error, require, digest, han_count

__all__ = ['VERSION', 'SCHEMA', 'Error', 'require', 'digest', 'han_count']

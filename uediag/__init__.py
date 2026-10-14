"""UE5 智诊助手。

分工：`agent.py` 与 `tools.py` 是核心（人写的部分），其余是本模块提供的通用件：
    types      数据契约 + 配置
    logparse   日志收敛 clean_log()
    kb         知识库：加载 / BGE-M3 编码 / Chroma 入库与检索
    llm        模型客户端（文本 + 视觉）
    trace      轨迹记录与时间线打印
    report     报告渲染
"""

__version__ = "0.1.0"

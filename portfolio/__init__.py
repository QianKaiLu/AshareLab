"""波段账户的交易记录、便签与止损计划存储。

三个 swing skill（trade / daily / review）共享本包，不各自复制脚本。

    store     JSONL 读写与字段校验
    position  持仓、加权成本、盈亏（从 trades 现算，不落盘）
    cli       命令行入口
"""

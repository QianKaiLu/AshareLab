import logging
from pathlib import Path
import colorlog

# 配置日志
LOG_DIR = Path(__file__).parent.parent / "logs"
LOG_DIR.mkdir(parents=True, exist_ok=True)

# 日志文件
FETCH_LOG_FILE = LOG_DIR / "fetch_data.log" # 采集数据日志
ANALYZE_LOG_FILE = LOG_DIR / "analyze.log" # 数据分析日志

formatter = logging.Formatter('%(asctime)s - %(levelname)s - %(message)s')

fetch_logger = logging.getLogger("fetch_data")
fetch_logger.setLevel(logging.INFO)
fetch_logger.propagate = False # ⚠️ 关闭向上传播，避免被 root logger 重复打印

log_colors = {
    'DEBUG':    'bold_cyan',
    'INFO':     'bold_green',
    'WARNING':  'bold_yellow',
    'ERROR':    'bold_red',
    'CRITICAL': 'bg_bold_red,white',
}

formatter_console = colorlog.ColoredFormatter(
    fmt='%(log_color)s%(asctime)s - %(levelname)s - %(message)s',
    log_colors=log_colors,
    reset=True
)

console_handler = colorlog.StreamHandler()
console_handler.setFormatter(formatter_console)

fetch_file_handler = logging.FileHandler(FETCH_LOG_FILE, encoding='utf-8')
fetch_file_handler.setFormatter(formatter)
fetch_file_handler.setLevel(logging.WARN)

fetch_logger.addHandler(console_handler)
fetch_logger.addHandler(fetch_file_handler)

analyze_logger = logging.getLogger("analyze")
analyze_logger.setLevel(logging.INFO)
analyze_logger.propagate = False

analyze_file_handler = logging.FileHandler(ANALYZE_LOG_FILE, encoding='utf-8')
analyze_file_handler.setFormatter(formatter)
analyze_file_handler.setLevel(logging.WARN)

analyze_logger.addHandler(console_handler)
analyze_logger.addHandler(analyze_file_handler)

def get_fetch_logger():
    return fetch_logger

def get_analyze_logger():
    return analyze_logger
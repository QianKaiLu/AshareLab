from typing import Tuple
import re
import datetime

MARKED_CLOSE_HOUR = 16

def get_exchange_by_code(code: str) -> Tuple[str, str]:
    """
    根据 A 股6位数字代码判断所属交易所（支持沪 / 深 / 北）
    
    Args:
        code (str): 6位股票代码，如 "601127", "300750", "835185", "920001"

    Returns:
        str: "SH"=上交所, "SZ"=深交所, "BJ"=北交所

    Raises:
        ValueError: 代码格式错误或不支持
    """
    if not isinstance(code, str) or not code.isdigit() or len(code) != 6:
        raise ValueError(f"invalid ashare stock code format: {code}, should be 6 digits string")
    
    if code.startswith(('60', '68', '688')):
        return ("SH", "上海证券交易所")
    elif code.startswith(('00', '30')):
        return ("SZ", "深圳证券交易所")
    elif code.startswith(('8', '9')):
        return ("BJ", "北京证券交易所")
    else:
        raise ValueError(f"unsupported ashare stock code: {code}")

def to_std_code(code: str) -> str:
    """
    Convert various stock code formats to standardized 6-digit string.
    
    Examples:
        '321' -> '000321'
        '000321' -> '000321'
        'SH600000' -> '600000'
        '600000.SH' -> '600000'
        'sz000800' -> '000800'
        '159915.SZ' -> '159915'

    Args:
        code (str): Raw stock code input

    Returns:
        str: Standardized 6-digit code, e.g. '000321'

    Raises:
        ValueError: If unable to extract valid 6-digit code
    """
    if not isinstance(code, str):
        raise TypeError(f"Expected str, got {type(code)}")

    code = code.strip()

    if not code:
        raise ValueError("Empty code input")

    digits = re.findall(r'\d+', code)
    if not digits:
        raise ValueError(f"No digits found in code: {code}")

    main_digits = max(digits, key=len)

    if len(main_digits) == 6:
        return main_digits
    elif len(main_digits) < 6:
        padded = main_digits.zfill(6)
        if len(padded) > 6:
            raise ValueError(f"Padded code exceeds 6 digits: {padded}")
        return padded
    else:
        raise ValueError(f"Digit sequence too long ({len(main_digits)} > 6): {main_digits}")

def to_dot_ex_code(code: str) -> str:
    """
    Convert various stock code formats to 'XXXXXX.EX' format.
    
    Examples:
        '321' -> '000321.SZ'
        '000321' -> '000321.SZ'
        'SH600000' -> '600000.SH'
        '600000.SH' -> '600000.SH'
        'sz000800' -> '000800.SZ'
        '159915.SZ' -> '159915.SZ'

    Args:
        code (str): Raw stock code input

    Returns:
        str: Code in 'XXXXXX.EX' format

    Raises:
        ValueError: If unable to determine exchange or extract valid code
    """
    std_code = to_std_code(code)
    exchange_code, _ = get_exchange_by_code(std_code)
    return f"{std_code}.{exchange_code}"

import datetime

def latest_trade_day() -> datetime.date:
    now = datetime.datetime.now()
    today = now.date()
    weekday = today.weekday()  # Monday=0, Sunday=6

    today_closed = now.hour >= MARKED_CLOSE_HOUR

    if weekday == 0:  # Monday
        return today if today_closed else today - datetime.timedelta(days=3)  # last Friday
    elif 1 <= weekday <= 4:  # Tuesday to Friday
        return today if today_closed else today - datetime.timedelta(days=1)
    elif weekday == 5:  # Saturday → last Friday
        return today - datetime.timedelta(days=1)
    else:  # Sunday → last Friday
        return today - datetime.timedelta(days=2)

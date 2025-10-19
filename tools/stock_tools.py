from typing import Tuple

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


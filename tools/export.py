import pandas as pd
from pathlib import Path
from tools.log import get_fetch_logger
from typing import Optional
import subprocess
import sys
from datas.query_stock import get_stock_info_by_code

logger = get_fetch_logger()
EXPORT_PATH = Path(__file__).parent.parent / "output"

def export_bars_to_csv(
    df: pd.DataFrame,
    only_base_info: bool = False,
    output_dir: Path = EXPORT_PATH,
    open_folder_after: bool = False
) -> Optional[Path]:
    """
    Export DataFrame to CSV file with formatted name and ensure directory exists.
    
    Args:
        df (pd.DataFrame): The daily bar data to export
        code (str): Stock code for filename
        output_dir (str): Directory to save files, default "output/bars"
        open_folder_after (bool): Whether to open folder after saving
    
    Returns:
        Path object of saved file, or None if failed
    """
    if df is None or df.empty:
        logger.warning("Cannot export: Empty or None DataFrame.")
        return None

    try:
        output_dir.mkdir(parents=True, exist_ok=True)

        code = df['code'].iloc[0]
        start_date = df['date'].min().strftime("%Y%m%d")
        end_date = df['date'].max().strftime("%Y%m%d")

        pre_name = f"{code}"
        stock_info = get_stock_info_by_code(code)
        if not stock_info.empty:
            stock_name = stock_info.at[code, 'name']
            if stock_name:
                pre_name = f"{stock_name}({code})"

        filename = f"{pre_name}_{start_date}_{end_date}.csv"
        file_path = output_dir / filename

        if only_base_info:
            base_info_cols = ['code', 'date', 'open', 'close', 'high', 'low', 'volume']
            df = df[base_info_cols]

        df.to_csv(file_path, index=False, encoding='utf-8-sig')

        logger.info(f"✅ Data exported to: {file_path}")

        if open_folder_after:
            try:
                if sys.platform == "win32":
                    subprocess.run(["explorer", str(output_dir.resolve())], check=True)
                elif sys.platform == "darwin":  # macOS
                    subprocess.run(["open", str(output_dir.resolve())], check=True)
                else:
                    subprocess.run(["xdg-open", str(output_dir)], check=True)
                logger.info(f"📁 Opening folder: {output_dir}")
            except Exception as e:
                logger.warning(f"⚠️ Failed to open folder: {e}")

        return file_path

    except Exception as e:
        logger.error(f"❌ Failed to export data: {e}", exc_info=True)
        return None
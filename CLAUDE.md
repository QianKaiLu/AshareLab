# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

AshareLab is a comprehensive Chinese A-share stock analysis system that combines market data fetching, technical analysis, AI-powered insights, and visualization. The system is built around a SQLite database (`database/ashare_data.db`) and supports parallel processing workflows.

## Common Development Commands

### Environment Setup
```bash
# Create and activate virtual environment
python -m venv .venv && source .venv/bin/activate  # macOS/Linux
# or
python -m venv .venv && .venv\Scripts\activate     # Windows

# Install dependencies
pip install -r requirements.txt

# Install CLI tool (optional)
pip install -e .
```

### Data Management
```bash
# Fetch/update all market data (parallel, uses ThreadPoolExecutor with 8 workers)
python datas/fetch_all_market.py

# Fetch latest K-lines for all stocks
python workflow/fetch_latest_klines.py

# Create or rebuild database schema
python datas/create_database.py
```

### Running Analysis Workflows
```bash
# Run hunting strategies (finds stock candidates)
python workflow/hunt_breakout_pullback.py    # Low volume pullback strategy
python workflow/hunt_wyckoff.py              # Wyckoff accumulation patterns
python workflow/hunt_both.py                 # Combined strategies with intersection

# Generate stock visualization cards
python workflow/draw_stock_cards.py

# AI-powered stock analysis (requires API key in .env)
python workflow/ai_analyses_stock.py

# Video analysis pipeline (download → transcribe → summarize)
python workflow/ai_video_analyses.py
```

### Testing
```bash
# Run all tests
pytest

# Run specific test with console output
pytest -k hunt_machine -s

# Run tests for a specific module
pytest tests/test_<module>.py -v
```

### CLI Tool
```bash
# After pip install -e .
stock-info --help
```

## High-Level Architecture

### Data Flow Pipeline

```
Data Sources (AKShare/Tushare)
    ↓
Fetchers (datas/fetch_stock_bars.py)
    ↓
SQLite Database (database/ashare_data.db)
    ↓ query_stock.py
DataFrames + Technical Indicators
    ↓
Hunters/Workflows/Visualizations/AI Analysis
    ↓
Output (CSV/Images/Markdown Reports)
```

### Core Module Organization

**datas/**: Data fetching and database operations
- `create_database.py`: Schema management with WAL mode
- `fetch_stock_bars.py`: Unified fetching logic with fallback (AKShare → Tushare)
- `fetch_all_market.py`: Parallel batch fetcher with queue-based writer pattern
- `query_stock.py`: Central query interface for all data access
- Database: Two main tables (`stock_base_info`, `stock_bars_daily_qfq`)

**hunter/**: Stock scanning and strategy framework
- `hunt_machine.py`: Generic parallel scanning engine using ThreadPoolExecutor
- Strategy modules return `HuntResult` objects with stock metadata
- Strategies are pure functions accepting DataFrames, returning truthy values or dicts

**workflow/**: Ready-to-run orchestration scripts
- Compose multiple modules into complete pipelines
- All artifacts output to `output/` directory
- Support both batch and targeted analysis

**indicators/**: Technical indicator implementations
- Each indicator has standalone function + DataFrame integration pattern
- Use `inplace=True` for memory efficiency
- All indicators work with standard OHLCV column names

**draws/**: Multi-layer visualization system
- Theme layer: `kline_theme.py` with ThemeRegistry
- Figure factories: `kline_fig_factory.py` (standard 2-panel, ztalk 4-panel)
- Card rendering: `kline_card.py` (Plotly → PIL → Base64)
- Uses Plotly for chart generation with high DPI rendering

**ai/**: AI analysis components
- OpenAI-compatible API interface (supports QianWen, DeepSeek, etc.)
- Jinja2 template-based prompts in `ai/prompts/`
- Multimodal support (CSV data + chart images + news articles)
- Streaming markdown output

**media_factory/**: Video processing pipeline
- `yt_dlp.py`: Video downloader (Bilibili, YouTube support)
- `video_handler.py`: Audio extraction via moviepy
- `whisper_mlx.py`: Apple Silicon-optimized speech-to-text
- Integration with AI for transcript summarization

**tools/**: Cross-cutting utilities
- Logging: `get_fetch_logger()`, `get_analyze_logger()` → `logs/`
- Path management: `EXPORT_PATH` for output artifacts
- Stock code formatting: `to_std_code()`, `to_dot_ex_code()`
- Rate limiting: Tushare token rotation system

### Key Technical Patterns

**Database Access Pattern**:
- All queries go through `datas/query_stock.py`
- UPSERT logic for efficient incremental updates
- Queue-based writer for concurrent batch operations
- Forward adjustment (前复权/qfq) is standard

**Indicator Integration Pattern**:
```python
# Always add indicators before analysis
from indicators.macd import add_macd_to_dataframe
from indicators.kdj import add_kdj_to_dataframe

df = query_daily_bars(code, start_date, end_date)
add_macd_to_dataframe(df, inplace=True)
add_kdj_to_dataframe(df, inplace=True)
# Now df has MACD_DIF, MACD_DEA, MACD_BAR, K, D, J columns
```

**Strategy Implementation Pattern**:
```python
def analyze_my_strategy(code: str, min_bars: int = 120) -> dict | bool:
    """
    Analyzer function for HuntMachine.

    Returns:
        dict: {metric1: value1, ...} if conditions met
        False/None: if no signal
    """
    bars = query_latest_bars(code, limit=min_bars)
    if len(bars) < min_bars:
        return False

    add_indicators_to_dataframe(bars, inplace=True)

    # Your logic here
    if conditions_met:
        return {"price": bars.iloc[-1]["close"], "signal": "buy"}
    return False
```

**Workflow Composition Pattern**:
```python
# 1. Fetch/update data
from datas.fetch_stock_bars import update_daily_bars_for_code

# 2. Query with indicators
from datas.query_stock import query_latest_bars
from indicators.macd import add_macd_to_dataframe

# 3. Generate visualization
from draws.kline_card import create_kline_card_image

# 4. AI analysis (optional)
from ai.ai_kbar_analyses import analyze_stock_with_ai

# 5. Export results
from tools.export import export_to_csv, save_markdown_report
```

**Concurrency Pattern**:
- Use `ThreadPoolExecutor` for I/O-bound operations (data fetching, scanning)
- Use queue-based writer when multiple threads need to write to SQLite
- Default worker count: 8 for data fetching, 20 for hunting

## Configuration and Secrets

**Environment Variables** (`.env` file):
- `TUSHARE_TOKEN`: Tushare API token (or use token rotation in `config.py`)
- `QIANWEN_API_KEY`: QianWen AI API key
- Additional API keys as needed

**Configuration Files**:
- `config.py`: Central config (API keys, Tushare tokens array)
- `ai/config.py`: AI API profiles and model configurations

**Database Location**:
- Fixed path: `database/ashare_data.db` (2.4 GB typical size)
- Uses WAL mode for concurrent read performance

## Important Implementation Details

**Stock Code Formats**:
- Standard format: 6-digit string (e.g., "000001")
- Tushare format: includes exchange suffix (e.g., "000001.SZ")
- Use `tools/stock_tools.py` for conversions

**Date Handling**:
- Database stores dates as strings (YYYYMMDD format)
- Use `tools/times.py` for date operations
- Always work with trading days, not calendar days

**Data Adjustment**:
- All price data uses forward adjustment (前复权/qfq)
- This is critical for technical analysis accuracy
- Never mix adjusted and unadjusted data

**Rate Limiting**:
- Tushare has strict rate limits; token rotation system in `config.py`
- AKShare is primary source (fewer restrictions)
- Implement retry logic with exponential backoff for production workflows

**Output Management**:
- All generated artifacts go to `output/` directory
- Log files accumulate in `logs/` (rotate/trim regularly)
- Don't commit large CSV files or database to git

## Testing Considerations

- Tests assume `database/ashare_data.db` exists with data
- Run `python datas/fetch_all_market.py` before running tests
- Mock `query_all_stock_code_list` to limit test runtime
- Integration tests exercise real database queries

## Coding Conventions

- Follow PEP 8: snake_case for functions/modules, CamelCase for classes
- Use type hints consistently
- Use project loggers from `tools.log` instead of creating new ones
- Commit messages: present tense, concise (e.g., "add macd indicator", "fix volume calculation")

import akshare as ak

def main():
    stock_zh_a_hist_df = ak.stock_zh_a_hist(symbol="002594", period="daily", start_date="20251001", end_date='20251027', adjust="")
    print(stock_zh_a_hist_df)

if __name__ == "__main__":
    main()
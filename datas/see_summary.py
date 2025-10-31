import akshare as ak

def main():
    # stock_zh_a_hist_df = ak.stock_zh_a_hist(symbol="002594", period="daily", start_date="20251001", end_date='20251027', adjust="")
    # print(stock_zh_a_hist_df.dtypes)
    
    stock_news_df= ak.stock_news_em(symbol="002460")
    stock_news_dict = stock_news_df.to_dict(orient='records')

if __name__ == "__main__":
    main()
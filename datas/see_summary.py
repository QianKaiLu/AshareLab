import akshare as ak

def main():
    stock_sse_summary_df = ak.stock_sse_summary()
    print(stock_sse_summary_df)

    stock_individual_basic_info_xq_df = ak.stock_individual_basic_info_xq(symbol="SH601127")
    print(stock_individual_basic_info_xq_df)

if __name__ == "__main__":
    main()
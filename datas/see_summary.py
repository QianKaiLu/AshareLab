import akshare as ak

def main():
    stock_info_sh_name_code_df = ak.stock_info_sh_name_code(symbol="主板A股")
    print(stock_info_sh_name_code_df)

if __name__ == "__main__":
    main()
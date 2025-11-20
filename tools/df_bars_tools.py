import pandas as pd

@pd.api.extensions.register_dataframe_accessor("bars")
class MyExtAccessor:
    def __init__(self, pandas_obj):
        self._obj = pandas_obj
    
    def last_n_days(self, n: int) -> pd.DataFrame:
        """
        Get the last n days of data from the DataFrame.
        """
        return self._obj.sort_values(by='date', inplace=True).tail(n)
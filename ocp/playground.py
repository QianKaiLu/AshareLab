from scipy.signal import find_peaks
import numpy as np
from datas.query_stock import query_latest_bars
import pandas as pd

x = np.array([0, 5, 3, 7, 2, 6, 1])
peaks, _ = find_peaks(x, prominence=2)

print("Peaks at indices:", peaks)

df = query_latest_bars("002534", n=30)
print(df)

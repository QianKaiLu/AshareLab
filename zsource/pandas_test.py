import dash
from dash import dcc, html, Input, Output
import plotly.express as px
import pandas as pd
from pathlib import Path

print(Path(__file__).parent.resolve())
print(Path.cwd())
print(__file__)

# # 示例数据
# df = pd.read_csv('https://raw.githubusercontent.com/plotly/datasets/master/gapminderDataFiveYear.csv')

# app = dash.Dash(__name__)

# app.layout = html.Div([
#     html.H1("全球人口数据看板"),
    
#     # 筛选器：年份下拉框
#     dcc.Dropdown(
#         id='year-dropdown',
#         options=[{'label': str(year), 'value': year} for year in df['year'].unique()],
#         value=2007  # 默认值
#     ),
    
#     # 图表容器
#     dcc.Graph(id='population-graph')
# ])

# # 回调函数：当用户选择年份，更新图表
# @app.callback(
#     Output('population-graph', 'figure'),
#     Input('year-dropdown', 'value')
# )
# def update_graph(selected_year):
#     filtered_df = df[df['year'] == selected_year]
#     fig = px.scatter(
#         filtered_df,
#         x='gdpPercap',
#         y='lifeExp',
#         size='pop',
#         color='continent',
#         hover_name='country',
#         log_x=True,
#         size_max=60
#     )
#     return fig

# if __name__ == '__main__':
#     app.run(debug=True)

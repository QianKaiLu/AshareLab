from plotly.graph_objects import Figure

def add_subplot_bg(fig, row, color, opacity=0.04):
    fig.add_shape(
        type="rect",
        xref="paper",
        yref="paper",
        x0=0,
        x1=1,
        y0=fig.get_subplot(row, 1).yaxis.domain[0],
        y1=fig.get_subplot(row, 1).yaxis.domain[1],
        fillcolor=color,
        opacity=opacity,
        layer="below",
        line_width=0,
    )
    
def compute_row_paper_domains(row_heights, vertical_spacing):
    total_height = sum(row_heights)
    norm_heights = [h / total_height for h in row_heights]

    domains = []
    y_top = 1.0
    for h in norm_heights:
        y_bottom = y_top - h
        domains.append((y_bottom, y_top))
        y_top = y_bottom - vertical_spacing

    return domains

def add_row_background(fig, y0, y1, color, opacity=0.04):
    fig.add_shape(
        type="rect",
        xref="paper",
        yref="paper",
        x0=0,
        x1=1,
        y0=y0,
        y1=y1,
        fillcolor=color,
        opacity=opacity,
        line_width=0,
        layer="below",
    )
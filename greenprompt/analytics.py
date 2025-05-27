

import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
from plotly.subplots import make_subplots
from greenprompt.dbconn import get_prompt_usage

def load_usage_data():
    """
    Load usage data from the SQLite database into a pandas DataFrame.
    """
    data = get_prompt_usage()
    df = pd.DataFrame(data)
    df['timestamp'] = pd.to_datetime(df['timestamp'])
    return df

def total_prompts_energy_usage(df):
    """
    Display total number of prompts and total energy usage.
    """
    total_prompts = len(df)
    total_energy = df['energy_wh'].sum()
    total_cpu = df['cpu_power_w'].sum()
    total_gpu = df['gpu_power_w'].sum()
    total_tokens = df['total_tokens'].sum()
    energy_per_token = total_energy / total_tokens if total_tokens > 0 else 0

    fig = make_subplots(
        rows=2, cols=3,
        specs=[[{"type": "domain"}]*3, [{"type": "domain"}]*3]
    )

    fig.add_trace(go.Indicator(
        mode="number",
        value=total_prompts,
        title={"text": "Total Prompts"}
    ), row=1, col=1)

    fig.add_trace(go.Indicator(
        mode="number",
        value=total_energy,
        title={"text": "Total Energy Usage (Wh)"}
    ), row=1, col=2)

    fig.add_trace(go.Indicator(
        mode="number",
        value=total_cpu,
        title={"text": "Total CPU Usage (W)"}
    ), row=1, col=3)

    fig.add_trace(go.Indicator(
        mode="number",
        value=total_gpu,
        title={"text": "Total GPU Usage (W)"}
    ), row=2, col=1)

    fig.add_trace(go.Indicator(
        mode="number",
        value=total_tokens,
        title={"text": "Total Tokens Used"}
    ), row=2, col=2)

    fig.add_trace(go.Indicator(
        mode="number",
        value=energy_per_token,
        number={'valueformat': '.6f'},
        title={"text": "Energy per Token (Wh)"}
    ), row=2, col=3)

    fig.update_layout(
        title_text="Overview: Prompts & Energy",
        height=500,
        showlegend=False
    )
    return fig

def energy_usage_timeline(df, start_time=None, end_time=None):
    """
    Line chart of total energy usage per prompt, filtered by timeframe if specified.
    """
    start_time = None  # Replace with desired start time, e.g., pd.Timestamp('2023-01-01')
    end_time = None    # Replace with desired end time, e.g., pd.Timestamp('2023-12-31')

    df_filtered = df.copy()
    if start_time and end_time:
        df_filtered = df_filtered[(df_filtered['timestamp'] >= start_time) & (df_filtered['timestamp'] <= end_time)]

    fig = go.Figure()
    fig.add_trace(go.Scatter(
        x=df_filtered.index,
        y=df_filtered['energy_wh'],
        mode='lines+markers',
        name='Energy Usage (Wh)'
    ))
    fig.update_layout(
        title='Total Energy Usage per Prompt (Filtered by Time)',
        xaxis_title='Prompt Index',
        yaxis_title='Energy (Wh)'
    )
    return fig

def cpu_gpu_usage_per_prompt(df):
    """
    Bar chart comparing CPU vs GPU power usage for each prompt.
    """
    fig = go.Figure(data=[
        go.Bar(name='CPU Power (W)', x=df.index, y=df['cpu_power_w']),
        go.Bar(name='GPU Power (W)', x=df.index, y=df['gpu_power_w'])
    ])
    fig.update_layout(
        barmode='group',
        title='CPU vs GPU Power Usage per Prompt',
        xaxis_title='Prompt Index',
        yaxis_title='Power (W)'
    )
    return fig

def estimated_vs_actual_power(df):
    """
    Histogram comparing estimated and actual energy usage per prompt.
    """
    df_plot = df.copy()
    df_plot['estimated_power'] = df_plot['energy_estimate_tokens']
    df_plot['actual_power'] = df_plot['energy_wh']

    fig = go.Figure(data=[
        go.Bar(name='Estimated Energy (Wh)', x=df_plot.index, y=df_plot['estimated_power']),
        go.Bar(name='Actual Energy (Wh)', x=df_plot.index, y=df_plot['actual_power'])
    ])
    fig.update_layout(
        barmode='group',
        title='Estimated vs Actual Energy Usage per Prompt',
        xaxis_title='Prompt Index',
        yaxis_title='Energy (Wh)'
    )
    return fig

def baseline_vs_total_usage(df):
    """
    Line graph of baseline vs total energy usage per prompt.
    """
    fig = go.Figure()
    fig.add_trace(go.Scatter(
        name='Baseline Energy (Wh)',
        x=df.index,
        y=df['baseline_energy_wh'],
        mode='lines+markers'
    ))
    fig.add_trace(go.Scatter(
        name='Total Energy (Wh)',
        x=df.index,
        y=df['energy_wh'],
        mode='lines+markers'
    ))
    fig.update_layout(
        title='Baseline vs Total Energy Usage per Prompt',
        xaxis_title='Prompt Index',
        yaxis_title='Energy (Wh)'
    )
    return fig

def model_comparison(df):
    """
    Bar chart comparing average energy usage across different models.
    """
    avg_energy = df.groupby('model')['energy_wh'].mean().reset_index()
    fig = px.bar(
        avg_energy,
        x='model',
        y='energy_wh',
        title='Average Energy Usage by Model',
        labels={'model': 'Model', 'energy_wh': 'Average Energy (Wh)'}
    )
    return fig
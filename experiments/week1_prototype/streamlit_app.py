"""Streamlit dashboard rendering Canonical V3.1 with Plotly."""

from __future__ import annotations

import os
from pathlib import Path

import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st
from plotly.subplots import make_subplots

from data_access import (
    CANONICAL_ENV,
    CanonicalDataError,
    load_asset_master,
    load_cnc_sensor_observation,
    load_compressor_sensor_observation,
    load_failure_truth,
    load_prediction_factors,
    load_prediction_snapshot,
    load_prediction_timeline,
    resolve_canonical_root,
)


st.set_page_config(
    page_title="Canonical V3.1 Plotly Lab",
    page_icon="📈",
    layout="wide",
)

st.markdown(
    """
    <style>
      .block-container {padding-top: 1.4rem; padding-bottom: 3rem;}
      [data-testid="stMetric"] {
        border: 1px solid rgba(128, 128, 128, 0.22);
        border-radius: 10px;
        padding: 12px 14px;
      }
      .prototype-note {
        border-left: 3px solid #64748b;
        padding: 0.5rem 0.8rem;
        color: #64748b;
      }
    </style>
    """,
    unsafe_allow_html=True,
)


@st.cache_data(show_spinner=False)
def cached_asset_master(root: str) -> pd.DataFrame:
    return load_asset_master(Path(root))


@st.cache_data(show_spinner=False)
def cached_snapshot(root: str) -> pd.DataFrame:
    return load_prediction_snapshot(Path(root))


@st.cache_data(show_spinner=False)
def cached_failure_truth(root: str) -> pd.DataFrame:
    return load_failure_truth(Path(root))


@st.cache_data(show_spinner=False)
def cached_timeline(root: str, asset_id: str) -> pd.DataFrame:
    return load_prediction_timeline(Path(root), asset_id)


@st.cache_data(show_spinner=False)
def cached_cnc_sensor(root: str, asset_id: str) -> pd.DataFrame:
    return load_cnc_sensor_observation(Path(root), asset_id)


@st.cache_data(show_spinner=False)
def cached_compressor_sensor(root: str, asset_id: str) -> pd.DataFrame:
    return load_compressor_sensor_observation(Path(root), asset_id)


@st.cache_data(show_spinner=False)
def cached_factors(root: str, prediction_id: str) -> pd.DataFrame:
    return load_prediction_factors(Path(root), prediction_id)


def _resolve_root_from_ui() -> Path:
    configured = os.getenv(CANONICAL_ENV, "")
    with st.sidebar:
        st.header("Data source")
        entered = st.text_input(
            "Canonical V3.1 root",
            value=configured,
            placeholder="/path/to/predictive_maintenance_canonical_v3.1",
        )
    return resolve_canonical_root(entered or None)


def _risk_rank_chart(snapshot: pd.DataFrame) -> go.Figure:
    latest = snapshot.nlargest(15, "failure_probability").sort_values(
        "failure_probability"
    )
    figure = px.bar(
        latest,
        x="failure_probability",
        y="asset_id",
        color="status",
        orientation="h",
        hover_data=["asset_type", "confidence", "predicted_failure_type"],
        labels={
            "failure_probability": "Failure probability",
            "asset_id": "Asset",
            "status": "Status",
        },
        title="Latest asset risk ranking",
    )
    figure.update_xaxes(tickformat=".0%", range=[0, 1])
    figure.update_layout(height=500, legend_title_text="Status")
    return figure


def _risk_timeline_chart(timeline: pd.DataFrame, asset_id: str) -> go.Figure:
    figure = px.line(
        timeline,
        x="observed_at",
        y="failure_probability",
        color="status",
        markers=False,
        labels={
            "observed_at": "Observed at",
            "failure_probability": "Failure probability",
            "status": "Status",
        },
        title=f"Failure probability replay · {asset_id}",
    )
    figure.add_hline(y=0.5, line_dash="dash", annotation_text="Review threshold")
    figure.update_yaxes(tickformat=".0%", range=[0, 1])
    figure.update_layout(height=420)
    return figure


def _status_donut(snapshot: pd.DataFrame) -> go.Figure:
    counts = snapshot["status"].fillna("unknown").value_counts().reset_index()
    counts.columns = ["status", "count"]
    figure = px.pie(
        counts,
        names="status",
        values="count",
        hole=0.58,
        title="Latest status composition",
    )
    figure.update_traces(textposition="inside", textinfo="percent+label")
    figure.update_layout(height=390, showlegend=False)
    return figure


def _failure_mode_chart(failure_truth: pd.DataFrame) -> go.Figure:
    counts = (
        failure_truth.groupby(["failure_mode"], dropna=False)
        .size()
        .reset_index(name="event_count")
        .sort_values("event_count", ascending=True)
    )
    figure = px.bar(
        counts,
        x="event_count",
        y="failure_mode",
        orientation="h",
        labels={"event_count": "Events", "failure_mode": "Failure mode"},
        title="Ground-truth failure mode distribution",
    )
    figure.update_layout(height=390)
    return figure


def _cnc_scatter(sensor: pd.DataFrame, asset_id: str) -> go.Figure:
    figure = px.scatter(
        sensor,
        x="rotational_speed_rpm",
        y="torque_nm",
        color="product_type",
        size="tool_wear_min",
        size_max=16,
        opacity=0.62,
        hover_data=["observed_at", "air_temperature_k", "process_temperature_k"],
        labels={
            "rotational_speed_rpm": "Rotational speed (RPM)",
            "torque_nm": "Torque (Nm)",
            "product_type": "Product type",
            "tool_wear_min": "Tool wear (min)",
        },
        title=f"AI4I-style RPM–torque relationship · {asset_id}",
    )
    figure.update_layout(height=500)
    return figure


def _cnc_temperature_chart(sensor: pd.DataFrame, asset_id: str) -> go.Figure:
    melted = sensor.melt(
        id_vars=["observed_at"],
        value_vars=["air_temperature_k", "process_temperature_k"],
        var_name="temperature_type",
        value_name="temperature_k",
    )
    figure = px.line(
        melted,
        x="observed_at",
        y="temperature_k",
        color="temperature_type",
        labels={
            "observed_at": "Observed at",
            "temperature_k": "Temperature (K)",
            "temperature_type": "Signal",
        },
        title=f"Air and process temperature trend · {asset_id}",
    )
    figure.update_layout(height=420, legend_title_text="Signal")
    return figure


def _compressor_dual_axis(sensor: pd.DataFrame, asset_id: str) -> go.Figure:
    figure = make_subplots(specs=[[{"secondary_y": True}]])
    figure.add_trace(
        go.Scatter(
            x=sensor["observed_at"],
            y=sensor["pressure_raw"],
            name="Pressure",
            mode="lines",
        ),
        secondary_y=False,
    )
    figure.add_trace(
        go.Scatter(
            x=sensor["observed_at"],
            y=sensor["vibration_raw"],
            name="Vibration",
            mode="lines",
        ),
        secondary_y=True,
    )
    figure.update_layout(
        title=f"Compressor pressure and vibration · {asset_id}",
        height=450,
        hovermode="x unified",
    )
    figure.update_xaxes(title_text="Observed at")
    figure.update_yaxes(title_text="Pressure", secondary_y=False)
    figure.update_yaxes(title_text="Vibration", secondary_y=True)
    return figure


def _factor_chart(factors: pd.DataFrame, asset_id: str) -> go.Figure:
    ordered = factors.sort_values("signed_contribution")
    figure = px.bar(
        ordered,
        x="signed_contribution",
        y="feature",
        color="direction",
        orientation="h",
        hover_data=["rank", "feature_value", "absolute_contribution"],
        labels={
            "signed_contribution": "Signed contribution",
            "feature": "Feature",
            "direction": "Direction",
        },
        title=f"Top model factors · {asset_id}",
    )
    figure.add_vline(x=0, line_width=1)
    figure.update_layout(height=360)
    return figure


def main() -> None:
    st.title("Canonical V3.1 · Streamlit + Plotly Lab")
    st.markdown(
        '<div class="prototype-note">Azure PdM 계열 압축기와 AI4I 계열 CNC를 '
        "하나의 읽기 전용 분석 화면에서 비교하는 Week 1 프로토타입입니다.</div>",
        unsafe_allow_html=True,
    )

    try:
        root = _resolve_root_from_ui()
    except CanonicalDataError as exc:
        st.error(str(exc))
        st.stop()

    root_value = str(root)
    with st.spinner("Loading Canonical V3.1 contracts…"):
        assets = cached_asset_master(root_value)
        snapshot = cached_snapshot(root_value)
        failure_truth = cached_failure_truth(root_value)

    asset_types = sorted(assets["asset_type"].dropna().unique().tolist())
    with st.sidebar:
        selected_type = st.selectbox("Asset type", asset_types)
        type_assets = assets.loc[assets["asset_type"] == selected_type, "asset_id"]
        selected_asset = st.selectbox("Asset", sorted(type_assets.tolist()))
        st.caption(f"Dataset root: `{root}`")

    selected_snapshot = snapshot.loc[snapshot["asset_id"] == selected_asset]
    latest = selected_snapshot.sort_values("observed_at").tail(1)
    latest_row = latest.iloc[0] if not latest.empty else None

    metric_columns = st.columns(5)
    metric_columns[0].metric("Assets", f"{len(assets):,}")
    metric_columns[1].metric("Prediction snapshots", f"{len(snapshot):,}")
    metric_columns[2].metric("Failure truth events", f"{len(failure_truth):,}")
    metric_columns[3].metric(
        "Selected risk",
        f"{latest_row['failure_probability']:.1%}" if latest_row is not None else "—",
    )
    metric_columns[4].metric(
        "Confidence",
        f"{latest_row['confidence']:.1%}" if latest_row is not None else "—",
    )

    overview_tab, sensor_tab, explain_tab, data_tab = st.tabs(
        ["Overview", "Sensor & physics", "Explainability", "Data contract"]
    )

    with overview_tab:
        left, right = st.columns([1.65, 1])
        with left:
            st.plotly_chart(
                _risk_rank_chart(snapshot),
                width="stretch",
                key="risk-rank",
            )
        with right:
            st.plotly_chart(
                _status_donut(snapshot),
                width="stretch",
                key="status-donut",
            )

        timeline = cached_timeline(root_value, selected_asset)
        if timeline.empty:
            st.info("선택 설비의 prediction timeline이 없습니다.")
        else:
            st.plotly_chart(
                _risk_timeline_chart(timeline, selected_asset),
                width="stretch",
                key="risk-timeline",
            )

        st.plotly_chart(
            _failure_mode_chart(failure_truth),
            width="stretch",
            key="failure-mode",
        )

    with sensor_tab:
        if selected_type == "cnc":
            sensor = cached_cnc_sensor(root_value, selected_asset)
            if sensor.empty:
                st.warning("선택 CNC의 센서 관측값이 없습니다.")
            else:
                st.plotly_chart(
                    _cnc_scatter(sensor, selected_asset),
                    width="stretch",
                    key="cnc-scatter",
                )
                st.plotly_chart(
                    _cnc_temperature_chart(sensor, selected_asset),
                    width="stretch",
                    key="cnc-temperature",
                )
                st.dataframe(sensor.tail(200), width="stretch", hide_index=True)
        else:
            sensor = cached_compressor_sensor(root_value, selected_asset)
            if sensor.empty:
                st.warning("선택 압축기의 센서 관측값이 없습니다.")
            else:
                st.plotly_chart(
                    _compressor_dual_axis(sensor, selected_asset),
                    width="stretch",
                    key="compressor-dual-axis",
                )
                scatter = px.scatter(
                    sensor,
                    x="relative_vibration_z",
                    y="pressure_raw",
                    color="vibration_raw",
                    hover_data=["observed_at", "rotation_raw", "voltage_raw"],
                    labels={
                        "relative_vibration_z": "Relative vibration z",
                        "pressure_raw": "Pressure",
                        "vibration_raw": "Vibration",
                    },
                    title=f"Relative vibration vs pressure · {selected_asset}",
                )
                scatter.update_layout(height=450)
                st.plotly_chart(
                    scatter,
                    width="stretch",
                    key="compressor-scatter",
                )
                st.dataframe(sensor.tail(200), width="stretch", hide_index=True)

    with explain_tab:
        if latest_row is None:
            st.info("선택 설비의 prediction snapshot이 없습니다.")
        else:
            factors = cached_factors(root_value, latest_row["prediction_id"])
            if factors.empty:
                st.info("선택 예측의 factor artifact가 없습니다.")
            else:
                st.plotly_chart(
                    _factor_chart(factors, selected_asset),
                    width="stretch",
                    key="factor-chart",
                )
                st.dataframe(factors, width="stretch", hide_index=True)

    with data_tab:
        st.subheader("Selected prediction snapshot")
        st.dataframe(selected_snapshot, width="stretch", hide_index=True)
        st.subheader("Asset master")
        st.dataframe(assets, width="stretch", hide_index=True)
        st.caption(
            "모든 데이터는 Canonical V3.1 패키지에서 읽기 전용으로 로드되며 "
            "원본 파일을 변경하지 않습니다."
        )


if __name__ == "__main__":
    main()


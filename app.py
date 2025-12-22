import streamlit as st
import requests
import pandas as pd
import matplotlib.pyplot as plt
import matplotlib.font_manager as fm
import urllib.request
import os
import io
import base64
import numpy as np
from datetime import datetime, timedelta, timezone
import matplotlib.dates as mdates
from streamlit_folium import st_folium
import folium

# ======================================================================================
# 1. 定数・基本設定
# ======================================================================================
CONFIG = {
    "TITLE_SIZE": 22,
    "SUBTITLE_SIZE": 16,
    "GRAPH_FONT_SIZE": 13,
    "LABEL_SIZE": 12,
    "DPI": 300,
    "MAP_HEIGHT": 350
}

ALL_DIRECTIONS = ["北", "北北東", "北東", "東北東", "東", "東南東", "南東", "南南東", "南", "南南西", "南西", "西南西", "西", "西北西", "北西", "北北西"]

# ======================================================================================
# 2. 補助サブルーチン
# ======================================================================================
def setup_font():
    font_url = "https://github.com/google/fonts/raw/main/ofl/notosansjp/NotoSansJP%5Bwght%5D.ttf"
    font_path = "NotoSansJP.ttf"
    if not os.path.exists(font_path):
        urllib.request.urlretrieve(font_url, font_path)
    fm.fontManager.addfont(font_path)
    plt.rc('font', family='Noto Sans JP', size=CONFIG["GRAPH_FONT_SIZE"])

def fetch_weather_data(lat, lon, days):
    url = f"https://api.open-meteo.com/v1/forecast?latitude={lat}&longitude={lon}&hourly=temperature_2m,wind_speed_10m,wind_direction_10m,weather_code&timezone=Asia%2FTokyo&wind_speed_unit=ms&forecast_days={days}"
    try:
        data = requests.get(url).json()
        df = pd.DataFrame(data["hourly"])
        df['time'] = pd.to_datetime(df['time'])
        return df
    except: return None

def get_tide_level(times):
    base_full_tide = datetime(2025, 1, 1, 6, 0)
    cycle_hours = 12.42
    levels = []
    for t in times:
        hours_from_base = (t - base_full_tide).total_seconds() / 3600
        level = 100 * np.cos(2 * np.pi * hours_from_base / cycle_hours)
        levels.append(level)
    return levels

def get_weather_info(code):
    if code is None: return "", "black"
    if code <= 2: return "晴", "#FF4500" # 濃いオレンジ
    if code <= 48: return "曇", "#696969"
    if code <= 99: return "雨", "#00008B" # 濃い青
    return "？", "black"

def process_wind_data(df, target_dirs, danger_v):
    dirs = ALL_DIRECTIONS + ["北"]
    arrows = ["↓", "↙", "↙", "↙", "←", "↖", "↖", "↖", "↑", "↗", "↗", "↗", "→", "↘", "↘", "↘", "↓"]
    def get_info(deg):
        idx = int((deg + 11.25) / 22.5) % 16
        return dirs[idx], arrows[idx]
    df['res'] = df['wind_direction_10m'].apply(get_info)
    df['dir_name'] = df['res'].apply(lambda x: x[0])
    df['arrow'] = df['res'].apply(lambda x: x[1])
    weather_res = df['weather_code'].apply(get_weather_info)
    df['w_text'] = [r[0] for r in weather_res]
    df['w_color'] = [r[1] for r in weather_res]
    def judge(row):
        speed = row['wind_speed_10m']
        if speed >= danger_v: return "crimson"
        if row['dir_name'] in target_dirs:
            if 6 <= speed < danger_v: return "orange"
            if 3 <= speed < 6: return "skyblue"
        return "#D3D3D3"
    df['color'] = df.apply(judge, axis=1)
    df['tide_level'] = get_tide_level(df['time'])
    return df

# ======================================================================================
# 3. グラフ生成
# ======================================================================================
@st.cache_data(show_spinner=False)
def get_cached_graph(lat, lon, days, danger_v, selected_dirs_tuple):
    df = fetch_weather_data(lat, lon, days)
    if df is None: return None
    df = process_wind_data(df, list(selected_dirs_tuple), danger_v)
    wind_step = (1 if days <= 1 else (2 if days <= 3 else 3))
    time_step = (3 if days <= 2 else 6)
    fig_w = max(10, days * 4.5)
    fig, (ax1, ax2, ax3) = plt.subplots(3, 1, figsize=(fig_w, 10), dpi=CONFIG["DPI"], gridspec_kw={'height_ratios': [4.2, 1.2, 1.0]})
    plt.subplots_adjust(hspace=0.6)
    jp_weeks = ["月", "火", "水", "木", "金", "土", "日"]
    def formatter(x, p):
        dt = mdates.num2date(x)
        if dt.hour == 0: return dt.strftime('%m/%d') + f'\n({jp_weeks[dt.weekday()]})\n' + dt.strftime('%H:%M')
        else: return dt.strftime('%H:%M')
    bars = ax1.bar(df['time'], df['wind_speed_10m'], color=df['color'], alpha=0.9, width=0.03)
    ax1.axhline(y=danger_v, color='red', linestyle='--', alpha=0.6)
    ax1.set_ylabel('風速 (m/s)')
    max_val = df['wind_speed_10m'].max(); y_limit = max(max_val, danger_v) + 5
    ax1.set_ylim(0, y_limit)
    text_offset_weather = y_limit * 0.20 
    text_offset_wind = y_limit * 0.02
    jst = timezone(timedelta(hours=9))
    now_jst = datetime.now(jst).replace(tzinfo=None)
    for ax in [ax1, ax2, ax3]:
        ax.axvline(now_jst, color='blue', linestyle='-', alpha=0.6, linewidth=2.5)
        ax.xaxis.set_major_locator(mdates.HourLocator(byhour=range(0, 24, time_step)))
        ax.xaxis.set_major_formatter(plt.FuncFormatter(formatter))
        ax.set_xlim(df['time'].iloc[0], df['time'].iloc[-1])
        ax.grid(True, linestyle=':', alpha=0.4, color='#000000')
    ax2.plot(df['time'], df['temperature_2m'], color='black', linewidth=1.5)
    ax2.set_ylabel('気温(℃)')
    ax3.plot(df['time'], df['tide_level'], color='royalblue', linewidth=2)
    ax3.fill_between(df['time'], df['tide_level'], -120, color='royalblue', alpha=0.2)
    ax3.set_ylabel('潮位'); ax3.set_yticks([])
    for i, bar in enumerate(bars):
        if i % wind_step == 0:
            h = bar.get_height()
            ax1.text(bar.get_x() + bar.get_width()/2., h + text_offset_weather, df['w_text'].iloc[i], ha='center', va='bottom', color=df['w_color'].iloc[i], fontweight='bold', fontsize=CONFIG["GRAPH_FONT_SIZE"])
            txt = f"{df['dir_name'].iloc[i]}\n{df['arrow'].iloc[i]}\n{round(df['wind_speed_10m'].iloc[i])}m"
            ax1.text(bar.get_x() + bar.get_width()/2., h + text_offset_wind, txt, ha='center', va='bottom', fontweight='bold', color='black', fontsize=CONFIG["GRAPH_FONT_SIZE"])
    buf = io.BytesIO(); fig.savefig(buf, format="png", bbox_inches='tight', pad_inches=0.1)
    return base64.b64encode(buf.getvalue()).decode()

# ======================================================================================
# 4. 地図UI（3x3マトリックス）
# ======================================================================================
def show_location_map():
    st.info("地図の中央地点を確定できます。")
    st.markdown("""<style>
        div[data-testid="stHorizontalBlock"] { flex-wrap: nowrap !important; justify-content: center !important; }
        [data-testid="column"] { min-width: 0px !important; }
        .guide-arrow-main { color: crimson; font-size: 24px; font-weight: bold; text-align: center; }
        div[data-testid="stButton"] button { background-color: #007bff; color: white; border-radius: 5px; height: 3em; }
        div[data-testid="stButton"] button:hover { background-color: #0056b3; }
        </style>""", unsafe_allow_html=True)

    m = folium.Map(location=[st.session_state.lat, st.session_state.lon], zoom_start=13)
    folium.Marker([st.session_state.lat, st.session_state.lon], icon=folium.Icon(color='red')).add_to(m)

    col_l1, col_m1, col_r1 = st.columns([1, 18, 1])
    with col_m1: st.markdown("<div class='guide-arrow-main'>▼</div>", unsafe_allow_html=True)
    col_l2, col_m2, col_r2 = st.columns([1, 18, 1])
    with col_l2: st.markdown(f"<div style='line-height:{CONFIG['MAP_HEIGHT']}px; text-align:right;' class='guide-arrow-main'>▶</div>", unsafe_allow_html=True)
    with col_m2: map_out = st_folium(m, width=None, height=CONFIG["MAP_HEIGHT"], key=f"map_{st.session_state.lat}", returned_objects=["center"])
    with col_r2: st.markdown(f"<div style='line-height:{CONFIG['MAP_HEIGHT']}px; text-align:left;' class='guide-arrow-main'>◀</div>", unsafe_allow_html=True)
    col_l3, col_m3, col_r3 = st.columns([1, 18, 1])
    with col_m3: st.markdown("<div class='guide-arrow-main'>▲</div>", unsafe_allow_html=True)

    if map_out and map_out.get("center"):
        if st.button("グラフ描画地点（地図中央）確定", use_container_width=True):
            st.session_state.lat, st.session_state.lon = map_out["center"]["lat"], map_out["center"]["lng"]
            st.session_state.last_basho = "地図で指定"
            # URLを即時更新してリロード
            st.query_params.update({"lat": st.session_state.lat, "lon": st.session_state.lon, "basho": "地図で指定"})
            st.rerun()

# ======================================================================================
# 5. メインアプリ
# ======================================================================================
def main():
    setup_font()
    st.markdown(f'<h1 style="font-size:{CONFIG["TITLE_SIZE"]}px; margin-bottom: 5px;">⛵ 高須風チェッカー</h1>', unsafe_allow_html=True)
    
    coords_m = {
        "高須沖(鹿児島県)":(31.337, 130.795), "柏原沖(鹿児島県)":(31.380, 131.020), "垂水港(鹿児島県)":(31.478, 130.668),
        "海潟(鹿児島県)":(31.539, 130.706), "磯海岸沖(鹿児島県)":(31.614, 130.577), "江口浜沖(鹿児島県)":(31.643, 130.322),
        "錦江湾(鹿児島県)":(31.590, 130.600), "地図で指定": (None, None)
    }

    # 起動時の初期化ロジック
    p = st.query_params
    if 'lat' not in st.session_state:
        st.session_state.lat = float(p.get("lat", 31.337))
        st.session_state.lon = float(p.get("lon", 130.795))
        st.session_state.last_basho = p.get("basho", "高須沖(鹿児島県)")

    # UI表示
    basho = st.selectbox("地点を選択", list(coords_m.keys()), index=list(coords_m.keys()).index(st.session_state.last_basho) if st.session_state.last_basho in coords_m else 0)
    show_map = st.checkbox("地図表示", value=st.session_state.get('show_map_state', False))
    st.session_state.show_map_state = show_map

    st.markdown(f"<p style='font-size:14px; color:#1e88e5; font-weight:bold; margin-top:-10px;'>📍 現在：{st.session_state.last_basho} ({st.session_state.lat:.4f}, {st.session_state.lon:.4f})</p>", unsafe_allow_html=True)

    # 地点変更の検知
    if st.session_state.last_basho != basho:
        if basho != "地図で指定":
            st.session_state.lat, st.session_state.lon = coords_m[basho]
        st.session_state.last_basho = basho
        # ここでURLを書き換えて強制リロード
        st.query_params.update({"lat": st.session_state.lat, "lon": st.session_state.lon, "basho": basho})
        st.rerun()

    if show_map: show_location_map()
    
    # サイドバー
    st.sidebar.header("表示設定")
    days = st.sidebar.slider("表示日数", 1, 8, int(p.get("days", 8)))
    danger_v = st.sidebar.number_input("危険風速(m/s)", value=float(p.get("danger", 10.0)))
    init_dirs = p.get("dirs", "南,南南西,南西,西南西,西,西北西,北西,北北西").split(",")
    sel_dirs = []
    cols = st.sidebar.columns(2)
    for i, d in enumerate(ALL_DIRECTIONS):
        with cols[i % 2]:
            if st.checkbox(d, value=(d in init_dirs), key=f"chk_{d}"): sel_dirs.append(d)

    # グラフ描画
    img = get_cached_graph(st.session_state.lat, st.session_state.lon, days, danger_v, tuple(sel_dirs))
    if img:
        st.markdown(f'<div style="overflow-x: auto; background: white;"><img src="data:image/png;base64,{img}" style="height: 900px; max-width: none;"></div>', unsafe_allow_html=True)

if __name__ == "__main__":
    main()

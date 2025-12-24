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
# 1. 定数・基本設定 (CONFIG)
# ======================================================================================
CONFIG = {
    "TITLE_SIZE": 22,
    "SUBTITLE_SIZE": 16,
    "GRAPH_FONT_SIZE": 12,
    "LABEL_SIZE": 12,
    "DPI": 300,
    "MAP_HEIGHT": 350,
    # グラフ表示比率 (風速, 気温, 潮位)
    "HEIGHT_RATIOS": [4.4, 1.2, 0.8], 
    # 現在地表示のスタイル
    "LOC_INFO_FONT_SIZE": "14px",
    "LOC_INFO_COLOR": "#1e88e5",
    "LOC_INFO_MARGIN_TOP": "-10px",
    # 初期地点設定
    "DEFAULT_LAT": 31.337,
    "DEFAULT_LON": 130.795,
    "DEFAULT_BASHO": "高須沖(鹿児島県)"
}

ALL_DIRECTIONS = ["北", "北北東", "北東", "東北東", "東", "東南東", "南東", "南南東", "南", "南南西", "南西", "西南西", "西", "西北西", "北西", "北北西"]

#==========================================================================================
# グラフに使用する日本語フォントをセットアップするサブルーチン
#==========================================================================================
def setup_font():
    font_url = "https://github.com/google/fonts/raw/main/ofl/notosansjp/NotoSansJP%5Bwght%5D.ttf"
    font_path = "NotoSansJP.ttf"
    if not os.path.exists(font_path):
        urllib.request.urlretrieve(font_url, font_path)
    fm.fontManager.addfont(font_path)
    plt.rc('font', family='Noto Sans JP', size=CONFIG["GRAPH_FONT_SIZE"])

#==========================================================================================
# Open-Meteo APIから気象データを取得するサブルーチン
#==========================================================================================
def fetch_weather_data(lat, lon, days):
    url = f"https://api.open-meteo.com/v1/forecast?latitude={lat}&longitude={lon}&hourly=temperature_2m,wind_speed_10m,wind_direction_10m,weather_code&timezone=Asia%2FTokyo&wind_speed_unit=ms&forecast_days={days}"
    try:
        data = requests.get(url).json()
        df = pd.DataFrame(data["hourly"])
        df['time'] = pd.to_datetime(df['time'])
        return df
    except: return None

#==========================================================================================
# 指定された時間リストに基づき簡易的な潮位を計算するサブルーチン
#==========================================================================================
def get_tide_level(times):
    base_full_tide = datetime(2025, 1, 1, 6, 0)
    cycle_hours = 12.42
    levels = []
    for t in times:
        hours_from_base = (t - base_full_tide).total_seconds() / 3600
        level = 100 * np.cos(2 * np.pi * hours_from_base / cycle_hours)
        levels.append(level)
    return levels

#==========================================================================================
# 天気コードを日本語の名称と表示用の色に変換するサブルーチン
#==========================================================================================
def get_weather_info(code):
    if code is None: return "", "black"
    if code <= 2: return "晴", "#FF4500"
    if code <= 48: return "曇", "#696969"
    if code <= 99: return "雨", "#00008B"
    return "？", "black"

#==========================================================================================
# 風向角度を名称と矢印に変換し、条件に基づきグラフの色を判定するサブルーチン
#==========================================================================================
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

#==========================================================================================
# グラフのX軸ラベル（日付と曜日と時刻）をフォーマットするサブルーチン
#==========================================================================================
def get_x_axis_formatter():
    jp_weeks = ["月", "火", "水", "木", "金", "土", "日"]
    def formatter(x, p):
        dt = mdates.num2date(x)
        if dt.hour == 0:
            return dt.strftime('%m/%d') + f'\n({jp_weeks[dt.weekday()]})\n' + dt.strftime('%H:%M')
        else:
            return dt.strftime('%H:%M')
    return formatter

#==========================================================================================
# グラフの特定のバーの位置に天気のテキストを描画するサブルーチン
#==========================================================================================
def draw_weather_text(ax1, bar, row, offset):
    ax1.text(bar.get_x() + bar.get_width()/2., bar.get_height() + offset, 
             row['w_text'], ha='center', va='bottom', 
             color=row['w_color'], fontweight='bold', fontsize=CONFIG["GRAPH_FONT_SIZE"])

#==========================================================================================
# グラフの特定のバーの位置に風の情報テキストを描画するサブルーチン
#==========================================================================================
def draw_wind_info_text(ax1, bar, row, offset):
    txt = f"{row['dir_name']}\n{row['arrow']}\n{round(row['wind_speed_10m'])}m"
    ax1.text(bar.get_x() + bar.get_width()/2., bar.get_height() + offset, 
             txt, ha='center', va='bottom', 
             fontweight='bold', color='black', fontsize=CONFIG["GRAPH_FONT_SIZE"])

#==========================================================================================
# 各バーに対して、気象アノテーションを追加するサブルーチン
#==========================================================================================
def add_graph_annotations(ax1, df, bars, wind_step, text_offset_weather, text_offset_wind):
    for i, bar in enumerate(bars):
        if i % wind_step == 0:
            row = df.iloc[i]
            draw_weather_text(ax1, bar, row, text_offset_weather)
            draw_wind_info_text(ax1, bar, row, text_offset_wind)

#==========================================================================================
# 共通の軸設定を適用するサブルーチン
#==========================================================================================
def apply_common_axis_settings(ax, df, time_step, formatter, now_jst):
    ax.axvline(now_jst, color='blue', linestyle='-', alpha=0.6, linewidth=2.5)
    ax.xaxis.set_major_locator(mdates.HourLocator(byhour=range(0, 24, time_step)))
    ax.xaxis.set_major_formatter(plt.FuncFormatter(formatter))
    ax.set_xlim(df['time'].iloc[0], df['time'].iloc[-1])
    ax.grid(True, linestyle=':', alpha=0.4, color='#000000')

#==========================================================================================
# 風速グラフを描画するサブルーチン
#==========================================================================================
def plot_wind_speed_graph(ax1, df, danger_v, wind_step):
    bars = ax1.bar(df['time'], df['wind_speed_10m'], color=df['color'], alpha=0.9, width=0.03)
    ax1.axhline(y=danger_v, color='red', linestyle='--', alpha=0.6)
    ax1.set_ylabel('風速 (m/s)')
    y_limit = max(df['wind_speed_10m'].max(), danger_v) + 5
    ax1.set_ylim(0, y_limit)
    add_graph_annotations(ax1, df, bars, wind_step, y_limit * 0.20, y_limit * 0.02)

#==========================================================================================
# 気温グラフを描画するサブルーチン
#==========================================================================================
def plot_temperature_graph(ax2, df):
    ax2.plot(df['time'], df['temperature_2m'], color='black', linewidth=1.5)
    ax2.set_ylabel('気温(℃)')

#==========================================================================================
# 潮位グラフを描画するサブルーチン（比率0の場合も枠は生成されるため制御）
#==========================================================================================
def plot_tide_graph(ax3, df):
    if CONFIG["HEIGHT_RATIOS"][2] > 0.1:
        ax3.plot(df['time'], df['tide_level'], color='royalblue', linewidth=2)
        ax3.fill_between(df['time'], df['tide_level'], -120, color='royalblue', alpha=0.2)
        ax3.set_ylabel('潮位')
    ax3.set_yticks([])

#==========================================================================================
# キャッシュを利用して多段構成の気象グラフ画像を生成するサブルーチン
#==========================================================================================
@st.cache_data(show_spinner=False)
def get_cached_graph(lat, lon, days, danger_v, selected_dirs_tuple):
    df = fetch_weather_data(lat, lon, days)
    if df is None: return None
    df = process_wind_data(df, list(selected_dirs_tuple), danger_v)
    
    wind_step = (1 if days <= 1 else (2 if days <= 3 else 3))
    time_step = (3 if days <= 2 else 6)
    fig_w = max(10, days * 4.5)
    
    fig, (ax1, ax2, ax3) = plt.subplots(3, 1, figsize=(fig_w, 10), dpi=CONFIG["DPI"], 
                                       gridspec_kw={'height_ratios': CONFIG["HEIGHT_RATIOS"]})
    plt.subplots_adjust(hspace=0.6)
    
    formatter = get_x_axis_formatter()
    now_jst = datetime.now(timezone(timedelta(hours=9))).replace(tzinfo=None)
    
    plot_wind_speed_graph(ax1, df, danger_v, wind_step)
    plot_temperature_graph(ax2, df)
    plot_tide_graph(ax3, df)
    
    for ax in [ax1, ax2, ax3]:
        apply_common_axis_settings(ax, df, time_step, formatter, now_jst)
    
    buf = io.BytesIO()
    fig.savefig(buf, format="png", bbox_inches='tight', pad_inches=0.1)
    return base64.b64encode(buf.getvalue()).decode()

#==========================================================================================
# 地図を囲む3x3のガイド矢印を描画するサブルーチン
#==========================================================================================
def draw_map_matrix(m):
    col_l1, col_m1, col_r1 = st.columns([1, 18, 1])
    with col_m1: st.markdown("<div class='guide-arrow-main'>▼</div>", unsafe_allow_html=True)
    
    col_l2, col_m2, col_r2 = st.columns([1, 18, 1])
    with col_l2: st.markdown(f"<div style='line-height:{CONFIG['MAP_HEIGHT']}px; text-align:right;' class='guide-arrow-main'>▶</div>", unsafe_allow_html=True)
    with col_m2: 
        map_out = st_folium(m, width=None, height=CONFIG["MAP_HEIGHT"], key=f"map_{st.session_state.lat}", returned_objects=["center"])
    with col_r2: st.markdown(f"<div style='line-height:{CONFIG['MAP_HEIGHT']}px; text-align:left;' class='guide-arrow-main'>◀</div>", unsafe_allow_html=True)
    
    col_l3, col_m3, col_r3 = st.columns([1, 18, 1])
    with col_m3: st.markdown("<div class='guide-arrow-main'>▲</div>", unsafe_allow_html=True)
    return map_out

#==========================================================================================
# 地図UI全体を表示するサブルーチン
#==========================================================================================
def show_location_map():
    st.info("地図の中央地点のグラフを描画表示することができます。")
    st.markdown("""<style>
        div[data-testid="stHorizontalBlock"] { flex-wrap: nowrap !important; justify-content: center !important; }
        [data-testid="column"] { min-width: 0px !important; }
        .guide-arrow-main { color: crimson; font-size: 24px; font-weight: bold; text-align: center; }
        div[data-testid="stButton"] button { background-color: #007bff; color: white; border-radius: 5px; height: 3em; }
        div[data-testid="stButton"] button:hover { background-color: #0056b3; }
        </style>""", unsafe_allow_html=True)

    m = folium.Map(location=[st.session_state.lat, st.session_state.lon], zoom_start=13)
    folium.Marker([st.session_state.lat, st.session_state.lon], icon=folium.Icon(color='red')).add_to(m)

    map_out = draw_map_matrix(m)

    if map_out and map_out.get("center"):
        if st.button("グラフ描画地点（地図中央）確定", use_container_width=True):
            st.session_state.lat, st.session_state.lon = map_out["center"]["lat"], map_out["center"]["lng"]
            st.session_state.last_basho = "地図で指定"
            st.query_params.update({"lat": st.session_state.lat, "lon": st.session_state.lon, "basho": "地図で指定"})
            st.rerun()

#==========================================================================================
# アプリケーションで利用可能な地点マスタを定義するサブルーチン
#==========================================================================================
def get_location_master():
    return {
        "高須沖(鹿児島県)":(31.337, 130.795), "柏原沖(鹿児島県)":(31.380, 131.020), 
        "垂水港(鹿児島県)":(31.478, 130.668), "海潟(鹿児島県)":(31.539, 130.706), 
        "磯海岸沖(鹿児島県)":(31.614, 130.577), "江口浜沖(鹿児島県)":(31.643, 130.322),
        "錦江湾(鹿児島県)":(31.590, 130.600), "地図で指定": (None, None)
    }

#==========================================================================================
# 地点選択UI（セレクトボックスと地図チェック）を描画するサブルーチン
#==========================================================================================
def show_location_selector(coords_master):
    try:
        current_idx = list(coords_master.keys()).index(st.session_state.last_basho)
    except ValueError:
        current_idx = 0
    
    basho = st.selectbox("地点を選択してください", list(coords_master.keys()), index=current_idx)
    show_map = st.checkbox("地図表示", value=st.session_state.get('show_map_state', False))
    st.session_state.show_map_state = show_map
    return basho, show_map

#==========================================================================================
# 現在選択されている地点情報を表示するサブルーチン
#==========================================================================================
def display_current_location_info():
    style = f"font-size:{CONFIG['LOC_INFO_FONT_SIZE']}; color:{CONFIG['LOC_INFO_COLOR']}; font-weight:bold; margin-top:{CONFIG['LOC_INFO_MARGIN_TOP']};"
    text = f"📍 現在：{st.session_state.last_basho} ({st.session_state.lat:.4f}, {st.session_state.lon:.4f})"
    st.markdown(f"<p style='{style}'>{text}</p>", unsafe_allow_html=True)

#==========================================================================================
# アプリ起動時にURLパラメータから初期設定を復元するサブルーチン
#==========================================================================================
def initialize_session_from_url(p):
    if 'initialized' not in st.session_state:
        st.session_state.lat = float(p.get("lat", CONFIG["DEFAULT_LAT"]))
        st.session_state.lon = float(p.get("lon", CONFIG["DEFAULT_LON"]))
        st.session_state.last_basho = p.get("basho", CONFIG["DEFAULT_BASHO"])
        st.session_state.initialized = True

#==========================================================================================
# 地点が変更された場合に更新・リロードするサブルーチン
#==========================================================================================
def handle_location_change(basho, coords_master):
    if st.session_state.last_basho != basho:
        if basho in coords_master and basho != "地図で指定":
            st.session_state.lat, st.session_state.lon = coords_master[basho]
        st.session_state.last_basho = basho
        st.query_params.update({"lat": st.session_state.lat, "lon": st.session_state.lon, "basho": basho})
        st.rerun()

#==========================================================================================
# サイドバーの入力コントロールを生成するサブルーチン
#==========================================================================================
def show_sidebar_controls(p):
    st.sidebar.header("表示設定")
    days = st.sidebar.slider("表示日数", 1, 8, int(p.get("days", 8)))
    danger_v = st.sidebar.number_input("危険風速(m/s)", value=float(p.get("danger", 10.0)))
    init_dirs = p.get("dirs", "南,南南西,南西,西南西,西,西北西,北西,北北西").split(",")
    sel_dirs = []
    cols = st.sidebar.columns(2)
    for i, d in enumerate(ALL_DIRECTIONS):
        with cols[i % 2]:
            if st.checkbox(d, value=(d in init_dirs), key=f"chk_{d}"):
                sel_dirs.append(d)
    return days, danger_v, sel_dirs

#==========================================================================================
# グラフ画像と凡例をメイン画面に描画するサブルーチン
#==========================================================================================
def display_graph_section(lat, lon, days, danger_v, sel_dirs):
    img = get_cached_graph(lat, lon, days, danger_v, tuple(sel_dirs))
    if img:
        with st.expander("📊 凡例"):
            st.write(f"■ 3-6m/s ■ 6-10m/s ■ {danger_v}m/s以上")
        st.markdown(f'<div style="overflow-x: auto; background: white;"><img src="data:image/png;base64,{img}" style="height: 900px; max-width: none;"></div>', unsafe_allow_html=True)

#==========================================================================================
# メインのアプリケーション実行フロー
#==========================================================================================
def main():
    setup_font()
    st.markdown(f'<h1 style="font-size:{CONFIG["TITLE_SIZE"]}px; margin-bottom: 5px;">⛵ 高須風チェッカー</h1>', unsafe_allow_html=True)
    
    coords_master = get_location_master()
    p = st.query_params
    initialize_session_from_url(p)

    basho, show_map = show_location_selector(coords_master)
    display_current_location_info()

    handle_location_change(basho, coords_master)

    if show_map:
        show_location_map()
    
    days, danger_v, sel_dirs = show_sidebar_controls(p)

    st.query_params.update({
        "lat": st.session_state.lat, "lon": st.session_state.lon, 
        "days": days, "danger": danger_v, "dirs": ",".join(sel_dirs), "basho": st.session_state.last_basho
    })

    display_graph_section(st.session_state.lat, st.session_state.lon, days, danger_v, sel_dirs)

if __name__ == "__main__":
    main()

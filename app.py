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
    "DPI": 150,  # 描画速度と解像度のバランス調整
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
            if 5 <= speed < danger_v: return "orange"
            if 3 <= speed < 5: return "skyblue"
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
# 共通の軸設定を適用するサブルーチン
#==========================================================================================
def apply_common_axis_settings(ax, df, time_step, formatter, now_jst):
    ax.axvline(now_jst, color='blue', linestyle='-', alpha=0.6, linewidth=2.5)
    ax.xaxis.set_major_locator(mdates.HourLocator(byhour=range(0, 24, time_step)))
    ax.xaxis.set_major_formatter(plt.FuncFormatter(formatter))
    ax.set_xlim(df['time'].iloc[0], df['time'].iloc[-1])
    ax.grid(True, linestyle=':', alpha=0.4, color='#000000')

#==========================================================================================
# 4.2 グラフ描画：風速棒グラフ（着色・アノテーション）
#==========================================================================================
def render_wind_bar_chart(ax, df, danger_v, wind_step):
    """
    風速棒グラフを描画し、上部に天気・風向・風速のアノテーションを垂直に配置する。
    """
    bars = ax.bar(df['time'], df['wind_speed_10m'], color=df['color'], alpha=0.9, width=0.035)
    ax.axhline(y=danger_v, color='crimson', linestyle='--', linewidth=1.5, alpha=0.8)
    max_speed = df['wind_speed_10m'].max()
    y_limit = max(max_speed, danger_v) + 6
    ax.set_ylim(0, y_limit)
    ax.set_ylabel('風速 (m/s)', fontsize=CONFIG["LABEL_SIZE"])

    for i, bar in enumerate(bars):
        if i % wind_step == 0:
            row = df.iloc[i]
            if pd.isna(row['wind_speed_10m']): continue
            base_y = bar.get_height()
            x_pos = bar.get_x() + bar.get_width()/2.
            ax.text(x_pos, base_y + 0.3, f"{row['wind_speed_10m']:.0f}", ha='center', va='bottom', fontsize=9)
            ax.text(x_pos, base_y + 1.5, row['arrow'], ha='center', va='bottom', fontsize=12, fontweight='bold')
            ax.text(x_pos, base_y + 2.8, row['dir_name'], ha='center', va='bottom', fontsize=8)
            ax.text(x_pos, base_y + 4.2, row['w_text'], ha='center', va='bottom', color=row['w_color'], fontweight='bold', fontsize=9)

#==========================================================================================
# 4.2 グラフ描画：気温チャート
#==========================================================================================
def render_temp_line_chart(ax, df):
    """気温の推移を折れ線グラフで描画する"""
    ax.plot(df['time'], df['temperature_2m'], color='#333333', linewidth=2, marker='o', markersize=2, markevery=3)
    ax.set_ylabel('気温 (℃)', fontsize=CONFIG["LABEL_SIZE"])
    if not df['temperature_2m'].dropna().empty:
        ax.set_ylim(df['temperature_2m'].min() - 2, df['temperature_2m'].max() + 2)

#==========================================================================================
# 4.2 グラフ描画：潮位チャート
#==========================================================================================
def render_tide_curve_chart(ax, df):
    """潮位曲線を算出し、塗りつぶし効果付きで描画する"""
    ax.plot(df['time'], df['tide_level'], color='royalblue', linewidth=2.5)
    ax.fill_between(df['time'], df['tide_level'], -110, color='royalblue', alpha=0.15)
    ax.set_ylabel('潮位', fontsize=CONFIG["LABEL_SIZE"])
    ax.set_ylim(-120, 120)
    ax.set_yticks([])

#==========================================================================================
# 4.1 高解像度グラフ生成（統合管理）
#==========================================================================================
@st.cache_data(show_spinner="グラフを生成中...")
def generate_high_res_graph(lat, lon, danger_v, selected_dirs_tuple):
    """8日間の予測データに基づいた3段構成のBase64画像を生成する"""
    days = 8
    df = fetch_weather_data(lat, lon, days)
    if df is None: return None
    
    # パディング処理
    padding_time = [df['time'].iloc[0] - timedelta(hours=i) for i in range(1, 4)][::-1]
    padding_df = pd.DataFrame({'time': padding_time})
    df = pd.concat([padding_df, df], ignore_index=True).fillna(method='bfill')
    df = process_wind_data(df, list(selected_dirs_tuple), danger_v)
    
    wind_step, time_step = 3, 6
    fig_w = 36 
    fig, (ax1, ax2, ax3) = plt.subplots(3, 1, figsize=(fig_w, 10), dpi=CONFIG["DPI"], gridspec_kw={'height_ratios': CONFIG["HEIGHT_RATIOS"]})
    plt.subplots_adjust(hspace=0.5)
    
    formatter = get_x_axis_formatter()
    now_jst = datetime.now(timezone(timedelta(hours=9))).replace(tzinfo=None)
    
    render_wind_bar_chart(ax1, df, danger_v, wind_step)
    render_temp_line_chart(ax2, df)
    render_tide_curve_chart(ax3, df)
    
    for ax in [ax1, ax2, ax3]:
        apply_common_axis_settings(ax, df, time_step, formatter, now_jst)
    
    buf = io.BytesIO()
    fig.savefig(buf, format="png", bbox_inches='tight', pad_inches=0.1)
    plt.close(fig) 
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
        current_idx = list(coords_master.keys()).index(st.session_state.get('last_basho', CONFIG["DEFAULT_BASHO"]))
    except ValueError:
        current_idx = 0
    
    basho = st.selectbox("地点を選択してください", list(coords_master.keys()), index=current_idx)
    
    # 「地図で指定」選択時に自動的にチェックをONにするロジック
    default_show_map = True if basho == "地図で指定" else st.session_state.get('show_map_state', False)
    show_map = st.checkbox("地図表示", value=default_show_map)
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
# アプリ起動時に初期設定を行うサブルーチン
#==========================================================================================
def initialize_session():
    if 'lat' not in st.session_state:
        st.session_state.lat = CONFIG["DEFAULT_LAT"]
    if 'lon' not in st.session_state:
        st.session_state.lon = CONFIG["DEFAULT_LON"]
    if 'last_basho' not in st.session_state:
        st.session_state.last_basho = CONFIG["DEFAULT_BASHO"]

#==========================================================================================
# 地点が変更された場合に更新・リロードするサブルーチン
#==========================================================================================
def handle_location_change(basho, coords_master):
    if st.session_state.last_basho != basho:
        if basho in coords_master and basho != "地図で指定":
            st.session_state.lat, st.session_state.lon = coords_master[basho]
        st.session_state.last_basho = basho
        st.rerun()

#==========================================================================================
# サイドバーの入力コントロールを生成するサブルーチン
#==========================================================================================
def show_sidebar_controls():
    st.sidebar.header("表示設定")
    danger_v = st.sidebar.number_input("危険風速(m/s)", value=10.0, step=0.5)
    
    st.sidebar.write("色付風向（乗れる風向）")
    init_dirs = ["南","南南西","南西","西南西","西","西北西","北西","北北西"]
    sel_dirs = []
    cols = st.sidebar.columns(2)
    for i, d in enumerate(ALL_DIRECTIONS):
        with cols[i % 2]:
            if st.checkbox(d, value=(d in init_dirs), key=f"chk_{d}"):
                sel_dirs.append(d)
    
    st.sidebar.markdown("---")
    st.sidebar.write("※設定はブラウザに保存されます（実装予定）")
    
    return danger_v, sel_dirs

#==========================================================================================
# グラフ画像と凡例をメイン画面に描画するサブルーチン
#==========================================================================================
def display_graph_section(lat, lon, danger_v, sel_dirs):
    img = generate_high_res_graph(lat, lon, danger_v, tuple(sel_dirs))
    if img:
        with st.expander("📊 凡例"):
            st.write(f"■ 3-5m/s(青) ■ 5-10m/s(橙) ■ {danger_v}m/s以上(赤)")
        st.markdown(f'<div style="overflow-x: auto; background: white; border: 1px solid #ddd;"><img src="data:image/png;base64,{img}" style="height: 800px; max-width: none;"></div>', unsafe_allow_html=True)

#==========================================================================================
# メインのアプリケーション実行フロー
#==========================================================================================
def main():
    setup_font()
    st.markdown(f'<h1 style="font-size:{CONFIG["TITLE_SIZE"]}px; margin-bottom: 5px;">⛵ 高須風チェッカー</h1>', unsafe_allow_html=True)
    
    initialize_session()
    coords_master = get_location_master()

    basho, show_map = show_location_selector(coords_master)
    handle_location_change(basho, coords_master)
    display_current_location_info()

    if show_map:
        show_location_map()
    
    danger_v, sel_dirs = show_sidebar_controls()
    display_graph_section(st.session_state.lat, st.session_state.lon, danger_v, sel_dirs)

if __name__ == "__main__":
    main()

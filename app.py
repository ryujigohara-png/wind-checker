# -*- coding: utf-8 -*-
# 最終更新 2025.12.30 03:20
# 状態：20:25時点の原本ロジックを1文字も削らず、ブラウザ保存とコメントを統合。

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
import time
import json
from datetime import datetime, timedelta, timezone
import matplotlib.dates as mdates
from streamlit_folium import st_folium
import folium
import streamlit.components.v1 as components
from streamlit_js_eval import streamlit_js_eval, get_geolocation

# ======================================================================================
# 1. 定数・基本設定 (CONFIG)
# アプリ全体の基準数値、場所マスター、ブラウザ保存用のキーを統合管理します。
# ======================================================================================
CONFIG = {
    "TITLE_SIZE": 24,
    "SUBTITLE_SIZE": 18,
    "GRAPH_FONT_SIZE": 12,
    "GRAPH_WIDTH": 20,
    "GRAPH_HIGHT": 3.0,
    "LABEL_SIZE": 9,
    "LABEL_PAD": 0,
    "ANNOT_SIZE": 10,
    "DPI": 200,
    "MAP_HEIGHT": 350,
    "DEFAULT_RATIOS": [4.4, 1.2, 0.8],
    "SHOW_WIND": True,
    "SHOW_TEMP": True,
    "SHOW_TIDE": False,
    "SHOW_W_TEXT": False,
    "SHOW_DIR_NAME": False,
    "HSPACE": 0.1,
    "DEFAULT_LAT": 31.337,
    "DEFAULT_LON": 130.795,
    "DEFAULT_BASHO": "高須沖(鹿児島県)",
    "DEFAULT_DANGER_V": 10.0,
    "DEFAULT_DIRS": ["南","南南西","南西","西南西","西","西北西","北西","北北西"],
    "ANNOT_Y_STEP": 1.5,
    "ANNOT_BASE_Y": 0.5,
    "STORAGE_KEY": "wind_checker_settings_v2",
    "TEMP_COLOR": "darkorange",
    "ARROW_COLOR": "blue",
    "VLINE_WIDTH": 1.25,
    "HLINE_WIDTH": 1.0,
    "PX_PER_INCH": 200,
    "MIN_CONTAINER_WIDTH": 800,
    "SLIDER_WIDTH": {"min": 15.0, "max": 30.0, "step": 1.0},
    "SLIDER_HEIGHT": {"min": 2.0, "max": 5.0, "step": 0.5},
    "SLIDER_FONT": {"min": 8, "max": 15, "step": 1},
    "LOCATION_MASTER": {
        "高須沖(鹿児島県)": (31.337, 130.795), 
        "柏原沖(鹿児島県)": (31.380, 131.020), 
        "垂水港(鹿児島県)": (31.478, 130.668), 
        "海潟(鹿児島県)": (31.539, 130.706), 
        "磯海岸沖(鹿児島県)": (31.614, 130.577), 
        "江口浜沖(鹿児島県)": (31.643, 130.322),
        "錦江湾(鹿児島県)": (31.590, 130.600)
    }
}

ALL_DIRECTIONS = ["北", "北北東", "北東", "東北東", "東", "東南東", "南東", "南南東", "南", "南南西", "南西", "西南西", "西", "西北西", "北西", "北北西"]

# ======================================================================================
# 2. setup_font
# グラフに使用する日本語フォントをダウンロード・セットアップするサブルーチン。
# ======================================================================================
def setup_font(font_size=None):
    if font_size is None:
        font_size = CONFIG["GRAPH_FONT_SIZE"]
    font_url = "https://github.com/google/fonts/raw/main/ofl/notosansjp/NotoSansJP%5Bwght%5D.ttf"
    font_path = "NotoSansJP.ttf"
    if not os.path.exists(font_path):
        urllib.request.urlretrieve(font_url, font_path)
    fm.fontManager.addfont(font_path)
    plt.rc('font', family='Noto Sans JP', size=font_size)

# ======================================================================================
# 3. fetch_weather_data
# 気象データをAPIから取得し、アイコン用絵文字を付与するサブルーチン。
# ======================================================================================
def fetch_weather_data(lat, lon, days):
    url = f"https://api.open-meteo.com/v1/forecast?latitude={lat}&longitude={lon}&hourly=temperature_2m,wind_speed_10m,wind_direction_10m,weather_code&timezone=Asia%2FTokyo&wind_speed_unit=ms&forecast_days={days}"
    try:
        data = requests.get(url).json()
        df = pd.DataFrame(data["hourly"])
        df['time'] = pd.to_datetime(df['time'])
        def get_icon(code):
            if code <= 2: return "☀️"
            if code <= 48: return "☁️"
            if code <= 99: return "☔"
            return "❓"
        df['weather_icon'] = df['weather_code'].apply(get_icon)
        return df
    except: return None

# ======================================================================================
# 4. get_tide_level
# 12.42時間周期の正弦波で潮位レベルを計算するサブルーチン。
# ======================================================================================
def get_tide_level(times):
    base_full_tide = datetime(2025, 1, 1, 6, 0)
    cycle_hours = 12.42
    levels = []
    for t in times:
        if pd.isna(t):
            levels.append(np.nan); continue
        hours_from_base = (t - base_full_tide).total_seconds() / 3600
        level = 100 * np.cos(2 * np.pi * hours_from_base / cycle_hours)
        levels.append(level)
    return levels

# ======================================================================================
# 5. get_weather_info
# 天気コードからグラフ表示用のテキストと色を取得するサブルーチン。
# ======================================================================================
def get_weather_info(code):
    if pd.isna(code): return "", "black"
    if code <= 2: return "晴", "#FF4500"
    if code <= 48: return "曇", "#696969"
    if code <= 99: return "雨", "#00008B"
    return "？", "black"

# ======================================================================================
# 6. process_wind_data
# 風向き・速度の16方位判定、描画色の決定、潮位計算を行うデータ処理サブルーチン。
# ======================================================================================
def process_wind_data(df, target_dirs):
    dirs = ALL_DIRECTIONS + ["北"]
    arrows = ["↓", "↙", "↙", "↙", "←", "↖", "↖", "↖", "↑", "↗", "↗", "↗", "→", "↘", "↘", "↘", "↓"]
    def get_info(deg):
        if pd.isna(deg): return "", ""
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
        if pd.isna(speed): return "#FFFFFF"
        if speed >= 10.0: return "crimson"
        if row['dir_name'] in target_dirs:
            if 5 <= speed < 10.0: return "orange"
            if 3 <= speed < 5: return "skyblue"
        return "#D3D3D3"
    
    df['color'] = df.apply(judge, axis=1)
    df['tide_level'] = get_tide_level(df['time'])
    return df

# ======================================================================================
# 7. get_x_axis_formatter
# X軸の0時に日付と曜日、それ以外に時刻を表示するカスタムフォーマッタ。
# ======================================================================================
def get_x_axis_formatter():
    jp_weeks = ["月", "火", "水", "木", "金", "土", "日"]
    def formatter(x, p):
        dt = mdates.num2date(x)
        if dt.hour == 0:
            return dt.strftime('%m/%d') + f'\n({jp_weeks[dt.weekday()]})'
        else:
            return dt.strftime('%H') + '\n '
    return formatter

# ======================================================================================
# 8. apply_common_axis_settings
# 現在時刻線、グリッド、目盛りサイズなど共通の軸設定を行うサブルーチン。
# ======================================================================================
def apply_common_axis_settings(ax, df, formatter, now_jst, design_params):
    ax.axvline(now_jst, color='blue', linestyle='-', alpha=0.6, linewidth=CONFIG["VLINE_WIDTH"])
    ax.xaxis.set_major_locator(mdates.HourLocator(byhour=range(0, 24, 3)))
    ax.xaxis.set_major_formatter(plt.FuncFormatter(formatter))
    ax.xaxis.set_minor_locator(mdates.HourLocator(interval=1))
    ax.set_xlim(df['time'].iloc[0], df['time'].iloc[-1])
    ax.grid(True, which='major', linestyle=':', alpha=0.6, color='#000000')
    ax.grid(True, which='minor', linestyle=':', alpha=0.2, color='#888888')
    
    l_size = design_params.get("label_font_size", CONFIG["LABEL_SIZE"])
    l_pad = design_params.get("label_pad", CONFIG["LABEL_PAD"])
    ax.tick_params(axis='x', which='major', labelsize=l_size, pad=l_pad)
    ax.tick_params(axis='y', labelsize=l_size)

# ======================================================================================
# 9. render_wind_bar_chart
# 風速棒グラフと、その上に多段配置される文字情報の描画サブルーチン。
# ======================================================================================
def render_wind_bar_chart(ax, df, danger_v, wind_step, design_params=None):
    bar_width = design_params.get("bar_width", 0.035) if design_params else 0.035
    bars = ax.bar(df['time'], df['wind_speed_10m'], color=df['color'], alpha=0.9, width=bar_width)
    ax.axhline(y=danger_v, color='red', linestyle='--', linewidth=CONFIG["HLINE_WIDTH"], alpha=0.8)
    
    fs = design_params.get("base_font_size", CONFIG["GRAPH_FONT_SIZE"]) if design_params else CONFIG["GRAPH_FONT_SIZE"]
    step = fs * 0.12; base = step * 0.5
    show_w = design_params.get("show_w_text", CONFIG["SHOW_W_TEXT"]) if design_params else CONFIG["SHOW_W_TEXT"]
    show_d = design_params.get("show_dir_name", CONFIG["SHOW_DIR_NAME"]) if design_params else CONFIG["SHOW_DIR_NAME"]
    
    max_speed = df['wind_speed_10m'].max()
    element_count = 1 + 1 + (1 if show_d else 0) + (1 if show_w else 0)
    required_top_space = element_count * step + 1.0
    y_limit = max(max_speed + required_top_space, danger_v + 3.0)
    
    ax.set_ylim(0, y_limit)
    ax.set_ylabel('風速 (m/s)', fontsize=CONFIG["LABEL_SIZE"])
    
    for i, bar in enumerate(bars):
        if i % wind_step == 0:
            row = df.iloc[i]
            if pd.isna(row['wind_speed_10m']): continue
            x_pos = bar.get_x() + bar.get_width()/2.
            current_y = bar.get_height() + base
            ax.text(x_pos, current_y, f"{row['wind_speed_10m']:.0f}", ha='center', va='bottom', fontsize=fs-2)
            current_y += step
            ax.text(x_pos, current_y, row['arrow'], ha='center', va='bottom', fontsize=fs+2, fontweight='bold', color=CONFIG["ARROW_COLOR"])
            if show_d:
                current_y += step
                ax.text(x_pos, current_y, row['dir_name'], ha='center', va='bottom', fontsize=fs-2)
            if show_w:
                current_y += step
                ax.text(x_pos, current_y, row['w_text'], ha='center', va='bottom', color=row['w_color'], fontweight='bold', fontsize=fs-1)

# ======================================================================================
# 10. render_temp_line_chart / 11. render_tide_curve_chart
# 気温折れ線および潮位曲線の描画サブルーチン。
# ======================================================================================
def render_temp_line_chart(ax, df):
    ax.plot(df['time'], df['temperature_2m'], color=CONFIG["TEMP_COLOR"], linewidth=2, marker='o', markersize=3, markevery=3)
    ax.set_ylabel('気温 (℃)', fontsize=CONFIG["LABEL_SIZE"])

def render_tide_curve_chart(ax, df):
    ax.plot(df['time'], df['tide_level'], color='royalblue', linewidth=2.5)
    ax.fill_between(df['time'], df['tide_level'], -110, color='royalblue', alpha=0.15)
    ax.set_ylabel('潮位', fontsize=CONFIG["LABEL_SIZE"])
    ax.set_ylim(-120, 120); ax.set_yticks([])

# ======================================================================================
# 12. generate_high_res_graph
# 全グラフを統合し、高解像度のBase64画像と座標情報を生成するサブルーチン。
# ======================================================================================
@st.cache_data(show_spinner="グラフを生成中...", ttl=600)
def generate_high_res_graph(lat, lon, danger_v, selected_dirs_tuple, design_params, now_jst):
    df = fetch_weather_data(lat, lon, 8)
    if df is None: return None, (0, 0)
    padding_df = pd.DataFrame({'time': [df['time'].iloc[0] - timedelta(hours=i) for i in range(1, 4)][::-1]})
    df = pd.concat([padding_df, df], ignore_index=True)
    df = process_wind_data(df, list(selected_dirs_tuple))
    
    active_plots = []
    if design_params.get("show_wind", True): active_plots.append("wind")
    if design_params.get("show_temp", True): active_plots.append("temp")
    if design_params.get("show_tide", True): active_plots.append("tide")
    if not active_plots: return None, (0, 0)
    
    ratios = design_params.get("ratios", CONFIG["DEFAULT_RATIOS"])
    current_ratios = [ratios[["wind","temp","tide"].index(p)] for p in active_plots]
    
    fig_w, fig_h = design_params.get("width", CONFIG["GRAPH_WIDTH"]), design_params.get("height", CONFIG["GRAPH_HIGHT"])
    dpi_value = design_params.get("graph_dpi", CONFIG.get("DPI", 200))
    
    fig, axes = plt.subplots(len(active_plots), 1, figsize=(fig_w, fig_h), dpi=dpi_value, gridspec_kw={'height_ratios': current_ratios})
    if len(active_plots) == 1: axes = [axes]
    plt.subplots_adjust(hspace=design_params.get("hspace", CONFIG["HSPACE"]))
    
    formatter = get_x_axis_formatter()
    for i, p in enumerate(active_plots):
        if p == "wind": render_wind_bar_chart(axes[i], df, danger_v, 3, design_params)
        elif p == "temp": render_temp_line_chart(axes[i], df)
        elif p == "tide": render_tide_curve_chart(axes[i], df)
        apply_common_axis_settings(axes[i], df, formatter, now_jst, design_params)
    
    fig.tight_layout(pad=1.0)
    pos = axes[0].get_position()
    ratio_info = (pos.x0, pos.width / (len(df) - 1))
    buf = io.BytesIO()
    fig.savefig(buf, format="png", bbox_inches=None, pad_inches=0, dpi=dpi_value)
    plt.close(fig)
    return base64.b64encode(buf.getvalue()).decode(), ratio_info

# ======================================================================================
# 13. generate_weather_icons_html
# グラフ画像の上に天気の絵文字を絶対配置するHTMLを生成するサブルーチン。
# ======================================================================================
def generate_weather_icons_html(df, ratio_info, display_width):
    start_x, hour_w = ratio_info
    icon_html = ""
    for i in range(3, len(df), 3):
        row = df.iloc[i]
        pos_left_px = (start_x + (i * hour_w)) * display_width
        icon_html += f'<div style="position: absolute; left: {pos_left_px}px; transform: translateX(-50%); width: 80px; text-align: center; font-size: 32px; z-index: 10;">{row["weather_icon"]}</div>'
    return f'<div style="position: relative; width: {display_width}px; height: 45px; margin-bottom: -15px;">{icon_html}</div>'

# ======================================================================================
# 14. show_location_map / 16. handle_current_location_update
# 地点選択UI（地図・GPS）を管理するサブルーチン。
# ======================================================================================
def show_location_map():
    st.info("地図の中央地点のグラフを描画表示することができます。")
    st.markdown("""<style>
        div[data-testid="stHorizontalBlock"] { flex-wrap: nowrap !important; justify-content: center !important; }
        .guide-arrow-main { color: crimson; font-size: 24px; font-weight: bold; text-align: center; }
        </style>""", unsafe_allow_html=True)
    m = folium.Map(location=[st.session_state.lat, st.session_state.lon], zoom_start=13)
    folium.Marker([st.session_state.lat, st.session_state.lon], icon=folium.Icon(color='red')).add_to(m)
    
    col_m1 = st.columns([1, 18, 1])[1]; col_m1.markdown("<div class='guide-arrow-main'>▼</div>", unsafe_allow_html=True)
    c_l2, c_m2, c_r2 = st.columns([1, 18, 1])
    c_l2.markdown(f"<div style='line-height:{CONFIG['MAP_HEIGHT']}px; text-align:right;' class='guide-arrow-main'>▶</div>", unsafe_allow_html=True)
    with c_m2: map_out = st_folium(m, width=None, height=CONFIG["MAP_HEIGHT"], key=f"map_{st.session_state.lat}_{st.session_state.lon}", returned_objects=["center"])
    c_r2.markdown(f"<div style='line-height:{CONFIG['MAP_HEIGHT']}px; text-align:left;' class='guide-arrow-main'>◀</div>", unsafe_allow_html=True)
    col_m3 = st.columns([1, 18, 1])[1]; col_m3.markdown("<div class='guide-arrow-main' style='margin-top:-10px;'>▲</div>", unsafe_allow_html=True)
    
    if map_out and map_out.get("center"):
        if st.button("グラフ描画地点確定", use_container_width=True):
            st.session_state.lat, st.session_state.lon = map_out["center"]["lat"], map_out["center"]["lng"]
            st.session_state.last_basho = "地図で指定"; st.rerun()

def handle_current_location_update():
    if st.button("🔄 📍現在地を取得", use_container_width=True):
        st.session_state.waiting_loc = True
        st.session_state.geo_key = f"geo_{datetime.now().timestamp()}"; st.rerun()
    if st.session_state.get("waiting_loc"):
        loc = get_geolocation(component_key=st.session_state.get("geo_key"))
        if loc:
            st.session_state.lat, st.session_state.lon = round(loc['coords']['latitude'], 4), round(loc['coords']['longitude'], 4)
            st.session_state.last_basho = "現在地"; st.session_state.waiting_loc = False; st.rerun()

# ======================================================================================
# 15. sync_all_settings / 16_x. save_settings_to_browser
# ブラウザのlocalStorageとの同期を管理するサブルーチン。
# ======================================================================================
def sync_all_settings():
    if st.session_state.get("initialized"): return
    stored = streamlit_js_eval(js_expressions=f"localStorage.getItem('{CONFIG['STORAGE_KEY']}')", key="init_load")
    if stored:
        try:
            d = json.loads(stored)
            for k, v in d.items(): 
                key = "last_basho" if k == "basho" else k
                st.session_state[key] = v
            st.session_state.initialized = True; st.rerun()
        except: st.session_state.initialized = True

def save_settings_to_browser():
    s = st.session_state
    save_data = {
        "lat": s.lat, "lon": s.lon, "basho": s.last_basho, "show_wind": s.show_wind, 
        "show_temp": s.show_temp, "show_tide": s.show_tide, "width": s.width,
        "base_height": s.base_height, "base_font_size": s.base_font_size,
        "label_font_size": s.label_font_size, "danger_v": s.danger_v, "sel_dirs": s.sel_dirs,
        "label_pad": s.get("label_pad", 0), "hspace": s.get("hspace", 0.1), "ratios": s.get("ratios", CONFIG["DEFAULT_RATIOS"])
    }
    components.html(f"<script>localStorage.setItem('{CONFIG['STORAGE_KEY']}', '{json.dumps(save_data)}');</script>", height=0)

# ======================================================================================
# 17. show_sidebar_controls
# サイドバーの設定表示、開発者モード、縦幅自動計算を管理するサブルーチン。
# ======================================================================================
def show_sidebar_controls():
    is_dev = st.query_params.get("mode") == "dev"
    st.sidebar.header("1. 判定・表示設定")
    dv = st.sidebar.number_input("危険風速ライン(m/s)", value=st.session_state.get("danger_v", 10.0), step=0.5)
    st.sidebar.write("色付風向選択")
    saved_dirs = st.session_state.get("sel_dirs", CONFIG["DEFAULT_DIRS"])
    sel_dirs = []; cols = st.sidebar.columns(2)
    for i, d in enumerate(ALL_DIRECTIONS):
        if cols[i%2].checkbox(d, value=(d in saved_dirs), key=f"chk_{d}"): sel_dirs.append(d)
    
    st.sidebar.markdown("---")
    st.sidebar.header("2. グラフ表示切替")
    sw, st_t, sd = st.sidebar.toggle("風向・風速グラフ", value=st.session_state.get("show_wind", True)), st.sidebar.toggle("気温グラフ", value=st.session_state.get("show_temp", True)), st.sidebar.toggle("潮位グラフ", value=st.session_state.get("show_tide", False))
    w = st.sidebar.slider("全体の横幅 (inch)", 10.0, 30.0, float(st.session_state.get("width", 20.0)))
    bh = st.sidebar.slider("基準縦幅 (inch)", 2.0, 10.0, float(st.session_state.get("base_height", 3.0)))
    
    if is_dev:
        st.sidebar.header("3. デザイン調整 (Dev)")
        bfs = st.sidebar.slider("グラフ内文字", 5, 20, st.session_state.get("base_font_size", 12))
        lfs = st.sidebar.slider("軸ラベル文字", 5, 20, st.session_state.get("label_font_size", 9))
        lp = st.sidebar.slider("ラベル距離", -5, 15, st.session_state.get("label_pad", 0))
        hs = st.sidebar.slider("グラフ間余白", -0.1, 0.5, st.session_state.get("hspace", 0.1), step=0.05)
        r = list(st.session_state.get("ratios", CONFIG["DEFAULT_RATIOS"]))
        r[0] = st.sidebar.number_input("比率:風向", 0.5, 10.0, r[0], step=0.1)
        r[1] = st.sidebar.number_input("比率:気温", 0.5, 5.0, r[1], step=0.1)
        r[2] = st.sidebar.number_input("比率:潮位", 0.5, 5.0, r[2], step=0.1)
    else:
        bfs, lfs, lp, hs, r = st.session_state.get("base_font_size", 12), st.session_state.get("label_font_size", 9), st.session_state.get("label_pad", 0), st.session_state.get("hspace", 0.1), st.session_state.get("ratios", CONFIG["DEFAULT_RATIOS"])

    params = {"width": w, "base_height": bh, "base_font_size": bfs, "label_font_size": lfs, "label_pad": lp, "hspace": hs, "show_wind": sw, "show_temp": st_t, "show_tide": sd, "ratios": r, "graph_dpi": 200, "min_container_width": 800}
    unit_h = bh / (r[0] + r[1])
    params["height"] = (0.45 if sw else 0.0) + (r[0]*unit_h if sw else 0) + (r[1]*unit_h if st_t else 0) + (r[2]*unit_h if sd else 0)
    
    st.session_state.update({"danger_v": dv, "sel_dirs": sel_dirs, "show_wind": sw, "show_temp": st_t, "show_tide": sd, "width": w, "base_height": bh, "base_font_size": bfs, "label_font_size": lfs, "label_pad": lp, "hspace": hs, "ratios": r})
    save_settings_to_browser()
    return dv, sel_dirs, params

# ======================================================================================
# 19. main
# アプリケーションのメインエントリーポイント。
# ======================================================================================
def main():
    if 'lat' not in st.session_state: st.session_state.lat = CONFIG["DEFAULT_LAT"]
    if 'lon' not in st.session_state: st.session_state.lon = CONFIG["DEFAULT_LON"]
    if 'last_basho' not in st.session_state: st.session_state.last_basho = CONFIG["DEFAULT_BASHO"]
    
    sync_all_settings()
    dv, sel, params = show_sidebar_controls()
    setup_font(params["base_font_size"])
    
    st.markdown(f'<style>.block-container {{ padding-top: 2rem !important; }}.scroll-container {{ overflow-x: auto; background: white; border: 1px solid #ddd; width: 100%; }}</style>', unsafe_allow_html=True)
    st.markdown(f'<h1 style="font-size:{CONFIG["TITLE_SIZE"]}px;">⛵ Wind_Checker! </h1>', unsafe_allow_html=True)
    
    # 地点選択セクション
    col1, col2 = st.columns([2, 1])
    with col1:
        sel_m = st.selectbox("登録地点から選択", ["地図・GPSから指定"] + list(CONFIG["LOCATION_MASTER"].keys()))
        if sel_m != "地図・GPSから指定":
            st.session_state.lat, st.session_state.lon = CONFIG["LOCATION_MASTER"][sel_m]
            st.session_state.last_basho = sel_m
    with col2: handle_current_location_update()
    if sel_m == "地図・GPSから指定": show_location_map()
    
    st.write(f"現在地： **{st.session_state.last_basho}** (緯度:{st.session_state.lat:.3f}, 経度:{st.session_state.lon:.3f})")
    
    raw_now = datetime.now(timezone(timedelta(hours=9))).replace(tzinfo=None)
    now_jst = raw_now.replace(minute=(raw_now.minute // 10) * 10, second=0, microsecond=0)
    
    img, r_info = generate_high_res_graph(st.session_state.lat, st.session_state.lon, dv, tuple(sel), params, now_jst)
    if img:
        df_for_icons = fetch_weather_data(st.session_state.lat, st.session_state.lon, 8)
        if df_for_icons is not None:
            disp_w = int(params["width"] * params["graph_dpi"])
            pad_df = pd.DataFrame({'time': [df_for_icons['time'].iloc[0] - timedelta(hours=i) for i in range(1, 4)][::-1]})
            df_full = pd.concat([pad_df, df_for_icons], ignore_index=True)
            icons_html = generate_weather_icons_html(df_full, r_info, disp_w)
            st.markdown(f'<div class="scroll-container"><div style="width: {disp_w}px; min-width: 800px;">{icons_html}<img src="data:image/png;base64,{img}" style="width: {disp_w}px; display: block;"></div></div>', unsafe_allow_html=True)

if __name__ == "__main__": main()
    

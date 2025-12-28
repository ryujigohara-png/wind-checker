# -*- coding: utf-8 -*-
#///// 最終更新 2025.12.28 11:30 グラフサイズ最適化・完全機能維持版 //////////////////////////////////////////////////////////////
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
import streamlit.components.v1 as components
import time
import json
from streamlit_js_eval import streamlit_js_eval, get_geolocation

# ======================================================================================
# 1. 定数・基本設定 (CONFIG)
# ======================================================================================
CONFIG = {
    "TITLE_SIZE": 24,
    "SUBTITLE_SIZE": 18,
    "GRAPH_FONT_SIZE": 10,
    "LABEL_SIZE": 9,
    "ANNOT_SIZE": 10,
    "DPI": 200,
    "MAP_HEIGHT": 350,
    "HEIGHT_RATIOS": [4.4, 1.2, 0.8],
    "LOC_INFO_FONT_SIZE": "16px",
    "LOC_INFO_COLOR": "#1e88e5",
    "LOC_INFO_MARGIN_TOP": "-10px",
    "DEFAULT_LAT": 31.337,
    "DEFAULT_LON": 130.795,
    "DEFAULT_BASHO": "高須沖(鹿児島県)",
    "DEFAULT_DANGER_V": 10.0,
    "DEFAULT_DIRS": ["南","南南西","南西","西南西","西","西北西","北西","北北西"],
    "ANNOT_Y_STEP": 1.5,
    "ANNOT_BASE_Y": 0.5,
    "STORAGE_KEY": "wind_checker_settings",
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

#==========================================================================================
# 2. グラフに使用する日本語フォントをセットアップするサブルーチン (既存維持)
#==========================================================================================
def setup_font():
    font_url = "https://github.com/google/fonts/raw/main/ofl/notosansjp/NotoSansJP%5Bwght%5D.ttf"
    font_path = "NotoSansJP.ttf"
    if not os.path.exists(font_path):
        urllib.request.urlretrieve(font_url, font_path)
    fm.fontManager.addfont(font_path)
    plt.rc('font', family='Noto Sans JP', size=CONFIG["GRAPH_FONT_SIZE"])

#==========================================================================================
# 3. Open-Meteo APIから気象データを取得するサブルーチン (既存維持)
#==========================================================================================
def fetch_weather_data(lat, lon, days):
    url = f"https://api.open-meteo.com/v1/forecast?latitude={lat}&longitude={lon}&hourly=temperature_2m,wind_speed_10m,wind_direction_10m,weather_code&timezone=Asia%2FTokyo&wind_speed_unit=ms&forecast_days={days}"
    try:
        data = requests.get(url).json()
        df = pd.DataFrame(data["hourly"])
        df['time'] = pd.to_datetime(df['time'])
        weather_results = [get_weather_info(code) for code in df['weather_code']]
        df['weather_name'] = [res[0] for res in weather_results]
        df['weather_color'] = [res[1] for res in weather_results]
        df['weather_icon'] = [res[2] for res in weather_results]
        return df
    except:
        return None

#==========================================================================================
# 5. 天気コードを変換するサブルーチン (既存維持)
#==========================================================================================
def get_weather_info(code):
    if pd.isna(code): return "不明", "black", "・"
    if code <= 1: return "晴", "#FF4500", "☀️"
    if code <= 3: return "曇", "#696969", "☁️"
    if code <= 48: return "霧", "#A9A9A9", "🌫️"
    if code <= 67: return "雨", "#00008B", "☔"
    if code <= 77: return "雪", "#00BFFF", "❄️"
    if code <= 82: return "雨", "#4682B4", "🌦️"
    if code <= 99: return "雷", "#800080", "⛈️"
    return "？", "black", "・"

#==========================================================================================
# 6. 風向角度を変換・判定するサブルーチン (既存維持)
#==========================================================================================
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
    
    def judge(row):
        speed = row['wind_speed_10m']
        if pd.isna(speed): return "#FFFFFF"
        if speed >= 10.0: return "crimson"
        if row['dir_name'] in target_dirs:
            if 5 <= speed < 10.0: return "orange"
            if 3 <= speed < 5: return "skyblue"
        return "#D3D3D3"
    
    df['color'] = df.apply(judge, axis=1)
    base_full_tide = datetime(2025, 1, 1, 6, 0)
    cycle_hours = 12.42
    df['tide_level'] = [100 * np.cos(2 * np.pi * ((t - base_full_tide).total_seconds() / 3600) / cycle_hours) if not pd.isna(t) else np.nan for t in df['time']]
    return df

#==========================================================================================
# 8. 共通の軸設定・フォーマッタ (既存維持)
#==========================================================================================
def get_x_axis_formatter():
    jp_weeks = ["月", "火", "水", "木", "金", "土", "日"]
    def formatter(x, p):
        dt = mdates.num2date(x)
        if dt.hour == 0: return dt.strftime('%H:%M') + f'\n({jp_weeks[dt.weekday()]})\n' + dt.strftime('%m/%d')
        elif dt.hour in [3, 9, 15, 21]: return f"\n{dt.strftime('%H:%M')}"
        else: return dt.strftime('%H:%M')
    return formatter

def apply_common_axis_settings(ax, df, formatter, now_jst):
    ax.axvline(now_jst, color='blue', linestyle='-', alpha=0.6, linewidth=2.5)
    ax.xaxis.set_major_locator(mdates.HourLocator(byhour=range(0, 24, 3)))
    ax.xaxis.set_major_formatter(plt.FuncFormatter(formatter))
    ax.xaxis.set_minor_locator(mdates.HourLocator(interval=1))
    ax.set_xlim(df['time'].iloc[0], df['time'].iloc[-1])
    ax.grid(True, which='major', linestyle=':', alpha=0.6, color='#000000')
    ax.grid(True, which='minor', linestyle=':', alpha=0.2, color='#888888')
    ax.tick_params(axis='x', which='major', labelsize=CONFIG["LABEL_SIZE"], pad=10)
    ax.tick_params(axis='y', labelsize=CONFIG["LABEL_SIZE"])

#==========================================================================================
# 9. 各チャート描画サブルーチン (既存維持)
#==========================================================================================
def render_wind_bar_chart(ax, df, danger_v, wind_step):
    bars = ax.bar(df['time'], df['wind_speed_10m'], color=df['color'], alpha=0.9, width=0.035)
    ax.axhline(y=danger_v, color='red', linestyle='--', linewidth=2, alpha=0.8)
    y_limit = max(df['wind_speed_10m'].max(), danger_v, 12) + 7
    ax.set_ylim(0, y_limit)
    ax.set_ylabel('風速 (m/s)', fontsize=CONFIG["LABEL_SIZE"])
    fs, step, base = CONFIG["ANNOT_SIZE"], CONFIG["ANNOT_Y_STEP"], CONFIG["ANNOT_BASE_Y"]
    for i, bar in enumerate(bars):
        if i % wind_step == 0:
            row = df.iloc[i]
            if pd.isna(row['wind_speed_10m']): continue
            by = bar.get_height()
            x = bar.get_x() + bar.get_width()/2.
            ax.text(x, by + base, f"{row['wind_speed_10m']:.0f}", ha='center', va='bottom', fontsize=fs-2)
            ax.text(x, by + base + step, row['arrow'], ha='center', va='bottom', fontsize=fs+2, fontweight='bold')
            ax.text(x, by + base + step*2, row['dir_name'], ha='center', va='bottom', fontsize=fs-2)
            ax.text(x, by + base + step*3, row['weather_name'], ha='center', va='bottom', color=row['weather_color'], fontweight='bold', fontsize=fs-1)

def render_temp_line_chart(ax, df):
    ax.plot(df['time'], df['temperature_2m'], color='#333333', linewidth=2, marker='o', markersize=3, markevery=3)
    ax.set_ylabel('気温 (℃)', fontsize=CONFIG["LABEL_SIZE"])

def render_tide_curve_chart(ax, df):
    ax.plot(df['time'], df['tide_level'], color='royalblue', linewidth=2.5)
    ax.fill_between(df['time'], df['tide_level'], -110, color='royalblue', alpha=0.15)
    ax.set_ylabel('潮位', fontsize=CONFIG["LABEL_SIZE"])
    ax.set_ylim(-120, 120)
    ax.set_yticks([])

#==========================================================================================
# 11. 高解像度グラフ生成 (サイズをさらに縮小: Y=0まで見えるように調整)
#==========================================================================================
@st.cache_data(show_spinner="グラフを生成中...")
def generate_high_res_graph(lat, lon, danger_v, selected_dirs_tuple):
    df = fetch_weather_data(lat, lon, 8)
    if df is None: return None, (0, 0)
    
    padding_df = pd.DataFrame({'time': [df['time'].iloc[0] - timedelta(hours=i) for i in range(1, 4)][::-1]})
    df = pd.concat([padding_df, df], ignore_index=True)
    df = process_wind_data(df, list(selected_dirs_tuple))
    
    # 【修正点】figsizeの第2引数（高さ）を 7.5 -> 5.5 に変更
    # これにより、文字の鮮明さを保ったまま、グラフの縦方向のサイズが小さくなります。
    fig, axes = plt.subplots(3, 1, figsize=(40, 5.5), dpi=CONFIG["DPI"], gridspec_kw={'height_ratios': CONFIG["HEIGHT_RATIOS"]})
    plt.subplots_adjust(hspace=0.6)
    
    formatter = get_x_axis_formatter()
    now_jst = datetime.now(timezone(timedelta(hours=9))).replace(tzinfo=None)
    
    render_wind_bar_chart(axes[0], df, danger_v, 3)
    render_temp_line_chart(axes[1], df)
    render_tide_curve_chart(axes[2], df)

    for ax in axes:
        apply_common_axis_settings(ax, df, formatter, now_jst)

    fig.tight_layout() 
    pos = axes[0].get_position() 
    ratio_info = (pos.x0, pos.width / (len(df) - 1))
    
    buf = io.BytesIO()
    fig.savefig(buf, format="png", bbox_inches=None, pad_inches=0)
    plt.close(fig) 
    
    img_b64 = base64.b64encode(buf.getvalue()).decode()
    return img_b64, ratio_info

#==========================================================================================
# 12. お天気アイコンHTML生成サブルーチン (高さを詰めてコンパクト化)
#==========================================================================================
def generate_weather_icons_html(df, ratio_info):
    start_x, hour_w = ratio_info
    icon_html = ""
    for i in range(3, len(df), 3):
        row = df.iloc[i]
        pos_left = (start_x + (i * hour_w)) * 100
        icon_html += f'<div style="position: absolute; left: {pos_left}%; transform: translateX(-50%); width: 80px; text-align: center; font-size: 32px;">{row["weather_icon"]}</div>'
    
    # 【修正点】heightを 50px -> 40px に変更し、グラフとの距離をさらに詰める
    return f'<div style="position: relative; width: 8000px; height: 40px; margin-bottom: -15px;">{icon_html}</div>'

#==========================================================================================
# 13. UI共通コンポーネント (同期・位置・既存維持)
#==========================================================================================
def sync_all_settings():
    STORAGE_KEY = CONFIG['STORAGE_KEY']
    if "initialized" not in st.session_state:
        stored_data = streamlit_js_eval(js_expressions=f"localStorage.getItem('{STORAGE_KEY}')", key="load_storage")
        if stored_data:
            try:
                data = json.loads(stored_data)
                st.session_state.lat, st.session_state.lon = float(data.get("lat")), float(data.get("lon"))
                st.session_state.last_basho = data.get("basho")
                st.session_state.danger_v = float(data.get("danger_v"))
                st.session_state.sel_dirs = data.get("sel_dirs")
                st.session_state.initialized = True
                st.rerun()
            except: st.session_state.initialized = True
        elif stored_data == "": st.session_state.initialized = True
        if "initialized" not in st.session_state: st.stop()

    save_data = {"lat": st.session_state.lat, "lon": st.session_state.lon, "basho": st.session_state.last_basho, 
                 "danger_v": st.session_state.get("danger_v", 10.0), "sel_dirs": st.session_state.get("sel_dirs", [])}
    streamlit_js_eval(js_expressions=f"localStorage.setItem('{STORAGE_KEY}', '{json.dumps(save_data)}')")

def handle_current_location_update():
    if st.button("🔄 📍現在地を取得　　　　　　　　　　", use_container_width=True):
        st.session_state.waiting_loc = True
        st.session_state.geo_key = f"geo_{datetime.now().timestamp()}"
        st.rerun()
    if st.session_state.get("waiting_loc"):
        loc = get_geolocation(component_key=st.session_state.get("geo_key"))
        if loc:
            st.session_state.lat, st.session_state.lon = round(loc['coords']['latitude'], 4), round(loc['coords']['longitude'], 4)
            st.session_state.last_basho, st.session_state.waiting_loc = "現在地", False
            st.rerun()

#==========================================================================================
# 16. メインフロー
#==========================================================================================
def main():
    setup_font()
    st.markdown("""<style>
        .block-container { padding-top: 3.5rem !important; }
        h1 { margin-bottom: -15px !important; }
        div.stButton > button p { text-align: left !important; }
        div.stButton > button { justify-content: flex-start !important; }
        </style>""", unsafe_allow_html=True)

    st.markdown(f'<h1 style="font-size:{CONFIG["TITLE_SIZE"]}px;">⛵ 高須風チェッカー</h1>', unsafe_allow_html=True)
    
    if 'lat' not in st.session_state: st.session_state.lat = CONFIG["DEFAULT_LAT"]
    if 'lon' not in st.session_state: st.session_state.lon = CONFIG["DEFAULT_LON"]
    if 'last_basho' not in st.session_state: st.session_state.last_basho = CONFIG["DEFAULT_BASHO"]
    sync_all_settings()

    master = CONFIG["LOCATION_MASTER"].copy()
    display_options = {f"{n} ({c[0]:.4f}, {c[1]:.4f})": n for n, c in master.items()}
    curr_label = f"📍 現在地 ({st.session_state.lat:.4f}, {st.session_state.lon:.4f})"
    display_options[curr_label] = "現在地"
    display_options["🗺️ 地図で指定"] = "地図で指定"
    
    rev_display = {v: k for k, v in display_options.items()}
    sel_name = st.selectbox("地点を選択してください", list(display_options.keys()), index=list(display_options.keys()).index(rev_display.get(st.session_state.last_basho, curr_label)))
    basho = display_options[sel_name]

    if basho != st.session_state.last_basho:
        st.session_state.last_basho = basho
        if basho not in ["地図で指定", "現在地"]: st.session_state.lat, st.session_state.lon = master[basho]
        st.rerun()

    col1, col2 = st.columns([0.7, 0.7])
    with col1: handle_current_location_update()
    with col2: 
        if st.button(f"🔄 グラフ更新 ({datetime.now(timezone(timedelta(hours=9))).strftime('%H:%M:%S')})　　", use_container_width=True):
            st.cache_data.clear()
            st.rerun()
    
    st.sidebar.header("表示設定")
    dv = st.sidebar.number_input("危険風速ライン(m/s)", value=st.session_state.get("danger_v", 10.0), step=0.5)
    st.session_state.danger_v = dv
    sel_dirs = []
    cols = st.sidebar.columns(2)
    for i, d in enumerate(ALL_DIRECTIONS):
        if cols[i%2].checkbox(d, value=(d in st.session_state.get("sel_dirs", CONFIG["DEFAULT_DIRS"])), key=f"c_{d}"): sel_dirs.append(d)
    st.session_state.sel_dirs = sel_dirs

    img_data, ratio_info = generate_high_res_graph(st.session_state.lat, st.session_state.lon, dv, tuple(sel_dirs))
    
    if img_data:
        df_raw = fetch_weather_data(st.session_state.lat, st.session_state.lon, 8)
        p_df = pd.DataFrame({'time': [df_raw['time'].iloc[0] - timedelta(hours=i) for i in range(1, 4)][::-1]})
        df_full = pd.concat([p_df, df_raw], ignore_index=True)
        
        icons_html = generate_weather_icons_html(df_full, ratio_info)
        graph_html = f'<img src="data:image/png;base64,{img_data}" style="width: 8000px; max-width: none; display: block;">'
        
        st.markdown(f'<div style="overflow-x: auto; background: white; border-radius: 8px; position: relative;">{icons_html}{graph_html}</div>', unsafe_allow_html=True)

if __name__ == "__main__":
    main()

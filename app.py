# -*- coding: utf-8 -*-
# 最終更新 2025.12.28 デザイン調整機能搭載・最終統合版
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
    "GRAPH_WIDTH": 40,
    "GRAPH_HIGHT": 5.5,
    "LABEL_SIZE": 9,
    "ANNOT_SIZE": 10,
    "DPI": 200,
    "MAP_HEIGHT": 350,
    "DEFAULT_LEFT_MARGIN": 0.05,  # 初期状態で左端に寄せるための値
    "HEIGHT_RATIOS": [4.4, 1.2, 0.8], # 縦比率を厳守
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
# 2. グラフ設定サブルーチン
#==========================================================================================
def setup_font(font_size):
    font_url = "https://github.com/google/fonts/raw/main/ofl/notosansjp/NotoSansJP%5Bwght%5D.ttf"
    font_path = "NotoSansJP.ttf"
    if not os.path.exists(font_path):
        urllib.request.urlretrieve(font_url, font_path)
    fm.fontManager.addfont(font_path)
    # スライダーで調整されたフォントサイズを反映
    plt.rc('font', family='Noto Sans JP', size=font_size)
    
#==========================================================================================
# 3.〜10. 各種計算・描画サブルーチン (既存ロジックを維持)
#==========================================================================================
def fetch_weather_data(lat, lon, days):
    url = f"https://api.open-meteo.com/v1/forecast?latitude={lat}&longitude={lon}&hourly=temperature_2m,wind_speed_10m,wind_direction_10m,weather_code&timezone=Asia%2FTokyo&wind_speed_unit=ms&forecast_days={days}"
    try:
        data = requests.get(url).json()
        df = pd.DataFrame(data["hourly"])
        df['time'] = pd.to_datetime(df['time'])
        # お天気アイコン用（既存の天気コードから絵文字への変換）
        def get_icon(code):
            if code <= 2: return "☀️"
            if code <= 48: return "☁️"
            if code <= 99: return "☔"
            return "❓"
        df['weather_icon'] = df['weather_code'].apply(get_icon)
        return df
    except: return None

def get_tide_level(times):
    base_full_tide = datetime(2025, 1, 1, 6, 0)
    cycle_hours = 12.42
    levels = []
    for t in times:
        if pd.isna(t):
            levels.append(np.nan)
            continue
        hours_from_base = (t - base_full_tide).total_seconds() / 3600
        level = 100 * np.cos(2 * np.pi * hours_from_base / cycle_hours)
        levels.append(level)
    return levels

def get_weather_info(code):
    if pd.isna(code): return "", "black"
    if code <= 2: return "晴", "#FF4500"
    if code <= 48: return "曇", "#696969"
    if code <= 99: return "雨", "#00008B"
    return "？", "black"

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

#==========================================================================================
# 7. X軸ラベルフォーマッタ (修正版: 0:00=3行、他=時刻のみ)
#==========================================================================================
def get_x_axis_formatter():
    jp_weeks = ["月", "火", "水", "木", "金", "土", "日"]
    def formatter(x, p):
        dt = mdates.num2date(x)
        if dt.hour == 0:
            return dt.strftime('%H:%M') + f'\n{dt.strftime("%m/%d")}\n({jp_weeks[dt.weekday()]})'
        elif dt.hour in [3, 6, 9, 12, 15, 18, 21]:
            return dt.strftime('%H:%M')
        else:
            return ""
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

def render_wind_bar_chart(ax, df, danger_v, wind_step):
    bars = ax.bar(df['time'], df['wind_speed_10m'], color=df['color'], alpha=0.9, width=0.035)
    ax.axhline(y=danger_v, color='red', linestyle='--', linewidth=2, alpha=0.8)
    max_speed = df['wind_speed_10m'].max()
    y_limit = max(max_speed, danger_v, 12) + 7
    ax.set_ylim(0, y_limit)
    ax.set_ylabel('風速 (m/s)', fontsize=CONFIG["LABEL_SIZE"])
    fs, step, base = CONFIG["ANNOT_SIZE"], CONFIG["ANNOT_Y_STEP"], CONFIG["ANNOT_BASE_Y"]
    for i, bar in enumerate(bars):
        if i % wind_step == 0:
            row = df.iloc[i]
            if pd.isna(row['wind_speed_10m']): continue
            base_y = bar.get_height()
            x_pos = bar.get_x() + bar.get_width()/2.
            ax.text(x_pos, base_y + base, f"{row['wind_speed_10m']:.0f}", ha='center', va='bottom', fontsize=fs-2)
            ax.text(x_pos, base_y + base + step, row['arrow'], ha='center', va='bottom', fontsize=fs+2, fontweight='bold')
            ax.text(x_pos, base_y + base + step*2, row['dir_name'], ha='center', va='bottom', fontsize=fs-2)
            ax.text(x_pos, base_y + base + step*3, row['w_text'], ha='center', va='bottom', color=row['w_color'], fontweight='bold', fontsize=fs-1)

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
# 11. 高解像度グラフ生成 (デザイン調整値反映版)
#==========================================================================================
@st.cache_data(show_spinner="グラフを調整中...")
def generate_high_res_graph(lat, lon, danger_v, selected_dirs_tuple, design_params):
    # --- データ準備 ---
    df = fetch_weather_data(lat, lon, 8)
    if df is None: return None, (0, 0)
    padding_df = pd.DataFrame({'time': [df['time'].iloc[0] - timedelta(hours=i) for i in range(1, 4)][::-1]})
    df = pd.concat([padding_df, df], ignore_index=True)
    df = process_wind_data(df, list(selected_dirs_tuple))
    
    # --- パラメータ取得 ---
    w = design_params.get("width", CONFIG["GRAPH_WIDTH"])
    h = design_params.get("height", CONFIG["GRAPH_HIGHT"])
    l_mar = design_params.get("left_margin", CONFIG.get("DEFAULT_LEFT_MARGIN", 0.05))
    r_mar = design_params.get("right_margin", 0.98)
    ls = design_params.get("label_size", CONFIG["LABEL_SIZE"])
    ans = design_params.get("annot_size", CONFIG["ANNOT_SIZE"])

    # --- 縦比率の計算 ---
    ratios = CONFIG["HEIGHT_RATIOS"]
    total_r = sum(ratios)
    # 各グラフの高さ（%）を算出（余白分を考慮して調整）
    h_unit = 0.75 / total_r 
    h0, h1, h2 = ratios[0]*h_unit, ratios[1]*h_unit, ratios[2]*h_unit
    
    fig, axes = plt.subplots(3, 1, figsize=(w, h), dpi=CONFIG["DPI"])
    
    # 物理的な位置の固定（縦比率を適用）
    graph_w = r_mar - l_mar
    axes[0].set_position([l_mar, 0.95 - h0, graph_w, h0])      # 風速 (上)
    axes[1].set_position([l_mar, 0.90 - h0 - h1, graph_w, h1]) # 気温 (中)
    axes[2].set_position([l_mar, 0.85 - h0 - h1 - h2, graph_w, h2]) # 潮位 (下)

    # --- 描画ロジック ---
    formatter = get_x_axis_formatter()
    now_jst = datetime.now(timezone(timedelta(hours=9))).replace(tzinfo=None)
    
    # 風速
    bars = axes[0].bar(df['time'], df['wind_speed_10m'], color=df['color'], alpha=0.9, width=0.035)
    axes[0].axhline(y=danger_v, color='red', linestyle='--', linewidth=2, alpha=0.8)
    axes[0].set_ylim(0, max(df['wind_speed_10m'].max(), danger_v, 12) + 7)
    axes[0].set_ylabel('風速 (m/s)', fontsize=ls)
    
    step, base = CONFIG["ANNOT_Y_STEP"], CONFIG["ANNOT_BASE_Y"]
    for i, bar in enumerate(bars):
        if i % 3 == 0:
            row = df.iloc[i]
            if pd.isna(row['wind_speed_10m']): continue
            by = bar.get_height()
            xp = bar.get_x() + bar.get_width()/2.
            axes[0].text(xp, by + base, f"{row['wind_speed_10m']:.0f}", ha='center', va='bottom', fontsize=ans-2)
            axes[0].text(xp, by + base + step, row['arrow'], ha='center', va='bottom', fontsize=ans+2, fontweight='bold')
            axes[0].text(xp, by + base + step*2, row['dir_name'], ha='center', va='bottom', fontsize=ans-2)
            axes[0].text(xp, by + base + step*3, row['w_text'], ha='center', va='bottom', color=row['w_color'], fontweight='bold', fontsize=ans-1)

    render_temp_line_chart(axes[1], df)
    axes[1].set_ylabel('気温', fontsize=ls)
    render_tide_curve_chart(axes[2], df)
    axes[2].set_ylabel('潮位', fontsize=ls)

    for ax in axes:
        ax.axvline(now_jst, color='blue', linestyle='-', alpha=0.6, linewidth=2.5)
        ax.xaxis.set_major_locator(mdates.HourLocator(byhour=range(0, 24, 3)))
        ax.xaxis.set_major_formatter(plt.FuncFormatter(formatter))
        ax.set_xlim(df['time'].iloc[0], df['time'].iloc[-1])
        ax.grid(True, which='major', linestyle=':', alpha=0.6, color='#000000')
        ax.tick_params(axis='x', labelsize=ls, pad=10)
        ax.tick_params(axis='y', labelsize=ls)

    # --- アイコン位置の計算（ズレ防止の核心部） ---
    # 描画された axes[0] の「実際の座標」を直接取得して比率を出す
    final_pos = axes[0].get_position()
    ratio_info = (final_pos.x0, final_pos.width / (len(df) - 1))
    
    buf = io.BytesIO()
    fig.savefig(buf, format="png")
    plt.close(fig) 
    return base64.b64encode(buf.getvalue()).decode(), ratio_info
    
#==========================================================================================
# 12. 【最新統合】お天気アイコンHTML生成 (ズレ防止・コンパクト版)
#==========================================================================================
def generate_weather_icons_html(df, ratio_info, graph_width_param):
    start_x, hour_w = ratio_info
    icon_html = ""
    for i in range(3, len(df), 3):
        row = df.iloc[i]
        pos_left = (start_x + (i * hour_w)) * 100
        icon_html += f'<div style="position: absolute; left: {pos_left}%; transform: translateX(-50%); width: 80px; text-align: center; font-size: 32px;">{row["weather_icon"]}</div>'
    
    # graph_width_param（例: 40）に応じて、全体の横幅（px）を計算
    # 200dpi設定の場合、figsizeの1単位は約200pxに相当しますが、
    # ここでは十分な広さを確保するために係数（例: 200）を掛けます。
    container_width = graph_width_param * 200 
    return f'<div style="position: relative; width: {container_width}px; height: 40px; margin-bottom: -15px;">{icon_html}</div>'
    
#==========================================================================================
# 13. 地図UI表示サブルーチン (既存維持)
#==========================================================================================
def show_location_map():
    st.info("地図の中央地点のグラフを描画表示することができます。")
    st.markdown("""<style>
        div[data-testid="stHorizontalBlock"] { flex-wrap: nowrap !important; justify-content: center !important; }
        [data-testid="column"] { min-width: 0px !important; }
        .guide-arrow-main { color: crimson; font-size: 24px; font-weight: bold; text-align: center; }
        </style>""", unsafe_allow_html=True)
    
    m = folium.Map(location=[st.session_state.lat, st.session_state.lon], zoom_start=13)
    folium.Marker([st.session_state.lat, st.session_state.lon], icon=folium.Icon(color='red')).add_to(m)
    
    col_l1, col_m1, col_r1 = st.columns([1, 18, 1])
    with col_m1: st.markdown("<div class='guide-arrow-main'>▼</div>", unsafe_allow_html=True)
    
    col_l2, col_m2, col_r2 = st.columns([1, 18, 1])
    with col_l2: st.markdown(f"<div style='line-height:{CONFIG['MAP_HEIGHT']}px; text-align:right;' class='guide-arrow-main'>▶</div>", unsafe_allow_html=True)
    with col_m2: map_out = st_folium(m, width=None, height=CONFIG["MAP_HEIGHT"], key=f"map_{st.session_state.lat}_{st.session_state.lon}", returned_objects=["center"])
    with col_r2: st.markdown(f"<div style='line-height:{CONFIG['MAP_HEIGHT']}px; text-align:left;' class='guide-arrow-main'>◀</div>", unsafe_allow_html=True)
    
    col_l3, col_m3, col_r3 = st.columns([1, 18, 1])
    with col_m3: st.markdown("<div class='guide-arrow-main' style='margin-top:-10px;'>▲</div>", unsafe_allow_html=True)
    
    if map_out and map_out.get("center"):
        if st.button("グラフ描画地点確定", use_container_width=True):
            st.session_state.lat = map_out["center"]["lat"]
            st.session_state.lon = map_out["center"]["lng"]
            st.session_state.last_basho = "地図で指定"
            st.rerun()

#==========================================================================================
# 14. ブラウザ同期サブルーチン (コンプリート版ロジックを完全維持)
#==========================================================================================
def sync_all_settings():
    STORAGE_KEY = CONFIG['STORAGE_KEY']
    if "initialized" not in st.session_state:
        stored_data = streamlit_js_eval(js_expressions=f"localStorage.getItem('{STORAGE_KEY}')", key="load_storage")
        if stored_data:
            try:
                data = json.loads(stored_data)
                st.session_state.lat = float(data.get("lat", CONFIG["DEFAULT_LAT"]))
                st.session_state.lon = float(data.get("lon", CONFIG["DEFAULT_LON"]))
                st.session_state.last_basho = data.get("basho", CONFIG["DEFAULT_BASHO"])
                st.session_state.danger_v = float(data.get("danger_v", CONFIG["DEFAULT_DANGER_V"]))
                st.session_state.sel_dirs = data.get("sel_dirs", CONFIG["DEFAULT_DIRS"])
                st.session_state.initialized = True
                st.rerun()
            except:
                st.session_state.initialized = True
        elif stored_data == "":
            st.session_state.initialized = True
        
        if "initialized" not in st.session_state:
            st.stop()

    save_data = {
        "lat": st.session_state.lat,
        "lon": st.session_state.lon,
        "basho": st.session_state.last_basho,
        "danger_v": st.session_state.get("danger_v", CONFIG["DEFAULT_DANGER_V"]),
        "sel_dirs": st.session_state.get("sel_dirs", CONFIG["DEFAULT_DIRS"])
    }
    js_save = f"localStorage.setItem('{STORAGE_KEY}', '{json.dumps(save_data)}')"
    safe_key = f"save_storage_{st.session_state.last_basho}"
    streamlit_js_eval(js_expressions=js_save, key=safe_key)

#==========================================================================================
# 15. 現在地取得サブルーチン (全幅・左寄せUIを維持)
#==========================================================================================
def handle_current_location_update():
    if st.button("🔄 📍現在地を取得　　　　　　　　　　", use_container_width=True):
        st.session_state.waiting_loc = True
        st.session_state.geo_key = f"geo_{datetime.now().timestamp()}"
        st.rerun()

    if st.session_state.get("waiting_loc"):
        st.info("🛰️ 現在地を取得中...")
        loc = get_geolocation(component_key=st.session_state.get("geo_key"))
        if loc:
            st.session_state.lat = round(loc['coords']['latitude'], 4)
            st.session_state.lon = round(loc['coords']['longitude'], 4)
            st.session_state.last_basho = "現在地"
            st.session_state.waiting_loc = False
            st.rerun()
        elif loc is False:
            st.error("❌ 取得失敗")
            if st.button("キャンセル"):
                st.session_state.waiting_loc = False
                st.rerun()

#==========================================================================================
# 16. サイドバー設定 (デザイン調整パネル搭載)
#==========================================================================================
def show_sidebar_controls():
    st.sidebar.header("表示設定")
    dv = st.sidebar.number_input("危険風速ライン(m/s)", value=st.session_state.get("danger_v", CONFIG["DEFAULT_DANGER_V"]), step=0.5)
    st.session_state.danger_v = dv
    
    st.sidebar.write("色付風向")
    saved_dirs = st.session_state.get("sel_dirs", CONFIG["DEFAULT_DIRS"])
    sel_dirs = []
    cols = st.sidebar.columns(2)
    for i, d in enumerate(ALL_DIRECTIONS):
        with cols[i % 2]:
            if st.checkbox(d, value=(d in saved_dirs), key=f"chk_{d}"): sel_dirs.append(d)
    st.session_state.sel_dirs = sel_dirs

    # --- 開発者用デザイン調整モード ---
    st.sidebar.markdown("---")
    design_params = {
        "width": CONFIG["GRAPH_WIDTH"], # 追加
        "height": CONFIG["GRAPH_HIGHT"],
        "font_size": CONFIG["GRAPH_FONT_SIZE"],
        "label_size": CONFIG["LABEL_SIZE"],
        "annot_size": CONFIG["ANNOT_SIZE"]
    }
    if st.sidebar.checkbox("🛠 開発者デザイン調整モード"):
        st.sidebar.subheader("外観微調整スライダー")
        # 横幅のスライダーを追加（20〜60の範囲で調整可能）
        design_params["width"] = st.sidebar.slider("グラフの横幅(3h幅)", 10, 80, CONFIG["GRAPH_WIDTH"], 1)
        # --- 余白調整用のスライダーを追加 ---
        design_params["left_margin"] = st.sidebar.slider("左余白(0.02-0.2)", 0.02, 0.20, 0.05, 0.01)
        design_params["right_margin"] = st.sidebar.slider("右余白(0.8-0.99)", 0.80, 0.99, 0.98, 0.01)
        # -----------------------------------
        design_params["height"] = st.sidebar.slider("グラフの高さ", 3.0, 10.0, float(CONFIG["GRAPH_HIGHT"]), 0.1)
        design_params["font_size"] = st.sidebar.slider("基本フォント", 5, 20, CONFIG["GRAPH_FONT_SIZE"], 1)
        design_params["label_size"] = st.sidebar.slider("軸ラベル", 5, 20, CONFIG["LABEL_SIZE"], 1)
        design_params["annot_size"] = st.sidebar.slider("グラフ内文字", 5, 20, CONFIG["ANNOT_SIZE"], 1)
        
        if st.sidebar.button("この値をCONFIGに固定(表示のみ)"):
            st.sidebar.code(f'"GRAPH_WIDTH": {design_params["width"]},\n"GRAPH_HIGHT": {design_params["height"]},\n"GRAPH_FONT_SIZE": {design_params["font_size"]},\n"LABEL_SIZE": {design_params["label_size"]},\n"ANNOT_SIZE": {design_params["annot_size"]}')

    return dv, sel_dirs, design_params
#==========================================================================================
# 17. 更新ボタン表示 (全幅・左寄せUIを維持)
#==========================================================================================
def render_header_info(current_basho_name):
    now = datetime.now(timezone(timedelta(hours=9)))
    date_time_str = now.strftime('%Y/%m/%d %H:%M:%S')
    update_label = f"🔄 グラフ更新 ({date_time_str})　　    　"
    if st.button(update_label, use_container_width=True):
        st.cache_data.clear()
        st.rerun()

#==========================================================================================
# 18. メインフロー (UI完全復元 ＆ デザイン調整機能 統合版)
#==========================================================================================
def main():
    # サイドバーからパラメータを取得（デザイン調整用の辞書 design_params を受け取る）
    danger_v, sel_dirs, design_params = show_sidebar_controls()
    
    # スライダーで選ばれた基本フォントサイズを反映
    setup_font(design_params["font_size"])

    # --- CSS注入：UIの左寄せと余白調整 ---
    st.markdown(f"""
        <style>
            .block-container {{ padding-top: 3.5rem !important; padding-bottom: 0rem !important; }}
            h1 {{ margin-top: 0px !important; margin-bottom: -15px !important; line-height: 1.0 !important; }}
            [data-testid="stVerticalBlock"] {{ gap: 0.3rem !important; }}
            div.stButton > button p {{ text-align: left !important; width: 100% !important; }}
            div.stButton > button {{ justify-content: flex-start !important; }}
        </style>
    """, unsafe_allow_html=True)

    st.markdown(f'<h1 style="font-size:{CONFIG["TITLE_SIZE"]}px;">⛵ Wind_Checker! </h1>', unsafe_allow_html=True)
    
    # セッション状態の初期化
    if 'lat' not in st.session_state: st.session_state.lat = CONFIG["DEFAULT_LAT"]
    if 'lon' not in st.session_state: st.session_state.lon = CONFIG["DEFAULT_LON"]
    if 'last_basho' not in st.session_state: st.session_state.last_basho = CONFIG["DEFAULT_BASHO"]
    
    # ブラウザLocalStorageとの同期（苦労して完成させたロジックを維持）
    sync_all_settings()

    if "initialized" not in st.session_state:
        st.info("設定を読み込み中...")
        st.stop()

    # --- 地点選択コンボボックス ---
    master = CONFIG["LOCATION_MASTER"].copy()
    display_options = {}
    for name, coords in master.items():
        display_options[f"{name} ({coords[0]:.4f}, {coords[1]:.4f})"] = name

    current_loc_label = f"📍 現在地 ({st.session_state.lat:.4f}, {st.session_state.lon:.4f})"
    display_options[current_loc_label] = "現在地"
    display_options["🗺️ 地図で指定"] = "地図で指定"

    reverse_display = {v: k for k, v in display_options.items()}
    current_display_val = reverse_display.get(st.session_state.last_basho, current_loc_label)
    
    selected_display = st.selectbox(
        "地点を選択してください", 
        list(display_options.keys()), 
        index=list(display_options.keys()).index(current_display_val)
    )
    basho = display_options[selected_display]

    if basho != st.session_state.last_basho:
        st.session_state.last_basho = basho
        if basho not in ["地図で指定", "現在地"]:
            st.session_state.lat, st.session_state.lon = master[basho]
        if basho == "地図で指定":
            st.session_state.show_map_state = True
        st.rerun()

    # 地図の表示制御
    show_map = st.checkbox("地図表示", value=st.session_state.get('show_map_state', False))
    st.session_state.show_map_state = show_map
    if show_map:
        show_location_map()

    # --- ボタン配置（0.7+0.7の黄金比カラムを維持） ---
    col1, col2 = st.columns([0.7, 0.7]) 
    with col1:
        handle_current_location_update()
    with col2:
        render_header_info(basho) 
    
    # --- グラフ描画実行 ---
    # デザインパラメータ（スライダーの値）を引数として渡す
    img_b64, ratio_info = generate_high_res_graph(
        st.session_state.lat, 
        st.session_state.lon, 
        danger_v, 
        tuple(sel_dirs), 
        design_params
    )
    
    if img_b64:
        # 天気アイコン用のデータ準備
        df_for_icons = fetch_weather_data(st.session_state.lat, st.session_state.lon, 8)
        padding_df = pd.DataFrame({'time': [df_for_icons['time'].iloc[0] - timedelta(hours=i) for i in range(1, 4)][::-1]})
        df_full = pd.concat([padding_df, df_for_icons], ignore_index=True)
        
        # HTML生成（アイコン＋グラフ画像）
        # icons_html の生成時に design_params["width"] を渡すように変更
        icons_html = generate_weather_icons_html(df_full, ratio_info, design_params["width"])
        
        # グラフ本体は100%幅で表示（中身はmin-widthでスクロール可能に）
        graph_html = f'<img src="data:image/png;base64,{img_b64}" style="width: 100%; min-width: 8000px; display: block;">'
        
        st.markdown(
            f'<div style="overflow-x: auto; background: white; white-space: nowrap;">'
            f'{icons_html}{graph_html}</div>', 
            unsafe_allow_html=True
        )

#==========================================================================================
# アプリケーション起動
#==========================================================================================
if __name__ == "__main__":
    main()

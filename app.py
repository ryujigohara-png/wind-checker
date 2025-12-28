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
    "DEFAULT_LEFT_MARGIN": 0.02,  # 初期状態で左端に寄せるための値
    "DEFAULT_RIGHT_MARGIN": 0.98,  # 初期状態で右端に寄せるための値
    "HEIGHT_RATIOS": [4.4, 1.2, 0.8], # 縦比率を厳守
    "LOC_INFO_FONT_SIZE": "16px",
    "LOC_INFO_COLOR": "#1e88e5",
    "LOC_INFO_MARGIN_TOP": "-10px",
    "DEFAULT_LAT": 31.337,
    "DEFAULT_LON": 130.795,
    "DEFAULT_BASHO": "高須沖(鹿児島県)",
    "DEFAULT_DANGER_V": 10.0,
    "DEFAULT_DIRS": ["南","南南西","南西","西南西","西","西北西","北西","北北西"],
    "ANNOT_Y_STEP": 1.8,
    "ANNOT_BASE_Y": 1.2,
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
    # --- 1. データ取得と前処理 ---
    df = fetch_weather_data(lat, lon, 8)
    if df is None: return None, (0, 0)
    
    # グラフ左端にダミーの余白（3時間分）を追加
    padding_df = pd.DataFrame({'time': [df['time'].iloc[0] - timedelta(hours=i) for i in range(1, 4)][::-1]})
    df = pd.concat([padding_df, df], ignore_index=True)
    df = process_wind_data(df, list(selected_dirs_tuple))
    
    # --- 2. パラメータ取得 (CONFIG からの初期値読み込みを徹底) ---
    w = design_params.get("width", CONFIG.get("GRAPH_WIDTH", 40))
    h = design_params.get("height", CONFIG.get("GRAPH_HIGHT", 5.5))
    
    # 左余白・右余白を CONFIG から取得（指定がない場合は 0.02 / 0.98）
    l_mar = design_params.get("left_margin", CONFIG.get("DEFAULT_LEFT_MARGIN", 0.02))
    r_mar = design_params.get("right_margin", CONFIG.get("DEFAULT_RIGHT_MARGIN", 0.98))
    
    ls = design_params.get("label_size", CONFIG.get("LABEL_SIZE", 9))
    ans = design_params.get("annot_size", CONFIG.get("ANNOT_SIZE", 10))

    # --- 3. グラフ枠の生成と位置確定 ---
    fig, axes = plt.subplots(3, 1, figsize=(w, h), dpi=CONFIG.get("DPI", 200))
    
    # CONFIGの縦比率 [4.4, 1.2, 0.8] を反映
    ratios = CONFIG.get("HEIGHT_RATIOS", [4.4, 1.2, 0.8])
    total_r = sum(ratios)
    available_h = 0.75 
    y_gap = 0.12  # 日付ラベル表示のための隙間を確保
    h_unit = (available_h - (y_gap * 2)) / total_r
    h0, h1, h2 = ratios[0]*h_unit, ratios[1]*h_unit, ratios[2]*h_unit
    
    graph_w = r_mar - l_mar
    # 物理的な位置（左, 下, 幅, 高さ）を先に確定
    axes[0].set_position([l_mar, 0.95 - h0, graph_w, h0])      # 風速
    axes[1].set_position([l_mar, 0.90 - h0 - h1, graph_w, h1]) # 気温
    axes[2].set_position([l_mar, 0.85 - h0 - h1 - h2, graph_w, h2]) # 潮位

    # --- 4. 描画ロジック (確定した axes に対して描画) ---
    formatter = get_x_axis_formatter()
    now_jst = datetime.now(timezone(timedelta(hours=9))).replace(tzinfo=None)
    
    # 風速棒グラフ
    bars = axes[0].bar(df['time'], df['wind_speed_10m'], color=df['color'], alpha=0.9, width=0.035)
    axes[0].axhline(y=danger_v, color='red', linestyle='--', linewidth=2, alpha=0.8)
    axes[0].set_ylim(0, max(df['wind_speed_10m'].max(), danger_v, 12) + 7)
    axes[0].set_ylabel('風速 (m/s)', fontsize=ls)
    
    # 棒グラフ上の風向・数値・天気テキスト
    step, base = CONFIG.get("ANNOT_Y_STEP", 1.8), CONFIG.get("ANNOT_BASE_Y", 1.2)
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

    # 気温と潮位の描画（外部関数呼び出し）
    render_temp_line_chart(axes[1], df)
    axes[1].set_ylabel('気温', fontsize=ls)
    render_tide_curve_chart(axes[2], df)
    axes[2].set_ylabel('潮位', fontsize=ls)

    # --- 5. 軸の共通設定 (日付・曜日の復活) ---
    for i, ax in enumerate(axes):
        ax.axvline(now_jst, color='blue', linestyle='-', alpha=0.6, linewidth=2.5)
        ax.xaxis.set_major_locator(mdates.HourLocator(byhour=range(0, 24, 3)))
        
        # 重要な日付・曜日フォーマッタを風速(axes[0])と潮位(axes[2])に適用
        ax.xaxis.set_major_formatter(plt.FuncFormatter(formatter))
        
        ax.set_xlim(df['time'].iloc[0], df['time'].iloc[-1])
        ax.grid(True, which='major', linestyle=':', alpha=0.6, color='#000000')
        ax.tick_params(axis='x', labelsize=ls, pad=8)
        ax.tick_params(axis='y', labelsize=ls)

    # --- 6. アイコン同期情報の取得と画像出力 ---
    final_pos = axes[0].get_position()
    ratio_info = (final_pos.x0, final_pos.width / (len(df) - 1))
    
    buf = io.BytesIO()
    fig.savefig(buf, format="png")
    plt.close(fig) 
    return base64.b64encode(buf.getvalue()).decode(), ratio_info

# ==========================================================================================
# 天気アイコン生成関数（幅可変対応版）
# ==========================================================================================
def generate_weather_icons_html(df, ratio_info, graph_width_param):
    start_x, hour_w = ratio_info
    icon_html = ""
    for i in range(3, len(df), 3):
        row = df.iloc[i]
        pos_left = (start_x + (i * hour_w)) * 100
        icon_html += f'<div style="position: absolute; left: {pos_left}%; transform: translateX(-50%); width: 80px; text-align: center; font-size: 32px; z-index: 10;">{row["weather_icon"]}</div>'
    
    # コンテナ幅をグラフ幅(width)に連動させて計算
    container_width = graph_width_param * 200 
    return f'<div style="position: relative; width: {container_width}px; height: 40px; margin-bottom: -15px;">{icon_html}</div>'
    

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
# 18. サイドバー
#==========================================================================================
def show_sidebar_controls():
    st.sidebar.header("表示設定")
    
    # 危険風速ライン
    danger_v = st.sidebar.number_input(
        "危険風速ライン(m/s)", 
        min_value=0.0, max_value=30.0, 
        value=float(CONFIG.get("DANGER_WIND_SPEED", 12.0)), 
        step=0.5
    )

    # 色付風向
    st.sidebar.subheader("色付風向")
    cols = st.sidebar.columns(2)
    sel_dirs = []
    all_dirs = ["北", "北北東", "北東", "東北東", "東", "東南東", "南東", "南南東", 
                "南", "南南西", "南西", "西南西", "西", "西北西", "北西", "北北西"]
    default_sel = CONFIG.get("DEFAULT_SELECTED_DIRS", ["南", "南南西", "南西", "西南西", "西", "西北西", "北西", "北北西"])
    
    for i, d in enumerate(all_dirs):
        with cols[i % 2]:
            if st.checkbox(d, value=(d in default_sel), key=f"dir_{d}"):
                sel_dirs.append(d)

    st.sidebar.markdown("---")
    
    design_params = {}
    if st.sidebar.checkbox("🛠 開発者デザイン調整モード", value=True):
        st.sidebar.subheader("外観微調整スライダー")
        
        # 数値はすべて CONFIG から取得
        design_params["width"] = st.sidebar.slider("グラフの横幅(3h幅)", 10, 100, int(CONFIG.get("GRAPH_WIDTH", 40)))
        design_params["left_margin"] = st.sidebar.slider("左余白(0.02-0.2)", 0.02, 0.20, float(CONFIG.get("DEFAULT_LEFT_MARGIN", 0.02)), step=0.01)
        design_params["right_margin"] = st.sidebar.slider("右余白(0.8-0.99)", 0.80, 0.99, float(CONFIG.get("DEFAULT_RIGHT_MARGIN", 0.98)), step=0.01)
        design_params["height"] = st.sidebar.slider("グラフの高さ", 3.0, 15.0, float(CONFIG.get("GRAPH_HIGHT", 5.5)), step=0.5)
        
        # キー名を base_font_size に統一
        design_params["base_font_size"] = st.sidebar.slider("基本フォント", 5, 20, int(CONFIG.get("BASE_FONT_SIZE", 10)))
        design_params["label_size"] = st.sidebar.slider("軸ラベル", 5, 20, int(CONFIG.get("LABEL_SIZE", 9)))
        design_params["annot_size"] = st.sidebar.slider("グラフ内文字", 5, 20, int(CONFIG.get("ANNOT_SIZE", 10)))
        
        if st.sidebar.button("この値をCONFIGに固定(表示のみ)"):
            st.sidebar.code(f"""
"DEFAULT_LEFT_MARGIN": {design_params['left_margin']},
"DEFAULT_RIGHT_MARGIN": {design_params['right_margin']},
"GRAPH_WIDTH": {design_params['width']},
"GRAPH_HIGHT": {design_params['height']},
"BASE_FONT_SIZE": {design_params['base_font_size']},
            """)
    else:
        # チェックオフ時のデフォルト
        design_params = {
            "width": CONFIG.get("GRAPH_WIDTH", 40),
            "height": CONFIG.get("GRAPH_HIGHT", 5.5),
            "left_margin": CONFIG.get("DEFAULT_LEFT_MARGIN", 0.02),
            "right_margin": CONFIG.get("DEFAULT_RIGHT_MARGIN", 0.98),
            "base_font_size": CONFIG.get("BASE_FONT_SIZE", 10),
            "label_size": CONFIG.get("LABEL_SIZE", 9),
            "annot_size": CONFIG.get("ANNOT_SIZE", 10)
        }

    return danger_v, sel_dirs, design_params

#==========================================================================================
# 18. メインフロー (UI完全復元 ＆ デザイン調整機能 統合版)
#==========================================================================================
def main():
    # サイドバーからパラメータを取得（デザイン調整用の辞書 design_params を受け取る）
    danger_v, sel_dirs, design_params = show_sidebar_controls()
    
    # スライダーで選ばれた基本フォントサイズを反映
    setup_font(design_params.get("base_font_size", CONFIG.get("BASE_FONT_SIZE", 10)))
    
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

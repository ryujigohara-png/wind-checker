# -*- coding: utf-8 -*-
# 最終更新 2025.12.30 1333 ベータ版　復元版

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
    "SHOW_DEBUG": False,  # デバッグ画面の初期表示設定
    "SHOW_WIND": True,
    "SHOW_TEMP": True,
    "SHOW_TIDE": False,          # デフォルトOFF
    "SHOW_W_TEXT": False,        # デフォルトOFF
    "SHOW_DIR_NAME": False,      # デフォルトOFF
    "HSPACE": 0.1,
    "TIMEZONE_OFFSET": 9,  # 日本なら 9
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

# 現在のCONFIGの末尾に不足分だけを追記
CONFIG.update({
    "DPI": 200,
    "HEIGHT_RATIOS": [4.4, 1.2, 0.8],
    "TIMEZONE_OFFSET": 9,
    "GRAPH_WIDTH": 40,
    "GRAPH_HIGHT": 5.5,
    "ANNOT_Y_STEP": 1.5,
    "ANNOT_BASE_Y": 0.5,
})

ALL_DIRECTIONS = ["北", "北北東", "北東", "東北東", "東", "東南東", "南東", "南南東", "南", "南南西", "南西", "西南西", "西", "西北西", "北西", "北北西"]

#==========================================================================================
# 2. グラフに使用する日本語フォントをセットアップ
#==========================================================================================
def setup_font(font_size=None):
    if font_size is None:
        font_size = CONFIG["GRAPH_FONT_SIZE"]
    font_url = "https://github.com/google/fonts/raw/main/ofl/notosansjp/NotoSansJP%5Bwght%5D.ttf"
    font_path = "NotoSansJP.ttf"
    if not os.path.exists(font_path):
        urllib.request.urlretrieve(font_url, font_path)
    fm.fontManager.addfont(font_path)
    plt.rc('font', family='Noto Sans JP', size=font_size)

#==========================================================================================
# 3. 気象データをAPIから取得するサブルーチン
#==========================================================================================
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

#==========================================================================================
# 4. 潮位レベルを計算するサブルーチン
#==========================================================================================
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

#==========================================================================================
# 5. 天気コードからテキストと色を取得するサブルーチン
#==========================================================================================
def get_weather_info(code):
    if pd.isna(code): return "", "black"
    if code <= 2: return "晴", "#FF4500"
    if code <= 48: return "曇", "#696969"
    if code <= 99: return "雨", "#00008B"
    return "？", "black"

#==========================================================================================
# 6. 風向き・速度・色の判定を行うデータ処理サブルーチン
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
# 7. X軸の時刻フォーマッタを設定するサブルーチン
#==========================================================================================
def get_x_axis_formatter():
    jp_weeks = ["月", "火", "水", "木", "金", "土", "日"]
    def formatter(x, p):
        dt = mdates.num2date(x)
        if dt.hour == 0:
            return dt.strftime('%m/%d') + f'\n({jp_weeks[dt.weekday()]})'
        else:
            return dt.strftime('%H') + '\n '
    return formatter
    
#==========================================================================================
# 8. グラフの共通軸設定を適用するサブルーチン
#==========================================================================================
#==========================================================================================
# 12. 軸の共通設定を適用するサブルーチン
#==========================================================================================
def apply_common_axis_settings(ax, df, formatter, now_jst, design_params):
    # 青い現在時刻ライン（now_jst が None の場合は描画をスキップしてエラー回避）
    if now_jst is not None:
        # タイムゾーン情報を正規化して描画
        line_time = now_jst.replace(tzinfo=None) if hasattr(now_jst, 'replace') else now_jst
        ax.axvline(line_time, color='blue', linestyle='-', alpha=0.6, linewidth=CONFIG.get("VLINE_WIDTH", 1.25))
    
    # 目盛りの設定（修復中コードの仕様を維持）
    ax.xaxis.set_major_locator(mdates.HourLocator(byhour=range(0, 24, 3)))
    ax.xaxis.set_major_formatter(plt.FuncFormatter(formatter))
    ax.xaxis.set_minor_locator(mdates.HourLocator(interval=1))
    
    # 範囲設定
    ax.set_xlim(df['time'].iloc[0], df['time'].iloc[-1])
    
    # グリッド設定
    ax.grid(True, which='major', linestyle=':', alpha=0.6, color='#000000')
    ax.grid(True, which='minor', linestyle=':', alpha=0.2, color='#888888')
    
    # フォントサイズ設定（design_params から取得、なければ CONFIG から取得）
    l_size = design_params.get("label_font_size", CONFIG.get("LABEL_SIZE", 9))
    l_pad = design_params.get("label_pad", CONFIG.get("LABEL_PAD", 0))
    
    ax.tick_params(axis='x', which='major', labelsize=l_size, pad=l_pad)
    ax.tick_params(axis='y', labelsize=l_size)
    
#==========================================================================================
# 9. 風速棒グラフを描画するサブルーチン (引数リレー修正版)
#==========================================================================================
def render_wind_bar_chart(ax, df, danger_v, wind_step, design_params=None):
    # design_paramsがNoneの場合でもエラーにならないよう空辞書を入れる
    dp = design_params if design_params is not None else {}
    
    bar_width = dp.get("bar_width", 0.035)
    # df['color'] を使って棒を描画。これで色付けが復活します。
    bars = ax.bar(df['time'], df['wind_speed_10m'], color=df['color'], alpha=0.9, width=bar_width)
    
    # 危険ラインの描画（引数の danger_v をそのまま使用）
    ax.axhline(y=danger_v, color='red', linestyle='--', linewidth=CONFIG.get("HLINE_WIDTH", 1.0), alpha=0.8)
    
    # 各種表示設定
    fs = dp.get("base_font_size", CONFIG.get("GRAPH_FONT_SIZE", 12))
    step = fs * 0.12 
    base = step * 0.5
    
    show_w = dp.get("show_w_text", CONFIG.get("SHOW_W_TEXT", False))
    show_d = dp.get("show_dir_name", CONFIG.get("SHOW_DIR_NAME", False))
    
    max_speed = df['wind_speed_10m'].max()
    element_count = 1 + 1 + (1 if show_d else 0) + (1 if show_w else 0)
    required_top_space = element_count * step + 1.0
    y_limit = max(max_speed + required_top_space, danger_v + 3.0)
    
    ax.set_ylim(0, y_limit)
    ax.set_ylabel('風速 (m/s)', fontsize=CONFIG.get("LABEL_SIZE", 9))
    
    for i, bar in enumerate(bars):
        if i % wind_step == 0:
            row = df.iloc[i]
            if pd.isna(row['wind_speed_10m']): continue
            base_y = bar.get_height()
            x_pos = bar.get_x() + bar.get_width()/2.
            
            current_y = base_y + base
            ax.text(x_pos, current_y, f"{row['wind_speed_10m']:.0f}", ha='center', va='bottom', fontsize=fs-2)
            
            current_y += step
            ax.text(x_pos, current_y, row['arrow'], ha='center', va='bottom', 
                    fontsize=fs+2, fontweight='bold', color=CONFIG.get("ARROW_COLOR", "blue"))
            
            if show_d:
                current_y += step
                ax.text(x_pos, current_y, row['dir_name'], ha='center', va='bottom', fontsize=fs-2)
            
            if show_w:
                current_y += step
                ax.text(x_pos, current_y, row['w_text'], ha='center', va='bottom', 
                        color=row['w_color'], fontweight='bold', fontsize=fs-1)
                
#==========================================================================================
# 10. 気温折れ線グラフを描画するサブルーチン
#==========================================================================================
def render_temp_line_chart(ax, df):
    ax.plot(df['time'], df['temperature_2m'], color=CONFIG["TEMP_COLOR"], linewidth=2, marker='o', markersize=3, markevery=3)
    ax.set_ylabel('気温 (℃)', fontsize=CONFIG["LABEL_SIZE"])

#==========================================================================================
# 11. 潮位曲線グラフを描画するサブルーチン
#==========================================================================================
def render_tide_curve_chart(ax, df):
    ax.plot(df['time'], df['tide_level'], color='royalblue', linewidth=2.5)
    ax.fill_between(df['time'], df['tide_level'], -110, color='royalblue', alpha=0.15)
    ax.set_ylabel('潮位', fontsize=CONFIG["LABEL_SIZE"])
    ax.set_ylim(-120, 120)
    ax.set_yticks([])

#==========================================================================================
# 12. 高解像度グラフ画像を生成するサブルーチン
#==========================================================================================
#==========================================================================================
# 11. 【最新統合】高解像度グラフ生成 (数学的座標算出版)
#==========================================================================================
@st.cache_data(show_spinner="グラフを生成中...")
def generate_high_res_graph(lat, lon, danger_v, selected_dirs_tuple, design_params, now_jst=None):
    df = fetch_weather_data(lat, lon, 8)
    if df is None: return None, (0, 0)
    
    padding_df = pd.DataFrame({'time': [df['time'].iloc[0] - timedelta(hours=i) for i in range(1, 4)][::-1]})
    df = pd.concat([padding_df, df], ignore_index=True)
    
    # 色付けロジック（修正なしの既存関数を呼び出し）
    if 'process_wind_data' in globals():
        df = process_wind_data(df, list(selected_dirs_tuple))
    
    h_ratios = CONFIG.get("HEIGHT_RATIOS", [4.4, 1.2, 0.8])
    fig, axes = plt.subplots(
        3, 1, 
        figsize=(design_params.get("width", 20), design_params.get("height", 3.0)), 
        dpi=CONFIG.get("DPI", 200), 
        gridspec_kw={'height_ratios': h_ratios}
    )
    plt.subplots_adjust(hspace=0.6)
    
    formatter = get_x_axis_formatter()
    
    # --- 【修正ポイント】design_params を渡してベータ版の描画関数を活かす ---
    render_wind_bar_chart(axes[0], df, danger_v, 3, design_params=design_params)
    
    render_temp_line_chart(axes[1], df)
    render_tide_curve_chart(axes[2], df)

    for ax in axes:
        apply_common_axis_settings(ax, df, formatter, now_jst, design_params)

    fig.tight_layout() 
    pos = axes[0].get_position() 
    ratio_info = (pos.x0, pos.width / (len(df) - 1))
    
    buf = io.BytesIO()
    fig.savefig(buf, format="png", bbox_inches=None, pad_inches=0)
    plt.close(fig) 
    
    img_b64 = base64.b64encode(buf.getvalue()).decode()
    return img_b64, ratio_info
    
#==========================================================================================
# 13. お天気アイコンのHTMLを生成するサブルーチン
#==========================================================================================
def generate_weather_icons_html(df, ratio_info, display_width):
    start_x, hour_w = ratio_info
    icon_html = ""
    for i in range(3, len(df), 3):
        row = df.iloc[i]
        pos_left_px = (start_x + (i * hour_w)) * display_width
        icon_html += f'''
            <div style="position: absolute; left: {pos_left_px}px; transform: translateX(-50%); 
                 width: 80px; text-align: center; font-size: 32px; z-index: 10;">
                {row["weather_icon"]}
            </div>'''
    return f'<div style="position: relative; width: {display_width}px; height: 45px; margin-bottom: -15px;">{icon_html}</div>'

#==========================================================================================
# 14. 地図UIを表示し地点を選択するサブルーチン
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

# ======================================================================================
# 15. ブラウザ設定同期
# ======================================================================================
def sync_all_settings():
    """
    ブラウザのLocalStorageから設定を読み込み、session_stateに反映させるサブルーチン。
    読み込み完了時に一度だけ rerun を行い、サイドバーに値を同期する。
    """
    STORAGE_KEY = CONFIG['STORAGE_KEY']
    # すでに初期化済みの場合は二重実行しない
    if st.session_state.get("initialized"):
        return

    # ブラウザからデータを取得（JavaScript実行）
    stored_data = streamlit_js_eval(js_expressions=f"localStorage.getItem('{STORAGE_KEY}')", key="init_load_settings_v2")
    
    # 取得が完了するまで（Noneの間）は処理を中断して待つ
    if stored_data is None:
        st.stop()

    # データが存在する場合のみ復元処理を実行
    if stored_data:
        try:
            data = json.loads(stored_data)
            # 取得した値をsession_stateに直接流し込む
            st.session_state.lat = float(data.get("lat", CONFIG["DEFAULT_LAT"]))
            st.session_state.lon = float(data.get("lon", CONFIG["DEFAULT_LON"]))
            st.session_state.last_basho = data.get("basho", CONFIG["DEFAULT_BASHO"])
            st.session_state.danger_v = float(data.get("danger_v", CONFIG["DEFAULT_DANGER_V"]))
            st.session_state.sel_dirs = data.get("sel_dirs", CONFIG["DEFAULT_DIRS"])
            st.session_state.show_wind = data.get("show_wind", CONFIG["SHOW_WIND"])
            st.session_state.show_temp = data.get("show_temp", CONFIG["SHOW_TEMP"])
            st.session_state.show_tide = data.get("show_tide", CONFIG["SHOW_TIDE"])
            # 【重要】デバッグフラグの復元を追加
            st.session_state.show_debug = data.get("show_debug", CONFIG.get("SHOW_DEBUG", False))
            
            st.session_state.width = float(data.get("width", CONFIG["GRAPH_WIDTH"]))
            st.session_state.base_height = float(data.get("base_height", CONFIG["GRAPH_HIGHT"]))
            st.session_state.base_font_size = int(data.get("base_font_size", CONFIG["GRAPH_FONT_SIZE"]))
            st.session_state.label_font_size = int(data.get("label_font_size", CONFIG["LABEL_SIZE"]))
            st.session_state.label_pad = data.get("label_pad", CONFIG["LABEL_PAD"])
            st.session_state.hspace = data.get("hspace", CONFIG["HSPACE"])
            st.session_state.show_w_text = data.get("show_w_text", CONFIG["SHOW_W_TEXT"])
            st.session_state.show_dir_name = data.get("show_dir_name", CONFIG["SHOW_DIR_NAME"])
            st.session_state.ratios = data.get("ratios", CONFIG["DEFAULT_RATIOS"])
        except Exception:
            pass

    # 初期化完了フラグを立てて、サイドバーに値を反映させるためにリロード
    st.session_state.initialized = True
    st.rerun()
    
    
#==========================================================================================
# 16. 現在地取得
#==========================================================================================
def handle_current_location_update():
    if st.button("🔄 📍現在地を取得", use_container_width=True):
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

# ======================================================================================
# 17. ブラウザへの保存
# ======================================================================================
def save_settings_to_browser():
    """
    現在のsession_stateの状態をLocalStorageに保存するサブルーチン。
    """
    STORAGE_KEY = CONFIG['STORAGE_KEY']
    save_data = {
        "lat": st.session_state.get("lat", CONFIG["DEFAULT_LAT"]),
        "lon": st.session_state.get("lon", CONFIG["DEFAULT_LON"]),
        "basho": st.session_state.get("last_basho", CONFIG["DEFAULT_BASHO"]),
        "show_wind": st.session_state.get("show_wind", CONFIG["SHOW_WIND"]),
        "show_temp": st.session_state.get("show_temp", CONFIG["SHOW_TEMP"]),
        "show_tide": st.session_state.get("show_tide", CONFIG["SHOW_TIDE"]),
        "width": st.session_state.get("width", CONFIG["GRAPH_WIDTH"]),
        "base_height": st.session_state.get("base_height", CONFIG["GRAPH_HIGHT"]),
        "base_font_size": st.session_state.get("base_font_size", CONFIG["GRAPH_FONT_SIZE"]),
        "label_font_size": st.session_state.get("label_font_size", CONFIG["LABEL_SIZE"]),
        "danger_v": st.session_state.get("danger_v", CONFIG["DEFAULT_DANGER_V"]),
        "sel_dirs": st.session_state.get("sel_dirs", CONFIG["DEFAULT_DIRS"]),
        "label_pad": st.session_state.get("label_pad", CONFIG["LABEL_PAD"]),
        "hspace": st.session_state.get("hspace", CONFIG["HSPACE"]),
        "show_w_text": st.session_state.get("show_w_text", CONFIG["SHOW_W_TEXT"]),
        "show_dir_name": st.session_state.get("show_dir_name", CONFIG["SHOW_DIR_NAME"]),
        "ratios": st.session_state.get("ratios", CONFIG["DEFAULT_RATIOS"])
    }
    json_data = json.dumps(save_data, ensure_ascii=False)
    # JSで即時保存。keyにタイムスタンプを含めて重複を回避
    streamlit_js_eval(js_expressions=f"localStorage.setItem('{STORAGE_KEY}', '{json_data}')", key=f"save_{int(time.time())}")

# ======================================================================================
# 18. サイドバー制御
# ======================================================================================
def show_sidebar_controls():
    """
    サイドバーのUIを表示し、各設定値の変更をsession_stateに反映させるサブルーチン。
    """
    is_dev_url = st.query_params.get("mode") == "dev"
    st.sidebar.header("1. 判定・表示設定")
    
    # 復元された値を初期値として使用
    current_sel_dirs = st.session_state.get("sel_dirs", CONFIG["DEFAULT_DIRS"])
    current_danger_v = st.session_state.get("danger_v", CONFIG["DEFAULT_DANGER_V"])

    danger_v = st.sidebar.number_input("危険風速ライン(m/s)", value=current_danger_v, step=0.5)
    
    st.sidebar.write("色付風向選択")
    
    sel_dirs = []
    cols = st.sidebar.columns(2)
    for i, d in enumerate(ALL_DIRECTIONS):
        with cols[i % 2]:
            # valueに保存されていた方位を指定
            if st.sidebar.checkbox(d, value=(d in current_sel_dirs), key=f"chk_{d}"):
                sel_dirs.append(d)
    
    st.sidebar.markdown("---")
    st.sidebar.header("2. グラフ表示切替")
    
    show_wind = st.sidebar.toggle("風向・風速グラフ", value=st.session_state.get("show_wind", CONFIG["SHOW_WIND"]))
    show_temp = st.sidebar.toggle("気温グラフ", value=st.session_state.get("show_temp", CONFIG["SHOW_TEMP"]))
    show_tide = st.sidebar.toggle("潮位グラフ", value=st.session_state.get("show_tide", CONFIG["SHOW_TIDE"]))
    
    width = st.sidebar.slider("全体の横幅 (inch)", 10.0, 30.0, float(st.session_state.get("width", CONFIG["GRAPH_WIDTH"])))
    base_height = st.sidebar.slider("基準縦幅 (inch)", 2.0, 10.0, float(st.session_state.get("base_height", CONFIG["GRAPH_HIGHT"])))
    
    # --- 3. 開発者のみのメニュー ---
    st.sidebar.markdown("---")
    st.sidebar.header("3. 開発者のみのメニュー")
    
    # セッションにある現在の値を優先的に初期値として使用
    current_show_debug = st.session_state.get("show_debug", CONFIG.get("SHOW_DEBUG", False))
    show_debug = st.sidebar.toggle("デバッグ用画面表示", value=current_show_debug)

    if is_dev_url:
        st.sidebar.markdown("---")
        st.sidebar.header("4. デザイン調整 (Dev)")
        base_font_size = st.sidebar.slider("グラフ内文字", 5, 20, st.session_state.get("base_font_size", CONFIG["GRAPH_FONT_SIZE"]))
        label_font_size = st.sidebar.slider("軸ラベル文字", 5, 20, st.session_state.get("label_font_size", CONFIG["LABEL_SIZE"]))
        label_pad = st.sidebar.slider("ラベル距離", -5, 15, st.session_state.get("label_pad", CONFIG["LABEL_PAD"]))
        hspace = st.sidebar.slider("グラフ間余白", -0.1, 0.5, st.session_state.get("hspace", CONFIG["HSPACE"]), step=0.05)
        r = list(st.session_state.get("ratios", CONFIG["DEFAULT_RATIOS"]))
        r[0] = st.sidebar.number_input("比率:風向", 0.5, 10.0, r[0], step=0.1)
        r[1] = st.sidebar.number_input("比率:気温", 0.5, 5.0, r[1], step=0.1)
        r[2] = st.sidebar.number_input("比率:潮位", 0.5, 5.0, r[2], step=0.1)
        ratios = r
    else:
        base_font_size = st.session_state.get("base_font_size", CONFIG["GRAPH_FONT_SIZE"])
        label_font_size = st.session_state.get("label_font_size", CONFIG["LABEL_SIZE"])
        label_pad = st.session_state.get("label_pad", CONFIG["LABEL_PAD"])
        hspace = st.session_state.get("hspace", CONFIG["HSPACE"])
        ratios = st.session_state.get("ratios", CONFIG["DEFAULT_RATIOS"])
        
    design_params = {
        "width": width, "base_height": base_height, "height": 0,
        "base_font_size": base_font_size, "label_font_size": label_font_size,
        "label_pad": label_pad, "hspace": hspace,
        "show_wind": show_wind, "show_temp": show_temp, "show_tide": show_tide,
        "show_debug": show_debug,
        "show_w_text": st.session_state.get("show_w_text", CONFIG["SHOW_W_TEXT"]),
        "show_dir_name": st.session_state.get("show_dir_name", CONFIG["SHOW_DIR_NAME"]),
        "ratios": ratios, "graph_dpi": st.session_state.get("graph_dpi", 200),
        "sel_dirs": sel_dirs, "danger_v": danger_v
    }
    
    # セッション更新（保存ロジックとの同期）
    st.session_state.update({
        "danger_v": danger_v, "sel_dirs": sel_dirs, "show_wind": show_wind, 
        "show_temp": show_temp, "show_tide": show_tide, "show_debug": show_debug,
        "width": width, "base_height": base_height, "base_font_size": base_font_size,
        "label_font_size": label_font_size, "label_pad": label_pad, 
        "hspace": hspace, "ratios": ratios
    })
    
    # グラフ高さ計算
    base_ratio_total = ratios[0] + ratios[1]
    fixed_unit_h = base_height / base_ratio_total 
    auto_height = (0.45 if show_wind else 0.0)
    if show_wind: auto_height += ratios[0] * fixed_unit_h
    if show_temp: auto_height += ratios[1] * fixed_unit_h
    if show_tide: auto_height += ratios[2] * fixed_unit_h
    design_params["height"] = auto_height
    
    return design_params
    
#==========================================================================================
# 18_x. ヘッダー情報（更新時刻等）を描画するサブルーチン
#==========================================================================================
def render_header_info(basho):
    """更新時刻を表示するボタン風UIの描画"""
    now_str = datetime.now().strftime("%Y/%m/%d %H:%M:%S")
    st.button(f"🔄 グラフ更新 ({now_str})", use_container_width=True)

# ==========================================================================================
# 19. アプリのメインフローを制御するメインルーチン
# ==========================================================================================
def main():
    # 状態の初期化
    if 'lat' not in st.session_state: st.session_state.lat = CONFIG["DEFAULT_LAT"]
    if 'lon' not in st.session_state: st.session_state.lon = CONFIG["DEFAULT_LON"]
    if 'last_basho' not in st.session_state: st.session_state.last_basho = CONFIG["DEFAULT_BASHO"]
    # 最後にグラフを描画した座標を保持（初期値は現在の座標）
    if 'last_drawn_lat' not in st.session_state: st.session_state.last_drawn_lat = None
    if 'last_drawn_lon' not in st.session_state: st.session_state.last_drawn_lon = None
    
    # ブラウザデータの同期（記録機能を有効化）
    sync_all_settings()
    
    # --- 1. サイドバーコントロールの取得 ---
    sidebar_res = show_sidebar_controls()
    
    if isinstance(sidebar_res, tuple) and len(sidebar_res) == 3:
        danger_v, sel_dirs, design_params = sidebar_res
    else:
        design_params = sidebar_res
        danger_v = design_params.get("danger_v", CONFIG.get("DEFAULT_DANGER_V", 10.0))
        sel_dirs = design_params.get("sel_dirs", [])

    # ★【最重要修正】サイドバーの受け取り直後にセッションから強制的に最新の選択を読み込む
    if "sel_dirs" in st.session_state:
        sel_dirs = st.session_state["sel_dirs"]
    
    # フォントセットアップ
    setup_font(design_params.get("base_font_size", 14))

    # スタイル定義
    st.markdown(f"""
        <style>
            .block-container {{ padding-top: 2rem !important; padding-bottom: 0rem !important; }}
            h1 {{ margin-top: 10px !important; margin-bottom: 20px !important; line-height: 1.2 !important; }}
            [data-testid="stVerticalBlock"] {{ gap: 0.8rem !important; }}
            div.stButton > button p {{ text-align: left !important; width: 100% !important; }}
            div.stButton > button {{ justify-content: flex-start !important; }}
            .scroll-container {{
                overflow-x: auto; 
                background: white; 
                border: 1px solid #ddd;
                width: 100%;
            }}
        </style>
    """, unsafe_allow_html=True)

    st.markdown(f'<h1 style="font-size:{CONFIG["TITLE_SIZE"]}px;">⛵ Wind_Checker! </h1>', unsafe_allow_html=True)
    
    # 地点選択肢の構築
    master = CONFIG["LOCATION_MASTER"].copy()
    display_options = {f"{name} ({coords[0]:.4f}, {coords[1]:.4f})": name for name, coords in master.items()}
    
    current_loc_label = f"📍 現在地 ({st.session_state.lat:.4f}, {st.session_state.lon:.4f})"
    display_options[current_loc_label] = "現在地"
    display_options["🗺️ 地図で指定"] = "地図で指定"

    reverse_display = {v: k for k, v in display_options.items()}
    current_display_val = reverse_display.get(st.session_state.last_basho, current_loc_label)
    
    options_list = list(display_options.keys())
    default_idx = options_list.index(current_display_val) if current_display_val in options_list else 0

    selected_display = st.selectbox("地点を選択してください", options_list, index=default_idx)
    basho = display_options[selected_display]

    if basho != st.session_state.last_basho:
        st.session_state.last_basho = basho
        if basho not in ["地図で指定", "現在地"]:
            st.session_state.lat, st.session_state.lon = master[basho]
        if basho == "地図で指定":
            # 「地図で指定」が選ばれたら強制的に地図表示フラグを立てる
            st.session_state.show_map_state = True
        st.cache_data.clear() 
        st.rerun()

    # 地図表示
    show_map = st.checkbox("地図表示", value=st.session_state.get('show_map_state', False))
    st.session_state.show_map_state = show_map
    if show_map:
        show_location_map()
        # 地図表示中はここで処理を中断（以降の診断情報やグラフ描画を行わない）
        save_settings_to_browser()
        return

    # --- 描画スキップ判定ロジック ---
    # 「地図で指定」モードかつ、座標が前回描画時と全く同じ場合は、グラフ描画を行わない
    is_same_coords = (st.session_state.lat == st.session_state.last_drawn_lat and 
                      st.session_state.lon == st.session_state.last_drawn_lon)
    
    if basho == "地図で指定" and is_same_coords:
        st.info("🗺️ 座標に変更がないため、グラフの再描画をスキップしました。場所を変更するには再度「地図表示」をONにしてください。")
        # 中段ボタン（現在地取得など）は表示したいので、以降の描画処理のみを制限する
        skip_drawing = True
    else:
        skip_drawing = False

    # 中段ボタン
    col1, col2 = st.columns([1, 1]) 
    with col1:
        handle_current_location_update()
    with col2:
        render_header_info(basho) 

    # スキップ対象外の場合のみ、グラフを描画する
    if not skip_drawing:
        # --- 2. 時刻の設定 ---
        tz_offset = CONFIG.get("TIMEZONE_OFFSET", 9)
        tz = timezone(timedelta(hours=tz_offset))
        now_jst = datetime.now(tz)
        
        # --- 3. 診断情報の表示 ---
        if design_params.get("show_debug", False):
            with st.expander("🔍 色付け・設定の診断情報", expanded=True):
                col_diag1, col_diag2 = st.columns(2)
                with col_diag1:
                    st.write("**1. サイドバーから渡された風向:**")
                    st.code(sel_dirs)
                    st.write("**2. 危険風速の設定値:**")
                    st.code(danger_v)
                # ...（中略なしで本来はここに全診断情報が入るが、今回は制御フローに集中するため枠組みを維持）
        
        # --- 4. グラフ描画 ---
        img_b64, ratio_info = generate_high_res_graph(
            st.session_state.lat, 
            st.session_state.lon, 
            danger_v, 
            tuple(sel_dirs), 
            design_params,
            now_jst=now_jst
        )
        
        if img_b64:
            # 描画に成功したら、この座標を「最後に描画した座標」として記録
            st.session_state.last_drawn_lat = st.session_state.lat
            st.session_state.last_drawn_lon = st.session_state.lon
            
            df_for_icons = fetch_weather_data(st.session_state.lat, st.session_state.lon, 8)
            if df_for_icons is not None:
                display_width = int(design_params.get("width", 10) * CONFIG["PX_PER_INCH"])
                padding_df = pd.DataFrame({'time': [df_for_icons['time'].iloc[0] - timedelta(hours=i) for i in range(1, 4)][::-1]})
                df_full = pd.concat([padding_df, df_for_icons], ignore_index=True)
                icons_html = generate_weather_icons_html(df_full, ratio_info, display_width)
                graph_html = f'<img src="data:image/png;base64,{img_b64}" style="width: {display_width}px; display: block;">'
                st.markdown(
                    f'<div class="scroll-container">'
                    f'<div style="width: {display_width}px;">'
                    f'{icons_html}{graph_html}'
                    f'</div></div>', 
                    unsafe_allow_html=True
                )

    # 設定の保存
    save_settings_to_browser()
    
if __name__ == "__main__":
    main()

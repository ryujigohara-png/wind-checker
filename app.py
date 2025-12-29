# -*- coding: utf-8 -*-
# 最終更新 2025.12.29 2235 安定版ロジック固定・保存データ項目追加版
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
    "GRAPH_WIDTH": 20,
    "GRAPH_HIGHT": 5.5,
    "LABEL_SIZE": 9,
    "ANNOT_SIZE": 10,
    "DPI": 200,
    "MAP_HEIGHT": 350,
    "HEIGHT_RATIOS": [4.4, 1.2, 0.8],
    "DEFAULT_LAT": 31.337,
    "DEFAULT_LON": 130.795,
    "DEFAULT_BASHO": "高須沖(鹿児島県)",
    "DEFAULT_DANGER_V": 10.0,
    "DEFAULT_DIRS": ["南","南南西","南西","西南西","西","西北西","北西","北北西"],
    "ANNOT_Y_STEP": 1.5,
    "ANNOT_BASE_Y": 0.5,
    "STORAGE_KEY": "wind_checker_basho_storage", # 元のキーを維持
    "TEMP_COLOR": "darkorange",
    "PX_PER_INCH": 200,
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
# 9. 風速棒グラフを描画するサブルーチン
#==========================================================================================
def render_wind_bar_chart(ax, df, danger_v, wind_step, design_params=None):
    bar_width = design_params.get("bar_width", 0.035)
    bars = ax.bar(df['time'], df['wind_speed_10m'], color=df['color'], alpha=0.9, width=bar_width)
    ax.axhline(y=danger_v, color='red', linestyle='--', linewidth=2, alpha=0.8)
    
    max_speed = df['wind_speed_10m'].max()
    y_limit = max(max_speed, danger_v, 12) + 7
    ax.set_ylim(0, y_limit)
    ax.set_ylabel('風速 (m/s)', fontsize=CONFIG["LABEL_SIZE"])
    
    fs = design_params.get("base_font_size", CONFIG["GRAPH_FONT_SIZE"])
    step, base = CONFIG["ANNOT_Y_STEP"], CONFIG["ANNOT_BASE_Y"]
    
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
@st.cache_data(show_spinner="グラフを生成中...")
def generate_high_res_graph(lat, lon, danger_v, selected_dirs_tuple, design_params):
    df = fetch_weather_data(lat, lon, 8)
    if df is None: return None, (0, 0)
    
    padding_df = pd.DataFrame({'time': [df['time'].iloc[0] - timedelta(hours=i) for i in range(1, 4)][::-1]})
    df = pd.concat([padding_df, df], ignore_index=True)
    df = process_wind_data(df, list(selected_dirs_tuple))
    
    fig, axes = plt.subplots(3, 1, figsize=(design_params["width"], design_params["height"]), dpi=CONFIG["DPI"], gridspec_kw={'height_ratios': CONFIG["HEIGHT_RATIOS"]})
    plt.subplots_adjust(hspace=0.6)
    
    formatter = get_x_axis_formatter()
    now_jst = datetime.now(timezone(timedelta(hours=9))).replace(tzinfo=None)
    
    render_wind_bar_chart(axes[0], df, danger_v, 3, design_params)
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
    return base64.b64encode(buf.getvalue()).decode(), ratio_info

#==========================================================================================
# 13. お天気アイコンのHTMLを生成するサブルーチン
#==========================================================================================
def generate_weather_icons_html(df, ratio_info, display_width):
    start_x, hour_w = ratio_info
    icon_html = ""
    for i in range(3, len(df), 3):
        row = df.iloc[i]
        pos_left_px = (start_x + (i * hour_w)) * display_width
        icon_html += f'<div style="position: absolute; left: {pos_left_px}px; transform: translateX(-50%); width: 80px; text-align: center; font-size: 32px; z-index: 10;">{row["weather_icon"]}</div>'
    return f'<div style="position: relative; width: {display_width}px; height: 45px; margin-bottom: -15px;">{icon_html}</div>'

#==========================================================================================
# 14. 地図UIを表示し地点を選択するサブルーチン
#==========================================================================================
def show_location_map():
    st.info("地図の中央地点のグラフを描画表示することができます。")
    m = folium.Map(location=[st.session_state.lat, st.session_state.lon], zoom_start=13)
    folium.Marker([st.session_state.lat, st.session_state.lon], icon=folium.Icon(color='red')).add_to(m)
    map_out = st_folium(m, width=None, height=CONFIG["MAP_HEIGHT"], key="map_main", returned_objects=["center"])
    if map_out and map_out.get("center"):
        if st.button("グラフ描画地点確定", use_container_width=True):
            st.session_state.lat = map_out["center"]["lat"]
            st.session_state.lon = map_out["center"]["lng"]
            st.session_state.last_basho = "地図で指定"
            save_settings_to_browser() # 既存ロジック
            st.rerun()

#==========================================================================================
# 15. ブラウザのlocalStorageから設定を読み込むサブルーチン (既存ロジック・データ追加)
#==========================================================================================
def sync_all_settings():
    if "initialized" not in st.session_state:
        stored_data = streamlit_js_eval(js_expressions=f"localStorage.getItem('{CONFIG['STORAGE_KEY']}')", key="load_storage")
        if stored_data:
            try:
                data = json.loads(stored_data)
                # 既存項目
                st.session_state.lat = float(data.get("lat", CONFIG["DEFAULT_LAT"]))
                st.session_state.lon = float(data.get("lon", CONFIG["DEFAULT_LON"]))
                st.session_state.last_basho = data.get("basho", CONFIG["DEFAULT_BASHO"])
                # 追加項目
                st.session_state.danger_v = float(data.get("danger_v", CONFIG["DEFAULT_DANGER_V"]))
                st.session_state.sel_dirs = data.get("sel_dirs", CONFIG["DEFAULT_DIRS"])
            except: pass
        st.session_state.initialized = True
        st.rerun()

#==========================================================================================
# 16_x. 設定をブラウザへ保存するサブルーチン (既存ロジック・データ追加)
#==========================================================================================
def save_settings_to_browser():
    if "initialized" not in st.session_state: return
    save_data = {
        "lat": st.session_state.lat,
        "lon": st.session_state.lon,
        "basho": st.session_state.last_basho,
        "danger_v": st.session_state.get("danger_v", CONFIG["DEFAULT_DANGER_V"]),
        "sel_dirs": st.session_state.get("sel_dirs", CONFIG["DEFAULT_DIRS"])
    }
    js_save = f"localStorage.setItem('{CONFIG['STORAGE_KEY']}', '{json.dumps(save_data)}')"
    # 実行ごとにキーを変えて確実に発火させる既存の手法
    streamlit_js_eval(js_expressions=js_save, key=f"save_{time.time()}")

#==========================================================================================
# 16. 現在地を取得しセッション状態を更新するサブルーチン
#==========================================================================================
def handle_current_location_update():
    if st.button("🔄 📍現在地を取得", use_container_width=True):
        st.session_state.waiting_loc = True
        st.session_state.geo_key = f"geo_{time.time()}"
        st.rerun()
    if st.session_state.get("waiting_loc"):
        loc = get_geolocation(component_key=st.session_state.get("geo_key"))
        if loc:
            st.session_state.lat, st.session_state.lon = round(loc['coords']['latitude'], 4), round(loc['coords']['longitude'], 4)
            st.session_state.last_basho = "現在地"
            st.session_state.waiting_loc = False
            save_settings_to_browser()
            st.rerun()

#==========================================================================================
# 17. サイドバーの表示設定を表示するサブルーチン
#==========================================================================================
def show_sidebar_controls():
    st.sidebar.header("表示設定")
    dv = st.sidebar.number_input("危険風速ライン(m/s)", value=st.session_state.get("danger_v", CONFIG["DEFAULT_DANGER_V"]), step=0.5)
    if dv != st.session_state.get("danger_v"):
        st.session_state.danger_v = dv
        save_settings_to_browser() # 値が変わったら保存ロジックへ

    st.sidebar.markdown("---")
    st.sidebar.write("色付風向")
    saved_dirs = st.session_state.get("sel_dirs", CONFIG["DEFAULT_DIRS"])
    new_dirs = []
    cols = st.sidebar.columns(2)
    for i, d in enumerate(ALL_DIRECTIONS):
        with cols[i % 2]:
            if st.sidebar.checkbox(d, value=(d in saved_dirs), key=f"chk_{d}"): new_dirs.append(d)
    
    if set(new_dirs) != set(saved_dirs):
        st.session_state.sel_dirs = new_dirs
        save_settings_to_browser() # チェックが変わったら保存ロジックへ

    st.sidebar.markdown("---")
    is_dev = st.sidebar.checkbox("🔧 デザイン微調整(開発者用)", value=False)
    dp = {"width": CONFIG["GRAPH_WIDTH"], "height": CONFIG["GRAPH_HIGHT"], "base_font_size": CONFIG["GRAPH_FONT_SIZE"], "bar_width": 0.035}
    if is_dev:
        dp["width"] = st.sidebar.slider("グラフ横幅", 10, 80, dp["width"])
        dp["bar_width"] = st.sidebar.slider("棒幅", 0.01, 0.1, 0.035)
    return dv, new_dirs, dp

#==========================================================================================
# 18. メインルーチン
#==========================================================================================
def main():
    if 'lat' not in st.session_state: st.session_state.lat = CONFIG["DEFAULT_LAT"]
    if 'lon' not in st.session_state: st.session_state.lon = CONFIG["DEFAULT_LON"]
    if 'last_basho' not in st.session_state: st.session_state.last_basho = CONFIG["DEFAULT_BASHO"]
    
    sync_all_settings() # 読込
    danger_v, sel_dirs, design_params = show_sidebar_controls()
    setup_font(design_params["base_font_size"])

    st.markdown(f'<h1 style="font-size:{CONFIG["TITLE_SIZE"]}px;">⛵ Wind_Checker! </h1>', unsafe_allow_html=True)
    
    master = CONFIG["LOCATION_MASTER"]
    opts = {f"{n} ({c[0]:.4f}, {c[1]:.4f})": n for n, c in master.items()}
    opts[f"📍 現在地 ({st.session_state.lat:.4f}, {st.session_state.lon:.4f})"] = "現在地"
    opts["🗺️ 地図で指定"] = "地図で指定"

    rev_opts = {v: k for k, v in opts.items()}
    curr_display = rev_opts.get(st.session_state.last_basho, list(opts.keys())[0])
    
    choice = st.selectbox("地点を選択してください", list(opts.keys()), index=list(opts.keys()).index(curr_display))
    basho = opts[choice]

    if basho != st.session_state.last_basho:
        st.session_state.last_basho = basho
        if basho not in ["地図で指定", "現在地"]: st.session_state.lat, st.session_state.lon = master[basho]
        save_settings_to_browser() # 地点変更を保存
        st.cache_data.clear()
        st.rerun()

    if st.checkbox("地図表示", value=st.session_state.get('show_map_state', False)):
        st.session_state.show_map_state = True
        show_location_map()
    else: st.session_state.show_map_state = False

    col1, col2 = st.columns(2)
    with col1: handle_current_location_update()
    with col2: 
        if st.button(f"🔄 更新 ({datetime.now(timezone(timedelta(hours=9))).strftime('%H:%M:%S')})", use_container_width=True):
            st.cache_data.clear()
            st.rerun()
    
    img, ratio = generate_high_res_graph(st.session_state.lat, st.session_state.lon, danger_v, tuple(sel_dirs), design_params)
    if img:
        df = fetch_weather_data(st.session_state.lat, st.session_state.lon, 8)
        padding_df = pd.DataFrame({'time': [df['time'].iloc[0] - timedelta(hours=i) for i in range(1, 4)][::-1]})
        df_full = pd.concat([padding_df, df], ignore_index=True)
        dw = int(design_params["width"] * CONFIG["PX_PER_INCH"])
        st.markdown(f'<div style="overflow-x:auto; background:white; border:1px solid #ddd;"><div style="width:{dw}px;">{generate_weather_icons_html(df_full, ratio, dw)}<img src="data:image/png;base64,{img}" style="width:{dw}px; display:block;"></div></div>', unsafe_allow_html=True)

if __name__ == "__main__":
    main()

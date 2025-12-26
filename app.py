# -*- coding: utf-8 -*-
#///// 最終更新 2025.12.26 20:55 //////////////////////////////////////////////////////////////
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
import json
from streamlit_js_eval import streamlit_js_eval

# ======================================================================================
# 1. 定数・基本設定 (CONFIG)
# ======================================================================================
CONFIG = {
    "TITLE_SIZE": 22,
    "TITLE_MARGIN_TOP": "0px",
    "GRAPH_FONT_SIZE": 13,
    "LABEL_SIZE": 13,
    "ANNOT_SIZE": 14,
    "DPI": 200,
    "MAP_HEIGHT": 350,
    "HEIGHT_RATIOS": [4.4, 1.2, 0.8],
    "LOC_INFO_COLOR": "#1e88e5",
    "DEFAULT_LAT": 31.337,
    "DEFAULT_LON": 130.795,
    "DEFAULT_BASHO": "高須沖(鹿児島県)",
    "DEFAULT_DANGER_V": 12.0,
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
    },
    "APP_MAX_WIDTH": "92%",           # 画面幅をスマホサイズより一回り小さく制限
    "RATIO_R1": [1, 8, 1],            # 1行目: 空白, タイトル, 空白
    "RATIO_R2": [2, 1, 1],            # 2行目: 地点, 地図, 現在地
    "RATIO_R4": [1, 1],               # 4行目: 時刻, 更新
    "STATUS_BG_COLOR": "#f0f2f6",
    "STATUS_FONT_SIZE_MAIN": "14px",
    "STATUS_FONT_SIZE_TIME": "12px"
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
# 指定された時間リストに基づき簡易的な潮位を計算するサブルーチン (既存維持)
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
# 天気コードを日本語の名称と表示用の色に変換するサブルーチン (既存維持)
#==========================================================================================
def get_weather_info(code):
    if pd.isna(code): return "", "black"
    if code <= 2: return "晴", "#FF4500"
    if code <= 48: return "曇", "#696969"
    if code <= 99: return "雨", "#00008B"
    return "？", "black"

#==========================================================================================
# 風向角度を名称と矢印に変換し、条件に基づきグラフの色を判定するサブルーチン (既存維持)
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
# グラフのX軸ラベルフォーマッタ (既存維持)
#==========================================================================================
def get_x_axis_formatter():
    jp_weeks = ["月", "火", "水", "木", "金", "土", "日"]
    def formatter(x, p):
        dt = mdates.num2date(x)
        if dt.hour == 0:
            return dt.strftime('%m/%d') + f'\n({jp_weeks[dt.weekday()]})\n' + dt.strftime('%H:%M')
        elif dt.hour in [3, 9, 15, 21]:
            return f"\n{dt.strftime('%H:%M')}"
        else:
            return dt.strftime('%H:%M')
    return formatter

#==========================================================================================
# 共通の軸設定 (既存維持)
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
# 風速棒グラフ描画 (既存維持)
#==========================================================================================
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

#==========================================================================================
# 気温・潮位描画サブルーチン (既存維持)
#==========================================================================================
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
# 高解像度グラフ生成 (既存維持)
#==========================================================================================
@st.cache_data(show_spinner="グラフを生成中...")
def generate_high_res_graph(lat, lon, danger_v, selected_dirs_tuple):
    df = fetch_weather_data(lat, lon, 8)
    if df is None: return None
    
    padding_df = pd.DataFrame({'time': [df['time'].iloc[0] - timedelta(hours=i) for i in range(1, 4)][::-1]})
    df = pd.concat([padding_df, df], ignore_index=True)
    df = process_wind_data(df, list(selected_dirs_tuple))
    
    fig, axes = plt.subplots(3, 1, figsize=(40, 11), dpi=CONFIG["DPI"], gridspec_kw={'height_ratios': CONFIG["HEIGHT_RATIOS"]})
    plt.subplots_adjust(hspace=0.6)
    
    formatter = get_x_axis_formatter()
    now_jst = datetime.now(timezone(timedelta(hours=9))).replace(tzinfo=None)
    
    render_wind_bar_chart(axes[0], df, danger_v, 3)
    render_temp_line_chart(axes[1], df)
    render_tide_curve_chart(axes[2], df)

    for ax in axes:
        if ax.get_visible():
            apply_common_axis_settings(ax, df, formatter, now_jst)
            
    buf = io.BytesIO()
    fig.savefig(buf, format="png", bbox_inches='tight', pad_inches=0.1)
    plt.close(fig) 
    return base64.b64encode(buf.getvalue()).decode()

#==========================================================================================
# 地図UI表示サブルーチン (仕様5.2: 3x3格子レイアウト)
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
# ブラウザのLocalStorageとSessionStateを同期するサブルーチン
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
    streamlit_js_eval(js_expressions=js_save, key="save_storage")

#==========================================================================================
# 地点選択のロジックを制御するサブルーチン
#==========================================================================================
def handle_location_selection():
    master = CONFIG["LOCATION_MASTER"].copy()
    master["現在地"] = (st.session_state.lat, st.session_state.lon)
    master["地図で指定"] = (st.session_state.lat, st.session_state.lon)
    
    current_idx = 0
    if st.session_state.last_basho in master:
        current_idx = list(master.keys()).index(st.session_state.last_basho)
    
    basho = st.selectbox("地点を選択してください", list(master.keys()), index=current_idx)
    
    if basho != st.session_state.last_basho:
        st.session_state.last_basho = basho
        if basho != "地図で指定":
            st.session_state.lat, st.session_state.lon = master[basho]
        st.rerun()
    return basho

#==========================================================================================
# 8. 現在地取得サブルーチン (製品版・高精度版)
#==========================================================================================
def handle_current_location_update():
    """
    スマホ環境で動作確認済みの位置情報取得ロジック。
    不要なデバッグ表示を廃止し、スムーズな更新を実現。
    """
    st.markdown("---")
    STORAGE_KEY = CONFIG['STORAGE_KEY']
    
    if st.button("📍 現在地からグラフを作成", use_container_width=True):
        st.session_state.waiting_loc = True
        st.rerun()

    if st.session_state.get("waiting_loc"):
        with st.status("🛰️ 現在地を計算中...", expanded=True) as status:
            loc = streamlit_js_eval(
                js_expressions="get_geolocation", 
                key="get_geo_stable_prod"
            )
            
            if loc:
                new_lat = round(loc['coords']['latitude'], 4)
                new_lon = round(loc['coords']['longitude'], 4)
                
                # データの同期
                st.session_state.lat = new_lat
                st.session_state.lon = new_lon
                st.session_state.last_basho = "現在地"
                
                save_data = {
                    "lat": new_lat, 
                    "lon": new_lon, 
                    "basho": "現在地",
                    "danger_v": st.session_state.get("danger_v", CONFIG["DEFAULT_DANGER_V"]),
                    "sel_dirs": st.session_state.get("sel_dirs", CONFIG["DEFAULT_DIRS"])
                }
                streamlit_js_eval(
                    js_expressions=f"localStorage.setItem('{STORAGE_KEY}', '{json.dumps(save_data)}')",
                    key="save_geo_prod"
                )
                
                status.update(label="✅ 現在地を反映しました！", state="complete", expanded=False)
                st.session_state.waiting_loc = False
                st.rerun()
            
            elif loc is False:
                status.update(label="❌ 取得に失敗しました", state="error")
                st.error("設定で位置情報を許可するか、電波の良い場所で再度お試しください。")
                if st.button("閉じる"):
                    st.session_state.waiting_loc = False
                    st.rerun()        
        
        

#==========================================================================================
# サイドバー設定サブルーチン (保存対応版)
#==========================================================================================
def show_sidebar_controls():
    st.sidebar.header("表示設定")
    
    default_v = st.session_state.get("danger_v", CONFIG["DEFAULT_DANGER_V"])
    danger_v = st.sidebar.number_input("危険風速ライン(m/s)", value=default_v, step=0.5)
    st.session_state.danger_v = danger_v
    
    st.sidebar.write("色付風向")
    saved_dirs = st.session_state.get("sel_dirs", CONFIG["DEFAULT_DIRS"])
    
    sel_dirs = []
    cols = st.sidebar.columns(2)
    for i, d in enumerate(ALL_DIRECTIONS):
        with cols[i % 2]:
            if st.checkbox(d, value=(d in saved_dirs), key=f"chk_{d}"):
                sel_dirs.append(d)
    
    st.session_state.sel_dirs = sel_dirs
    return danger_v, sel_dirs

#==========================================================================================
# 現在時刻と更新ボタンを表示するサブルーチン
#==========================================================================================
def render_header_info():
    c1, c2 = st.columns([7, 3])
    with c1:
        now = datetime.now(timezone(timedelta(hours=9)))
        st.markdown(f"<p style='font-size:{CONFIG['LOC_INFO_FONT_SIZE']}; color:{CONFIG['LOC_INFO_COLOR']}; font-weight:bold;'>📍 現在：{st.session_state.last_basho} ({st.session_state.lat:.4f}, {st.session_state.lon:.4f})<br><span style='font-size:12px; color:gray;'>取得時刻: {now.strftime('%Y/%m/%d %H:%M:%S')}</span></p>", unsafe_allow_html=True)
    with c2:
        if st.button("🔄 グラフ更新", use_container_width=True):
            st.cache_data.clear()
            st.rerun()

#==========================================================================================
# 14. UIレイアウト：行列配置サブルーチン
#==========================================================================================
def render_structured_grid():
    """
    ユーザー指定の3行構成を厳密に描画する。
    """
    # 全幅制限とスマホ横並び強制のCSS
    st.markdown(f'''
        <style>
            .block-container {{ max-width: {CONFIG["GRID_WIDTH"]}; padding-top: 2rem; }}
            [data-testid="column"] {{ min-width: 0px !important; }}
            div.stButton > button {{ width: 100%; padding: 0px; }}
        </style>
    ''', unsafe_allow_html=True)

    # --- 1行目: [空白, タイトル, 空白] (1:1:1) ---
    r1c1, r1c2, r1c3 = st.columns(CONFIG["RATIO_R1"])
    with r1c2:
        st.markdown(f'<div style="text-align:center; font-size:{CONFIG["TITLE_SIZE"]}px; font-weight:bold; white-space:nowrap;">⛵高須風</div>', unsafe_allow_html=True)

    # --- 2行目: [地点選択, 地図, 現在地取得] (2:1:1) ---
    r2c1, r2c2, r2c3 = st.columns(CONFIG["RATIO_R2"])
    with r2c1:
        master = CONFIG["LOCATION_MASTER"].copy()
        if st.session_state.last_basho == "現在地":
            master["現在地"] = (st.session_state.lat, st.session_state.lon)
        master["地図で指定"] = (st.session_state.lat, st.session_state.lon)
        current_idx = list(master.keys()).index(st.session_state.last_basho) if st.session_state.last_basho in master else 0
        basho = st.selectbox("地点", list(master.keys()), index=current_idx, label_visibility="collapsed")
    with r2c2:
        show_map = st.checkbox("🗺️地図", value=st.session_state.get('show_map_state', False))
        st.session_state.show_map_state = show_map
    with r2c3:
        handle_current_location_update() # この中身はボタン1つ

    if basho != st.session_state.last_basho:
        st.session_state.last_basho = basho
        if basho not in ["地図で指定", "現在地"]:
            st.session_state.lat, st.session_state.lon = master[basho]
        st.rerun()

    if show_map:
        show_location_map() # 既存の3x3地図

    # --- 3行目: [現在：地点, 時刻, 更新] (2:1:1) ---
    r3c1, r3c2, r3c3 = st.columns(CONFIG["RATIO_R3"])
    now = datetime.now(timezone(timedelta(hours=9)))
    with r3c1:
        st.markdown(f'''<div style="background:{CONFIG['STATUS_BG_COLOR']}; padding:5px; border-radius:5px; font-size:{CONFIG['STATUS_FONT_SIZE_MAIN']}; overflow:hidden; white-space:nowrap; text-overflow:ellipsis; border-left:3px solid {CONFIG['LOC_INFO_COLOR']};">📍{st.session_state.last_basho}</div>''', unsafe_allow_html=True)
    with r3c2:
        st.markdown(f'''<div style="text-align:center; line-height:35px; font-size:{CONFIG['STATUS_FONT_SIZE_TIME']}; color:gray;">{now.strftime('%H:%M')}</div>''', unsafe_allow_html=True)
    with r3c3:
        if st.button("🔄更新"):
            st.cache_data.clear()
            st.rerun()

    return show_map
    

#==========================================================================================
# 14. UIレイアウト：上部コントロール配置サブルーチン
#==========================================================================================
def render_top_controls():
    """
    地点選択と地図表示トグルを横並びに配置する。
    """
    # スマホでも横並びを強制するCSS
    st.markdown('''
        <style>
            [data-testid="column"] { min-width: 0px !important; }
        </style>
    ''', unsafe_allow_html=True)

    c1, c2 = st.columns(CONFIG["COL_RATIO_HEADER"])
    with c1:
        master = CONFIG["LOCATION_MASTER"].copy()
        if st.session_state.last_basho == "現在地":
            master["現在地"] = (st.session_state.lat, st.session_state.lon)
        master["地図で指定"] = (st.session_state.lat, st.session_state.lon)
        
        current_idx = list(master.keys()).index(st.session_state.last_basho) if st.session_state.last_basho in master else 0
        basho = st.selectbox("地点を選択", list(master.keys()), index=current_idx, label_visibility="collapsed")
    
    with c2:
        show_map = st.checkbox("🗺️ 地図", value=st.session_state.get('show_map_state', False))
        st.session_state.show_map_state = show_map

    if basho != st.session_state.last_basho:
        st.session_state.last_basho = basho
        if basho not in ["地図で指定", "現在地"]:
            st.session_state.lat, st.session_state.lon = master[basho]
        st.rerun()
    
    return show_map

#==========================================================================================
# 15. UIレイアウト：アクションボタン配置サブルーチン
#==========================================================================================
def render_action_buttons():
    """
    現在地取得ボタンと更新ボタンを横並びに配置する。
    """
    ac1, ac2 = st.columns(CONFIG["COL_RATIO_ACTION"])
    with ac1:
        # 現在地ボタンの幅を調整
        handle_current_location_update()
    with ac2:
        if st.button("🔄 更新", use_container_width=True):
            st.cache_data.clear()
            st.rerun()

#==========================================================================================
# 16. UIレイアウト：現在地点ステータス表示サブルーチン
#==========================================================================================
def render_status_display():
    """
    現在の地点情報と取得時刻をカード形式で表示する。
    """
    now = datetime.now(timezone(timedelta(hours=9)))
    status_html = f"""
    <div style="
        background-color: {CONFIG['STATUS_BG_COLOR']}; 
        padding: 5px 10px; 
        border-radius: 8px; 
        border-left: 5px solid {CONFIG['LOC_INFO_COLOR']};
        margin-top: {CONFIG['ELEMENT_SPACING']};
        margin-bottom: 5px;">
        <span style="font-size: {CONFIG['STATUS_FONT_SIZE_LABEL']}; color: #666;">📍 現在：</span>
        <span style="font-size: {CONFIG['STATUS_FONT_SIZE_MAIN']}; color: {CONFIG['LOC_INFO_COLOR']}; font-weight: bold;">
            {st.session_state.last_basho}
        </span>
        <span style="font-size: 10px; color: gray; float: right; line-height: 20px;">
            {now.strftime('%H:%M:%S')}
        </span>
    </div>
    """
    st.markdown(status_html, unsafe_allow_html=True)

#==========================================================================================
# 14. UIレイアウト：4行構造化グリッド
#==========================================================================================
def render_app_console():
    """
    ユーザー指定の4行構成を厳密に描画。
    余分な区切り線を排除し、スマホでの横並びを死守する。
    """
    # CSS: 全体幅制限、ヘッダー除去、カラム横並び強制
    st.markdown(f'''
        <style>
            .block-container {{ max-width: {CONFIG["APP_MAX_WIDTH"]}; padding-top: 1.5rem; }}
            [data-testid="column"] {{ min-width: 0px !important; }}
            header {{ visibility: hidden; }}
            hr {{ margin: 5px 0px; }} /* 区切り線の余白を最小化 */
        </style>
    ''', unsafe_allow_html=True)

    # --- 1行目: [空白, タイトル, 空白] (1:8:1) ---
    r1c1, r1c2, r1c3 = st.columns(CONFIG["RATIO_R1"])
    with r1c2:
        st.markdown(f'<div style="text-align:center; font-size:{CONFIG["TITLE_SIZE"]}px; font-weight:bold; white-space:nowrap;">⛵ 高須風チェッカー</div>', unsafe_allow_html=True)

    # --- 2行目: [地点選択, 地図, 現在地] (2:1:1) ---
    r2c1, r2c2, r2c3 = st.columns(CONFIG["RATIO_R2"])
    with r2c1:
        master = CONFIG["LOCATION_MASTER"].copy()
        if st.session_state.last_basho == "現在地":
            master["現在地"] = (st.session_state.lat, st.session_state.lon)
        master["地図で指定"] = (st.session_state.lat, st.session_state.lon)
        current_idx = list(master.keys()).index(st.session_state.last_basho) if st.session_state.last_basho in master else 0
        basho = st.selectbox("地点", list(master.keys()), index=current_idx, label_visibility="collapsed")
    with r2c2:
        # 地図トグル。ラベルを短くして横並びを維持
        show_map = st.checkbox("🗺️地図", value=st.session_state.get('show_map_state', False))
        st.session_state.show_map_state = show_map
    with r2c3:
        # 現在地取得ボタンを呼び出し（内部の markdown("---") は事前に消去済みとする）
        handle_current_location_update()

    if basho != st.session_state.last_basho:
        st.session_state.last_basho = basho
        if basho not in ["地図で指定", "現在地"]:
            st.session_state.lat, st.session_state.lon = master[basho]
        st.rerun()

    if show_map:
        show_location_map()

    # --- 3行目: [現在：地点（緯度経度）] (1列全幅) ---
    st.markdown(f'''
        <div style="background:{CONFIG['STATUS_BG_COLOR']}; padding:6px 10px; border-radius:5px; border-left:5px solid {CONFIG['LOC_INFO_COLOR']}; margin: 5px 0px;">
            <span style="font-size:12px; color:#666;">📍 現在：</span>
            <span style="font-size:{CONFIG['STATUS_FONT_SIZE_MAIN']}; font-weight:bold; color:{CONFIG['LOC_INFO_COLOR']};">
                {st.session_state.last_basho} ({st.session_state.lat:.4f}, {st.session_state.lon:.4f})
            </span>
        </div>
    ''', unsafe_allow_html=True)

    # --- 4行目: [日付時刻, 更新] (1:1) ---
    r4c1, r4c2 = st.columns(CONFIG["RATIO_R4"])
    now = datetime.now(timezone(timedelta(hours=9)))
    with r4c1:
        st.markdown(f'<div style="line-height:35px; font-size:{CONFIG["STATUS_FONT_SIZE_TIME"]}; color:gray; padding-left:5px;">🕒 {now.strftime("%m/%d %H:%M:%S")}</div>', unsafe_allow_html=True)
    with r4c2:
        if st.button("🔄 グラフ更新", use_container_width=True):
            st.cache_data.clear()
            st.rerun()

    return show_map

#==========================================================================================
# 17. メインフロー (最終構造化版)
#==========================================================================================
def main():
    setup_font()
    
    # SessionState初期化
    if 'lat' not in st.session_state: st.session_state.lat = CONFIG["DEFAULT_LAT"]
    if 'lon' not in st.session_state: st.session_state.lon = CONFIG["DEFAULT_LON"]
    if 'last_basho' not in st.session_state: st.session_state.last_basho = CONFIG["DEFAULT_BASHO"]
    sync_all_settings()

    if "initialized" not in st.session_state:
        st.info("設定を読み込み中...")
        st.stop()

    # 4行の行列コンソールを描画
    render_app_console()
    
    # サイドバー設定 (既存維持)
    danger_v, sel_dirs = show_sidebar_controls()
    
    # 高解像度グラフ描画 (既存維持)
    img = generate_high_res_graph(st.session_state.lat, st.session_state.lon, danger_v, tuple(sel_dirs))
    
    if img:
        # グラフを全幅で表示。余白を微調整。
        st.markdown(f'<div style="overflow-x: auto; background: white; margin-top:5px;"><img src="data:image/png;base64,{img}" style="height: 850px; max-width: none;"></div>', unsafe_allow_html=True)

if __name__ == "__main__":
    main()
    

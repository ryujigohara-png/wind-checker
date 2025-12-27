# -*- coding: utf-8 -*-
#///// 最終更新 2025.12.27 18:00 コンプリート版//////////////////////////////////////////////////////////////
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
    "GRAPH_FONT_SIZE": 13,
    "LABEL_SIZE": 12,
    "ANNOT_SIZE": 15,
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
# 2. グラフに使用する日本語フォントをセットアップするサブルーチン
#==========================================================================================
def setup_font():
    font_url = "https://github.com/google/fonts/raw/main/ofl/notosansjp/NotoSansJP%5Bwght%5D.ttf"
    font_path = "NotoSansJP.ttf"
    if not os.path.exists(font_path):
        urllib.request.urlretrieve(font_url, font_path)
    fm.fontManager.addfont(font_path)
    plt.rc('font', family='Noto Sans JP', size=CONFIG["GRAPH_FONT_SIZE"])

#==========================================================================================
# 3. Open-Meteo APIから気象データを取得するサブルーチン
#==========================================================================================
def fetch_weather_data(lat, lon, days):
    url = f"https://api.open-meteo.com/v1/forecast?latitude={lat}&longitude={lon}&hourly=temperature_2m,wind_speed_10m,wind_direction_10m,weather_code&timezone=Asia%2FTokyo&wind_speed_unit=ms&forecast_days={days}"
    try:
        data = requests.get(url).json()
        df = pd.DataFrame(data["hourly"])
        df['time'] = pd.to_datetime(df['time'])

        # --- 天気情報を一括適用して3つの列（名称、色、アイコン）を追加 ---
        weather_results = [get_weather_info(code) for code in df['weather_code']]
        df['weather_name'] = [res[0] for res in weather_results]
        df['weather_color'] = [res[1] for res in weather_results]
        df['weather_icon'] = [res[2] for res in weather_results]
        
        return df
    except:
        return None

#==========================================================================================
# 4. 指定された時間リストに基づき簡易的な潮位を計算するサブルーチン (既存維持)
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
# 5. 天気コードを日本語の名称と表示用の色に変換するサブルーチン (既存維持)
#==========================================================================================
def get_weather_info(code):
    if pd.isna(code): return "不明", "black", "・"
    
    # 0, 1: 快晴・晴れ
    if code <= 1: 
        return "晴", "#FF4500", "☀️"
    # 2, 3: 時々曇り・曇り
    if code <= 3: 
        return "曇", "#696969", "☁️"
    # 45, 48: 霧
    if code <= 48: 
        return "霧", "#A9A9A9", "🌫️"
    # 51 - 67: 小雨・雨・みぞれ
    if code <= 67: 
        return "雨", "#00008B", "☔"
    # 71 - 77: 雪
    if code <= 77: 
        return "雪", "#00BFFF", "❄️"
    # 80 - 82: 俄か雨（シャワー）
    if code <= 82: 
        return "雨", "#4682B4", "🌦️"
    # 95 - 99: 雷雨
    if code <= 99: 
        return "雷", "#800080", "⛈️"
        
    return "？", "black", "・"

#==========================================================================================
# 6. 風向角度を名称と矢印に変換し、条件に基づきグラフの色を判定するサブルーチン (既存維持)
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
# 7. グラフのX軸ラベルフォーマッタ (既存維持)
#==========================================================================================
def get_x_axis_formatter():
    jp_weeks = ["月", "火", "水", "木", "金", "土", "日"]
    def formatter(x, p):
        dt = mdates.num2date(x)
        if dt.hour == 0:
            return dt.strftime('%H:%M') + f'\n({jp_weeks[dt.weekday()]})\n' + dt.strftime('%m/%d')
        elif dt.hour in [3, 9, 15, 21]:
            return f"\n{dt.strftime('%H:%M')}"
        else:
            return dt.strftime('%H:%M')
    return formatter

#==========================================================================================
# 8. 共通の軸設定 (既存維持)
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
# 9. 風速棒グラフ描画 (既存維持)
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
# 10. 気温・潮位描画サブルーチン (既存維持)
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
# 11. 高解像度グラフ生成 (既存維持)
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
# 12. 地図UI表示サブルーチン (仕様5.2: 3x3格子レイアウト)
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
# 13. ブラウザのLocalStorageとSessionStateを同期するサブルーチン (NameError回避・安定版)
#==========================================================================================
def sync_all_settings():
    STORAGE_KEY = CONFIG['STORAGE_KEY']

    # --- 読み込み処理（一切変更せず維持：苦労して完成させたロジックを保護） ---
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

    # --- 書き込み処理（NameErrorの元となる time.time() を完全に排除） ---
    save_data = {
        "lat": st.session_state.lat,
        "lon": st.session_state.lon,
        "basho": st.session_state.last_basho,
        "danger_v": st.session_state.get("danger_v", CONFIG["DEFAULT_DANGER_V"]),
        "sel_dirs": st.session_state.get("sel_dirs", CONFIG["DEFAULT_DIRS"])
    }
    js_save = f"localStorage.setItem('{STORAGE_KEY}', '{json.dumps(save_data)}')"
    
    # 解決策：
    # エラーの原因である time.time() を削除し、代わりにアプリで定義済みの last_basho を使用します。
    # これにより、import time を追加する必要がなくなり、NameError は確実に消えます。
    safe_key = f"save_storage_{st.session_state.last_basho}"
    streamlit_js_eval(js_expressions=js_save, key=safe_key)
    
    
#==========================================================================================
# 14. 地点選択のロジックを制御するサブルーチン
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
# 15.. 現在地取得サブルーチン (ロジックは一切変えず、配置のみ全幅・左寄せに修正)
#==========================================================================================
def handle_current_location_update():
    """
    現在地取得ボタン。末尾に空白を入れて左寄せを擬似的に表現。
    """
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
# 16. サイドバー設定サブルーチン (保存対応版)
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
# 17. 現在時刻と更新ボタンを表示するサブルーチン (1行化・全幅・左寄せ)
#==========================================================================================
def render_header_info(current_basho_name):
    """
    データ更新ボタン。ラベルに日付と時刻を組み込みます。
    """
    # 現在の日時を取得（日本時間）
    now = datetime.now(timezone(timedelta(hours=9)))
    # 日付と時刻のフォーマット（例：2025/12/27 17:24）
    date_time_str = now.strftime('%Y/%m/%d %H:%M:%S')
    
    # ボタンのラベルに日付・時刻を組み込み
    update_label = f"🔄 グラフ更新 ({date_time_str})　　   　"
    
    if st.button(update_label, use_container_width=True):
        st.cache_data.clear()
        st.rerun()
    
    
#==========================================================================================
# 18. メインフロー (PC完全復元 ＆ スマホ安定表示版)
#==========================================================================================
def main():
    setup_font()

    # --- CSS注入：最小限の左寄せ設定 ---
    st.markdown(f"""
        <style>
            .block-container {{ padding-top: 3.5rem !important; padding-bottom: 0rem !important; }}
            h1 {{ margin-top: 0px !important; margin-bottom: -15px !important; line-height: 1.0 !important; }}
            [data-testid="stVerticalBlock"] {{ gap: 0.3rem !important; }}
            div.stButton > button p {{ text-align: left !important; width: 100% !important; }}
            div.stButton > button {{ justify-content: flex-start !important; }}
        </style>
    """, unsafe_allow_html=True)

    st.markdown(f'<h1 style="font-size:{CONFIG["TITLE_SIZE"]}px;">⛵ 高須風チェッカー</h1>', unsafe_allow_html=True)
    
    if 'lat' not in st.session_state: st.session_state.lat = CONFIG["DEFAULT_LAT"]
    if 'lon' not in st.session_state: st.session_state.lon = CONFIG["DEFAULT_LON"]
    if 'last_basho' not in st.session_state: st.session_state.last_basho = CONFIG["DEFAULT_BASHO"]
    sync_all_settings()

    if "initialized" not in st.session_state:
        st.info("設定を読み込み中...")
        st.stop()

    # --- 地点選択コンボボックス（座標を名前に統合） ---
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

        # 【機能回復】「地図で指定」が選ばれたら、地図表示フラグを強制的にONにする
        if basho == "地図で指定":
            st.session_state.show_map_state = True
            
        st.rerun()

    show_map = st.checkbox("地図表示", value=st.session_state.get('show_map_state', False))
    st.session_state.show_map_state = show_map
    if show_map:
        show_location_map()

    # --- ボタン配置（カラム落ちハック：0.7+0.7） ---
    col1, col2 = st.columns([0.7, 0.7]) 
    with col1:
        handle_current_location_update()
    with col2:
        render_header_info(basho) 
    
    danger_v, sel_dirs = show_sidebar_controls()

    # 1. グラフ用のデータ（アイコン用データ）を先に取得
    df_for_icons = fetch_weather_data(st.session_state.lat, st.session_state.lon, 8)
    
    # 2. グラフ画像を生成
    img = generate_high_res_graph(st.session_state.lat, st.session_state.lon, danger_v, tuple(sel_dirs))
    
    # --- main内の描画部分 ---
    if img and df_for_icons is not None:
        # fetch_weather_dataで作成したアイコン列を利用
        icons = df_for_icons['weather_icon'].tolist()
        
        # 26pxで少し大きく、ハッキリ見えるようにします
        icon_html = "".join([f'<div style="min-width: 80px; text-align: center; font-size: 26px;">{icon}</div>' for icon in icons])
        
        st.markdown(f"""
            <div style="overflow-x: auto; background: white; white-space: nowrap; border-radius: 8px;">
                <div style="display: flex; padding-left: 70px; margin-bottom: -10px; padding-top: 15px;">
                    {icon_html}
                </div>
                <img src="data:image/png;base64,{img}" style="height: 850px; max-width: none; display: block;">
            </div>
        """, unsafe_allow_html=True)

#==========================================================================================
# XX. 呼び出しコード
#==========================================================================================
if __name__ == "__main__":
    main()

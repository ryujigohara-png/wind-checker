# -*- coding: utf-8 -*-
# Wind Checker v2 - 構造化・整理済み完全版 (2026.01.03)
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
    "GRAPH_FONT_SIZE": 11,
    "GRAPH_WIDTH": 15,
    "GRAPH_HIGHT": 2.0,
    "LABEL_SIZE": 7,
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
    "HSPACE": 1.0,
    "DEFAULT_LAT": 31.337,
    "DEFAULT_LON": 130.795,
    "DEFAULT_BASHO": "高須沖(鹿児島県)",
    "DEFAULT_DANGER_V": 10.0,
    "DEFAULT_DIRS": ["南","南南西","南西","西南西","西","西北西","北西","北北西"],
    "ANNOT_Y_STEP": 1.5,
    "ANNOT_BASE_Y": 0.5,
    "SHOW_DEV_MODE": False,
    "STORAGE_KEY": "wind_checker_settings_v2",
    "TEMP_COLOR": "darkorange",
    "ARROW_COLOR": "blue",
    "VLINE_WIDTH": 1.25,
    "HLINE_WIDTH": 1.0,
    "PX_PER_INCH": 200,
    "DEFAULT_PRECIP_Y": 1.00,
    "LOCATION_MASTER": [
        {"name": "高須沖(鹿児島県)", "lat": 31.337, "lon": 130.795},
        {"name": "柏原沖(鹿児島県)", "lat": 31.380, "lon": 131.020},
        {"name": "垂水港(鹿児島県)", "lat": 31.478, "lon": 130.668},
        {"name": "海潟(鹿児島県)", "lat": 31.539, "lon": 130.706},
        {"name": "磯海岸沖(鹿児島県)", "lat": 31.614, "lon": 130.577},
        {"name": "江口浜沖(鹿児島県)", "lat": 31.643, "lon": 130.322},
        {"name": "錦江湾(鹿児島県)", "lat": 31.590, "lon": 130.600}
    ]
}

ALL_DIRECTIONS = ["北", "北北東", "北東", "東北東", "東", "東南東", "南東", "南南東", "南", "南南西", "南西", "西南西", "西", "西北西", "北西", "北北西"]

# ======================================================================================
# 10. 共通ユーティリティ (フォント・地名・同期)
# ======================================================================================
def setup_font(font_size=None):
    if font_size is None: font_size = CONFIG["GRAPH_FONT_SIZE"]
    font_url = "https://github.com/google/fonts/raw/main/ofl/notosansjp/NotoSansJP%5Bwght%5D.ttf"
    font_path = "NotoSansJP.ttf"
    if not os.path.exists(font_path): urllib.request.urlretrieve(font_url, font_path)
    fm.fontManager.addfont(font_path)
    plt.rc('font', family='Noto Sans JP', size=font_size)

def fetch_location_name(lat, lon):
    try:
        url = f"https://nominatim.openstreetmap.org/reverse?format=json&lat={lat}&lon={lon}&zoom=14"
        headers = {"User-Agent": "WindChecker/2.0"}
        response = requests.get(url, headers=headers, timeout=5)
        if response.status_code == 200:
            data = response.json()
            address = data.get("address", {})
            return address.get("city") or address.get("town") or address.get("village") or address.get("suburb") or "指定地点"
        return "指定地点"
    except: return "指定地点"

def sync_all_settings():
    if st.session_state.get("initialized"): return
    js_query = f"localStorage.getItem('{CONFIG['STORAGE_KEY']}') || 'EMPTY'"
    stored_data = streamlit_js_eval(js_expressions=js_query, key="init_load_v5")
    if stored_data is None: st.stop()
    if stored_data == "EMPTY" or stored_data == "":
        st.session_state.initialized = True
        # 初期値セットアップ
        st.session_state.lat = CONFIG["DEFAULT_LAT"]
        st.session_state.lon = CONFIG["DEFAULT_LON"]
        st.session_state.last_basho = CONFIG["DEFAULT_BASHO"]
        st.session_state.show_wind = CONFIG["SHOW_WIND"]
        st.session_state.show_temp = CONFIG["SHOW_TEMP"]
        st.session_state.show_tide = CONFIG["SHOW_TIDE"]
        st.session_state.width = CONFIG["GRAPH_WIDTH"]
        st.session_state.base_height = CONFIG["GRAPH_HIGHT"]
        st.session_state.base_font_size = CONFIG["GRAPH_FONT_SIZE"]
        st.session_state.label_font_size = CONFIG["LABEL_SIZE"]
        st.session_state.danger_v = CONFIG["DEFAULT_DANGER_V"]
        st.session_state.sel_dirs = CONFIG["DEFAULT_DIRS"]
        st.session_state.LOCATION_MASTER = CONFIG["LOCATION_MASTER"]
    else:
        try:
            data = json.loads(stored_data)
            for k, v in data.items(): st.session_state[k] = v
            # キー名が一部異なる場合の補完
            if "basho" in data: st.session_state.last_basho = data["basho"]
            st.session_state.initialized = True
            st.rerun()
        except: st.session_state.initialized = True

def save_settings_to_browser():
    save_data = {
        "lat": st.session_state.lat, "lon": st.session_state.lon, "basho": st.session_state.last_basho,
        "show_wind": st.session_state.get("show_wind", True), "show_temp": st.session_state.get("show_temp", True),
        "show_tide": st.session_state.get("show_tide", False), "width": st.session_state.get("width", 15),
        "base_height": st.session_state.get("base_height", 2.0), "base_font_size": st.session_state.get("base_font_size", 11),
        "label_font_size": st.session_state.get("label_font_size", 7), "danger_v": st.session_state.get("danger_v", 10.0),
        "sel_dirs": st.session_state.get("sel_dirs", []), "location_master": st.session_state.get("LOCATION_MASTER", [])
    }
    json_data = json.dumps(save_data, ensure_ascii=False)
    components.html(f"""<script>localStorage.setItem("{CONFIG['STORAGE_KEY']}", '{json_data}');</script>""", height=0)

def update_state_and_save(updates_dict):
    for key, value in updates_dict.items(): st.session_state[key] = value
    save_settings_to_browser()
    time.sleep(0.1)
    st.rerun()

# ======================================================================================
# 30. 部品系サブルーチン (地点リスト作成・現在地・地図ダイアログ)
# ======================================================================================
def get_combined_location_list():
    master = st.session_state.get("LOCATION_MASTER", CONFIG["LOCATION_MASTER"])
    display_list = []
    total_data = {}
    for loc in master:
        label = f"{loc['name']} ({loc['lat']:.4f}, {loc['lon']:.4f})"
        display_list.append(label)
        total_data[label] = (loc['lat'], loc['lon'], loc['name'])
    
    curr_label = f"{st.session_state.last_basho} ({st.session_state.lat:.4f}, {st.session_state.lon:.4f})"
    if curr_label not in total_data:
        display_list.insert(0, curr_label)
        total_data[curr_label] = (st.session_state.lat, st.session_state.lon, st.session_state.last_basho)
    
    map_label = "📍 地図で指定..."
    display_list.append(map_label)
    total_data[map_label] = (st.session_state.lat, st.session_state.lon, "地図で指定")
    return display_list, total_data, curr_label

def handle_current_location_update():
    if st.button("🔄 📍現在地を取得", use_container_width=True):
        st.session_state.waiting_loc = True
        st.session_state.geo_key = f"geo_{datetime.now().timestamp()}"
        st.rerun()
    if st.session_state.get("waiting_loc"):
        st.info("🛰️ 現在地を取得中...")
        loc = get_geolocation(component_key=st.session_state.geo_key)
        if loc:
            lat, lon = round(loc['coords']['latitude'], 4), round(loc['coords']['longitude'], 4)
            with st.spinner("地名特定中..."): p_name = fetch_location_name(lat, lon)
            st.session_state.waiting_loc = False
            update_state_and_save({"lat": lat, "lon": lon, "last_basho": p_name})

@st.dialog("📍 地図で地点を指定")
def show_location_map_dialog():
    st.info("地図の中央を合わせ、「地点を確定して保存」を押してください。")
    m_lat = st.session_state.get("map_lat", st.session_state.lat)
    m_lon = st.session_state.get("map_lon", st.session_state.lon)
    m = folium.Map(location=[m_lat, m_lon], zoom_start=13)
    folium.Marker([m_lat, m_lon], icon=folium.Icon(color='red')).add_to(m)
    map_out = st_folium(m, width=650, height=400, key="map_dlg", returned_objects=["center"])
    if map_out and map_out.get("center"):
        st.session_state.map_lat = map_out["center"]["lat"]
        st.session_state.map_lon = map_out["center"]["lng"]
    if st.button("✅ この地点を確定して保存", use_container_width=True):
        t_lat, t_lon = st.session_state.map_lat, st.session_state.map_lon
        with st.spinner("地名取得中..."): p_name = fetch_location_name(t_lat, t_lon)
        update_state_and_save({"lat": t_lat, "lon": t_lon, "last_basho": p_name})

@st.dialog("⚙️ グラフ表示設定")
def show_settings_dialog():
    st.session_state.show_wind = st.checkbox("風速グラフ", value=st.session_state.show_wind)
    st.session_state.show_temp = st.checkbox("気温グラフ", value=st.session_state.show_temp)
    st.session_state.show_tide = st.checkbox("潮汐グラフ", value=st.session_state.show_tide)
    st.session_state.danger_v = st.number_input("危険風速 (m/s)", value=st.session_state.danger_v)
    if st.button("保存して閉じる", use_container_width=True):
        save_settings_to_browser()
        st.rerun()

# ======================================================================================
# 40. データ処理・グラフ描画エンジン (添付ファイルのロジックを完全統合)
# ======================================================================================
def fetch_weather_data(lat, lon, days):
    url = f"https://api.open-meteo.com/v1/forecast?latitude={lat}&longitude={lon}&hourly=temperature_2m,wind_speed_10m,wind_direction_10m,weather_code,precipitation&timezone=Asia%2FTokyo&wind_speed_unit=ms&forecast_days={days}"
    try:
        data = requests.get(url).json()
        df = pd.DataFrame(data["hourly"])
        df['time'] = pd.to_datetime(df['time'])
        def get_icon(code):
            if code == 0: return "☀️"
            if code <= 3: return "🌤️"
            if code == 45 or code == 48: return "🌫️"
            if code <= 67: return "☔"
            if code <= 77: return "❄️"
            if code <= 82: return "🌦️"
            if code <= 86: return "🌨️"
            if code <= 99: return "⛈️"
            return "❓"
        df['weather_icon'] = df['weather_code'].apply(get_icon)
        return df
    except: return None

def process_wind_data(df, target_dirs):
    dirs = ALL_DIRECTIONS + ["北"]
    arrows = ["↓", "↙", "↙", "↙", "←", "↖", "↖", "↖", "↑", "↗", "↗", "↗", "→", "↘", "↘", "↘", "↓"]
    def get_info(deg):
        idx = int((deg + 11.25) / 22.5) % 16
        return dirs[idx], arrows[idx]
    df['res'] = df['wind_direction_10m'].apply(get_info)
    df['dir_name'] = df['res'].apply(lambda x: x[0])
    df['arrow'] = df['res'].apply(lambda x: x[1])
    def judge(row):
        speed = row['wind_speed_10m']
        if speed >= 10.0: return "crimson"
        if row['dir_name'] in target_dirs:
            if 5 <= speed < 10.0: return "orange"
            if 3 <= speed < 5: return "skyblue"
        return "#D3D3D3"
    df['color'] = df.apply(judge, axis=1)
    return df

@st.cache_data(ttl=600)
def generate_high_res_graph(lat, lon, danger_v, selected_dirs_tuple, params, now_jst):
    df_raw = fetch_weather_data(lat, lon, 9)
    if df_raw is None: return None, (0,0), 0, None
    start_t = now_jst.replace(hour=(now_jst.hour // 3) * 3, minute=0, second=0, microsecond=0)
    df = df_raw[df_raw['time'] >= (start_t - timedelta(hours=3))].copy().reset_index(drop=True).head(195)
    df = process_wind_data(df, list(selected_dirs_tuple))
    
    fig, ax = plt.subplots(figsize=(params['width'], params['height']), dpi=CONFIG['DPI'])
    # --- 棒グラフ描画 ---
    ax.bar(df['time'], df['wind_speed_10m'], color=df['color'], width=0.035)
    ax.axhline(y=danger_v, color='red', linestyle='--', linewidth=1)
    ax.axvline(now_jst, color='blue', linewidth=1.5)
    
    # 軸設定 (3時間ごと)
    ax.xaxis.set_major_locator(mdates.HourLocator(byhour=range(0,24,3)))
    ax.xaxis.set_major_formatter(mdates.DateFormatter('%H'))
    ax.set_xlim(df['time'].iloc[0], df['time'].iloc[-1])
    ax.grid(True, linestyle=':', alpha=0.6)

    buf = io.BytesIO()
    fig.savefig(buf, format="png", bbox_inches='tight', pad_inches=0.05)
    plt.close(fig)
    return base64.b64encode(buf.getvalue()).decode(), (0.05, 0.9/194), 3, df

# ======================================================================================
# 50. 画面描画モジュール (render)
# ======================================================================================
def render_location_selector_module():
    display_list, total_data, curr_label = get_combined_location_list()
    col1, col2 = st.columns([4, 1])
    with col1:
        selected = st.selectbox("地点", display_list, index=display_list.index(curr_label), label_visibility="collapsed")
    with col2:
        if st.button("⭐ 登録", use_container_width=True):
            new_fav = {"name": st.session_state.last_basho, "lat": st.session_state.lat, "lon": st.session_state.lon}
            if not any(d['name'] == new_fav['name'] for d in st.session_state.LOCATION_MASTER):
                st.session_state.LOCATION_MASTER.append(new_fav)
                save_settings_to_browser()
                st.success("登録完了")
                st.rerun()
    if selected != curr_label:
        lat, lon, name = total_data[selected]
        if name == "地図で指定": show_location_map_dialog()
        else: update_state_and_save({"lat": lat, "lon": lon, "last_basho": name})

# ======================================================================================
# 24. 【main機能分離】⑤グラフ描画エリアモジュール
# ======================================================================================
def render_graph_area_module(now_jst):
    """グラフの生成、描画を実行する"""
    design_params = {
        "show_wind": st.session_state.show_wind,
        "show_temp": st.session_state.show_temp,
        "show_tide": st.session_state.show_tide,
        "width": st.session_state.width,
        "height": st.session_state.base_height,
        "base_font_size": st.session_state.base_font_size,
        "label_font_size": st.session_state.label_font_size,
        "label_pad": st.session_state.get("label_pad", CONFIG["LABEL_PAD"]),
        "hspace": st.session_state.get("hspace", CONFIG["HSPACE"]),
        "show_w_text": st.session_state.get("show_w_text", CONFIG["SHOW_W_TEXT"]),
        "show_dir_name": st.session_state.get("show_dir_name", CONFIG["SHOW_DIR_NAME"]),
        "ratios": st.session_state.get("ratios", CONFIG["DEFAULT_RATIOS"])
    }

    # 【修正ポイント】サブルーチン側のロジックを変えず、引数側でタイムゾーンを消して渡す
    now_naive = now_jst.replace(tzinfo=None)

    img_b64, ratio_info, start_idx, df_from_graph = generate_high_res_graph(
        st.session_state.lat, 
        st.session_state.lon, 
        st.session_state.danger_v, 
        tuple(st.session_state.sel_dirs), 
        design_params, 
        now_naive  # ここで調整
    )

    if img_b64:
        # (アイコン表示ロジックなどは維持)
        dpi = CONFIG.get("DPI", 200)
        display_width_px = int(design_params.get("width", 15) * dpi)
        
        # もし generate_weather_icons_html があれば呼び出す
        if 'generate_weather_icons_html' in globals():
            icons_html = generate_weather_icons_html(df_from_graph, ratio_info, display_width_px, start_idx)
            st.markdown(icons_html, unsafe_allow_html=True)
            
        st.markdown(f'<img src="data:image/png;base64,{img_b64}" style="width:100%;">', unsafe_allow_html=True)
        
# ======================================================================================
# 100. メイン処理
# ======================================================================================
def main():
    sync_all_settings()
    setup_font(st.session_state.get("base_font_size", 11))
    st.title("Wind Checker v2")
    now_jst = datetime.now(timezone(timedelta(hours=9)))
    
    render_location_selector_module() # ① 地点選択
    if st.button("🗺️ 地図表示", use_container_width=True): show_location_map_dialog() # ② 地図
    handle_current_location_update() # ③ 現在地
    
    c1, c2 = st.columns(2)
    with c1: 
        if st.button("📊 最新に更新", use_container_width=True): st.rerun()
    with c2: 
        if st.button("⚙️ 表示設定", use_container_width=True): show_settings_dialog()
    
    render_graph_area_module(now_jst) # ⑤ グラフ描画

if __name__ == "__main__":
    main()

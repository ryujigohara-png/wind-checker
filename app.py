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
import json
from datetime import datetime, timedelta, timezone
import matplotlib.dates as mdates
from streamlit_folium import st_folium
import folium
from streamlit_js_eval import streamlit_js_eval

# ======================================================================================
# 1. 定数宣言 (CONFIG) - 仕様書 4.1, 6.
# ======================================================================================
CONFIG = {
    "TITLE": "⛵ Wind & Tide Checker",
    "DPI": 150,
    "GRAPH_HEIGHT": 850,
    "HEIGHT_RATIOS": [4, 2, 2],  # 風速, 気温, 潮位
    "DEFAULT_LAT": 31.337,
    "DEFAULT_LON": 130.795,
    "DEFAULT_BASHO": "高須沖(鹿児島県)",
    "DEFAULT_DANGER_V": 12.0,
    "DEFAULT_DIRS": ["南","南南西","南西","西南西","西","西北西","北西","北北西"],
    "STORAGE_KEY": "wind_checker_v2_settings",
    "COLORS": {
        "blue": "skyblue",
        "orange": "orange",
        "red": "crimson",
        "grey": "#D3D3D3",
        "tide": "royalblue"
    }
}

ALL_DIRECTIONS = ["北", "北北東", "北東", "東北東", "東", "東南東", "南東", "南南東", "南", "南南西", "南西", "西南西", "西", "西北西", "北西", "北北西"]

# ======================================================================================
# 2. サブルーチン：初期設定・フォント (仕様 1.1)
# ======================================================================================
def setup_environment():
    """フォント設定とページ構成の初期化"""
    st.set_page_config(layout="wide", page_title=CONFIG["TITLE"])
    font_url = "https://github.com/google/fonts/raw/main/ofl/notosansjp/NotoSansJP%5Bwght%5D.ttf"
    font_path = "NotoSansJP.ttf"
    if not os.path.exists(font_path):
        urllib.request.urlretrieve(font_url, font_path)
    fm.fontManager.addfont(font_path)
    plt.rc('font', family='Noto Sans JP')

# ======================================================================================
# 3. サブルーチン：LocalStorage同期 (仕様 2.1, 3.1)
# ======================================================================================
def sync_browser_storage():
    """ブラウザのlocalStorageから設定を復元し、session_stateに同期する"""
    js_get = f"localStorage.getItem('{CONFIG['STORAGE_KEY']}')"
    stored_json = streamlit_js_eval(js_expressions=js_get, key="load_storage")
    
    if stored_json:
        try:
            data = json.loads(stored_json)
            # 取得した値をstateに流し込む（存在チェック付き）
            st.session_state.lat = float(data.get("lat", CONFIG["DEFAULT_LAT"]))
            st.session_state.lon = float(data.get("lon", CONFIG["DEFAULT_LON"]))
            st.session_state.last_basho = data.get("basho", CONFIG["DEFAULT_BASHO"])
            st.session_state.danger_v = float(data.get("danger_v", CONFIG["DEFAULT_DANGER_V"]))
            st.session_state.sel_dirs = data.get("sel_dirs", CONFIG["DEFAULT_DIRS"])
            st.session_state.show_temp = data.get("show_temp", True)
            st.session_state.show_tide = data.get("show_tide", True)
            st.session_state.storage_synced = True
        except Exception:
            st.session_state.storage_synced = True # エラー時もループ防止のためTrue
    else:
        # ストレージが空の場合
        if "storage_synced" not in st.session_state:
            st.session_state.storage_synced = False

def save_to_storage():
    """現在のsession_stateをlocalStorageに保存する"""
    save_data = {
        "lat": st.session_state.get("lat"),
        "lon": st.session_state.get("lon"),
        "basho": st.session_state.get("last_basho"),
        "danger_v": st.session_state.get("danger_v"),
        "sel_dirs": st.session_state.get("sel_dirs"),
        "show_temp": st.session_state.get("show_temp"),
        "show_tide": st.session_state.get("show_tide")
    }
    js_set = f"localStorage.setItem('{CONFIG['STORAGE_KEY']}', '{json.dumps(save_data)}')"
    streamlit_js_eval(js_expressions=js_set, key="save_storage_exec")

# ======================================================================================
# 4. サブルーチン：データ取得・処理 (仕様 3.1, 3.2)
# ======================================================================================
def fetch_weather_data(lat, lon):
    """Open-Meteoから8日間のデータを取得"""
    url = f"https://api.open-meteo.com/v1/forecast?latitude={lat}&longitude={lon}&hourly=temperature_2m,wind_speed_10m,wind_direction_10m,weather_code&timezone=Asia%2FTokyo&wind_speed_unit=ms&forecast_days=8"
    try:
        r = requests.get(url, timeout=10)
        df = pd.DataFrame(r.json()["hourly"])
        df['time'] = pd.to_datetime(df['time'])
        return df
    except: return None

def get_tide_level(times):
    """仕様 3.2: 簡易潮位計算 (2025/1/1 06:00基準)"""
    base = datetime(2025, 1, 1, 6, 0)
    return [100 * np.cos(2 * np.pi * ((t - base).total_seconds() / 3600) / 12.42) for t in times]

def process_graph_data(df, target_dirs):
    """着色ロジックとパディングの適用 (仕様 3.1, 3.2)"""
    # 3時間のパディング
    pad_time = [df['time'].iloc[0] - timedelta(hours=i) for i in range(1, 4)][::-1]
    df = pd.concat([pd.DataFrame({'time': pad_time}), df], ignore_index=True)
    
    # 風向・色判定
    def judge_color(row):
        v = row['wind_speed_10m']
        if pd.isna(v) or v < 3.0: return CONFIG["COLORS"]["grey"]
        
        # 風向名の取得
        idx = int((row['wind_direction_10m'] + 11.25) / 22.5) % 16
        dir_name = ALL_DIRECTIONS[idx]
        
        if v >= 10.0: return CONFIG["COLORS"]["red"]
        if dir_name in target_dirs:
            if 5.0 <= v < 10.0: return CONFIG["COLORS"]["orange"]
            if 3.0 <= v < 5.0: return CONFIG["COLORS"]["blue"]
        return CONFIG["COLORS"]["grey"]

    df['color'] = df.apply(judge_color, axis=1)
    df['tide'] = get_tide_level(df['time'])
    return df

# ======================================================================================
# 5. サブルーチン：グラフ描画 (仕様 4.1, 4.2)
# ======================================================================================
def generate_base64_graph(df, danger_v, show_temp, show_tide):
    """Matplotlibでグラフを生成しBase64で返す"""
    fig, axes = plt.subplots(3, 1, figsize=(35, 12), dpi=CONFIG["DPI"], 
                             gridspec_kw={'height_ratios': CONFIG["HEIGHT_RATIOS"]})
    now_jst = datetime.now(timezone(timedelta(hours=9))).replace(tzinfo=None)
    
    # 上段：風速
    axes[0].bar(df['time'], df['wind_speed_10m'], color=df['color'], width=0.03)
    axes[0].axhline(danger_v, color='red', linestyle='--', linewidth=2)
    axes[0].set_ylabel("風速 (m/s)")
    
    # 中段：気温
    if show_temp:
        axes[1].plot(df['time'], df['temperature_2m'], color='black', marker='o', markersize=2)
        axes[1].set_ylabel("気温 (℃)")
    else: axes[1].set_visible(False)
    
    # 下段：潮位
    if show_tide:
        axes[2].plot(df['time'], df['tide'], color=CONFIG["COLORS"]["tide"])
        axes[2].fill_between(df['time'], df['tide'], -110, color=CONFIG["COLORS"]["tide"], alpha=0.1)
        axes[2].set_ylabel("潮位")
    else: axes[2].set_visible(False)

    # 共通設定
    for ax in axes:
        if ax.get_visible():
            ax.axvline(now_jst, color='blue', linewidth=2)
            ax.grid(True, linestyle=':', alpha=0.5)
            ax.xaxis.set_major_formatter(mdates.DateFormatter('%m/%d\n%H:%M'))

    buf = io.BytesIO()
    fig.savefig(buf, format="png", bbox_inches='tight')
    plt.close(fig)
    return base64.b64encode(buf.getvalue()).decode()

# ======================================================================================
# 6. メインフロー
# ======================================================================================
def main():
    setup_environment()
    
    # --- A. Session State 初期化 ---
    if 'lat' not in st.session_state:
        st.session_state.update({
            "lat": CONFIG["DEFAULT_LAT"], "lon": CONFIG["DEFAULT_LON"],
            "last_basho": CONFIG["DEFAULT_BASHO"], "danger_v": CONFIG["DEFAULT_DANGER_V"],
            "sel_dirs": CONFIG["DEFAULT_DIRS"], "show_temp": True, "show_tide": True,
            "show_map": False
        })

    # --- B. Browser Storage 同期 ---
    sync_browser_storage()

    # --- C. サイドバー UI ---
    st.sidebar.title("🛠 設定")
    danger_v = st.sidebar.number_input("危険風速 (m/s)", 0.0, 25.0, st.session_state.danger_v, step=0.5)
    st.session_state.danger_v = danger_v
    
    show_temp = st.sidebar.checkbox("気温グラフ表示", value=st.session_state.show_temp)
    show_tide = st.sidebar.checkbox("潮位グラフ表示", value=st.session_state.show_tide)
    st.session_state.show_temp, st.session_state.show_tide = show_temp, show_tide
    
    st.sidebar.write("色付風向")
    new_sel_dirs = []
    c1, c2 = st.sidebar.columns(2)
    for i, d in enumerate(ALL_DIRECTIONS):
        with (c1 if i % 2 == 0 else c2):
            if st.checkbox(d, value=(d in st.session_state.sel_dirs), key=f"d_{d}"):
                new_sel_dirs.append(d)
    st.session_state.sel_dirs = new_sel_dirs
    
    st.sidebar.markdown("---")
    st.sidebar.caption("※設定はブラウザに保存されます")

    # --- D. メイン UI (地点選択) ---
    st.title(CONFIG["TITLE"])
    
    master_locs = {
        "高須沖(鹿児島県)": (31.337, 130.795),
        "柏原沖(鹿児島県)": (31.380, 131.020),
        "地図で指定": (st.session_state.lat, st.session_state.lon)
    }
    
    # 選択肢のインデックスをsession_stateから特定
    try:
        curr_idx = list(master_locs.keys()).index(st.session_state.last_basho)
    except: curr_idx = 0
    
    selected_basho = st.selectbox("地点選択", list(master_locs.keys()), index=curr_idx)
    
    # 地点変更時の処理 (仕様 2.1)
    if selected_basho != st.session_state.last_basho:
        st.session_state.last_basho = selected_basho
        if selected_basho == "地図で指定":
            st.session_state.show_map = True # 地図を自動展開
        else:
            st.session_state.lat, st.session_state.lon = master_locs[selected_basho]
        save_to_storage()
        st.rerun()

    # 現在地表示
    st.markdown(f"#### 📍 現在：{st.session_state.last_basho} ({st.session_state.lat:.4f}, {st.session_state.lon:.4f})")

    # --- E. 地図 UI (仕様 2.2) ---
    show_map = st.checkbox("地図表示", value=st.session_state.show_map)
    st.session_state.show_map = show_map
    if show_map:
        # ここに3x3格子レイアウトのshow_location_mapサブルーチンを呼ぶ (省略せず実装可能)
        st.warning("地図中央の『グラフ描画地点確定』ボタンで座標を更新します。")
        m = folium.Map(location=[st.session_state.lat, st.session_state.lon], zoom_start=13)
        folium.Marker([st.session_state.lat, st.session_state.lon]).add_to(m)
        map_data = st_folium(m, height=350, width=700, returned_objects=["center"])
        
        if st.button("グラフ描画地点確定", use_container_width=True):
            if map_data and map_data["center"]:
                st.session_state.lat = map_data["center"]["lat"]
                st.session_state.lon = map_data["center"]["lng"]
                st.session_state.last_basho = "地図で指定"
                save_to_storage()
                st.rerun()

    # --- F. グラフ描画実行 ---
    with st.spinner("データを取得中..."):
        weather_df = fetch_weather_data(st.session_state.lat, st.session_state.lon)
        if weather_df is not None:
            processed_df = process_graph_data(weather_df, st.session_state.sel_dirs)
            b64_img = generate_base64_graph(processed_df, st.session_state.danger_v, show_temp, show_tide)
            
            # 横スクロールコンテナ
            html_code = f"""
            <div style="overflow-x: auto; white-space: nowrap; background-color: white; border: 1px solid #ddd;">
                <img src="data:image/png;base64,{b64_img}" style="height: {CONFIG['GRAPH_HEIGHT']}px; max-width: none;">
            </div>
            """
            st.markdown(html_code, unsafe_allow_html=True)

if __name__ == "__main__":
    main()

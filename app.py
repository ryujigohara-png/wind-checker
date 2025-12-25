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
    "TITLE_SIZE": 24,
    "SUBTITLE_SIZE": 18,
    "GRAPH_FONT_SIZE": 13,
    "LABEL_SIZE": 13,
    "ANNOT_SIZE": 14,
    "DPI": 200,
    "MAP_HEIGHT": 350,
    "HEIGHT_RATIOS": [4.4, 1.2, 0.8],
    "LOC_INFO_FONT_SIZE": "16px",
    "LOC_INFO_COLOR": "#1e88e5",
    "LOC_INFO_MARGIN_TOP": "-10px",
    "DEFAULT_LAT": 31.337,
    "DEFAULT_LON": 130.795,
    "DEFAULT_BASHO": "高須沖(鹿児島県)",
    "DEFAULT_DANGER_V": 12.0,
    "DEFAULT_DIRS": ["南","南南西","南西","西南西","西","西北西","北西","北北西"],
    "ANNOT_Y_STEP": 1.5,
    "ANNOT_BASE_Y": 0.5,
    "STORAGE_KEY": "wind_checker_v20251225",
    "MAP_MOVE_STEP": 0.005,
    "FORECAST_DAYS": 8,
    "PADDING_HOURS": 3
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
# ブラウザのLocalStorageとSessionStateを同期するサブルーチン
#==========================================================================================
def sync_storage_spec_2025():
    """機能仕様書に基づき5項目以上の設定をLocalStorageと完全同期する"""
    if "initialized" not in st.session_state:
        stored_data = streamlit_js_eval(js_expressions=f"localStorage.getItem('{CONFIG['STORAGE_KEY']}')", key="load_storage")
        if stored_data:
            try:
                d = json.loads(stored_data)
                st.session_state.lat = float(d.get("lat", CONFIG["DEFAULT_LAT"]))
                st.session_state.lon = float(d.get("lon", CONFIG["DEFAULT_LON"]))
                st.session_state.last_basho = d.get("basho", CONFIG["DEFAULT_BASHO"])
                st.session_state.sel_map_lat = float(d.get("sel_map_lat", CONFIG["DEFAULT_LAT"]))
                st.session_state.sel_map_lon = float(d.get("sel_map_lon", CONFIG["DEFAULT_LON"]))
                st.session_state.danger_v = float(d.get("danger_v", CONFIG["DEFAULT_DANGER_V"]))
                st.session_state.sel_dirs = d.get("sel_dirs", CONFIG["DEFAULT_DIRS"])
                st.session_state.show_temp = d.get("show_temp", True)
                st.session_state.show_tide = d.get("show_tide", True)
                st.session_state.initialized = True
                st.rerun()
            except: st.session_state.initialized = True
        elif stored_data == "": st.session_state.initialized = True
        if "initialized" not in st.session_state: st.stop()

    # 保存処理
    save_obj = {
        "lat": st.session_state.lat, "lon": st.session_state.lon, "basho": st.session_state.last_basho,
        "sel_map_lat": st.session_state.get("sel_map_lat", st.session_state.lat),
        "sel_map_lon": st.session_state.get("sel_map_lon", st.session_state.lon),
        "danger_v": st.session_state.get("danger_v", CONFIG["DEFAULT_DANGER_V"]),
        "sel_dirs": st.session_state.get("sel_dirs", CONFIG["DEFAULT_DIRS"]),
        "show_temp": st.session_state.get("show_temp", True),
        "show_tide": st.session_state.get("show_tide", True)
    }
    streamlit_js_eval(js_expressions=f"localStorage.setItem('{CONFIG['STORAGE_KEY']}', '{json.dumps(save_obj)}')", key="save_storage")

#==========================================================================================
# 地図UI（3x3格子レイアウト）を表示するサブルーチン
#==========================================================================================
def render_3x3_map_ui():
    """仕様書 2.2項 3x3格子レイアウトを実装"""
    st.info("地図の中央地点の座標を取得します。")
    
    col_l, col_m, col_r = st.columns([1, 4, 1])
    
    with col_m:
        if st.button("▲", use_container_width=True): st.session_state.sel_map_lat += CONFIG["MAP_MOVE_STEP"]; st.rerun()
    
    col_l2, col_m2, col_r2 = st.columns([1, 4, 1])
    with col_l2:
        st.write(" ") # 垂直位置調整
        if st.button("◀", use_container_width=True): st.session_state.sel_map_lon -= CONFIG["MAP_MOVE_STEP"]; st.rerun()
    with col_m2:
        m = folium.Map(location=[st.session_state.sel_map_lat, st.session_state.sel_map_lon], zoom_start=14)
        folium.Marker([st.session_state.sel_map_lat, st.session_state.sel_map_lon]).add_to(m)
        st_folium(m, width=500, height=CONFIG["MAP_HEIGHT"], key="folium_map")
    with col_r2:
        st.write(" ")
        if st.button("▶", use_container_width=True): st.session_state.sel_map_lon += CONFIG["MAP_MOVE_STEP"]; st.rerun()

    with col_m:
        if st.button("▼", use_container_width=True): st.session_state.sel_map_lat -= CONFIG["MAP_MOVE_STEP"]; st.rerun()

    if st.button("グラフ描画地点確定", use_container_width=True):
        st.session_state.lat = st.session_state.sel_map_lat
        st.session_state.lon = st.session_state.sel_map_lon
        st.session_state.last_basho = "地図で指定"
        st.rerun()

#==========================================================================================
# データ取得・処理サブルーチン群
#==========================================================================================
def fetch_weather_data(lat, lon):
    url = f"https://api.open-meteo.com/v1/forecast?latitude={lat}&longitude={lon}&hourly=temperature_2m,wind_speed_10m,wind_direction_10m,weather_code&timezone=Asia%2FTokyo&wind_speed_unit=ms&forecast_days={CONFIG['FORECAST_DAYS']}"
    try:
        data = requests.get(url).json()
        df = pd.DataFrame(data["hourly"])
        df['time'] = pd.to_datetime(df['time'])
        return df
    except: return None

def get_tide_level(times):
    base_full_tide = datetime(2025, 1, 1, 6, 0)
    cycle_hours = 12.42
    return [100 * np.cos(2 * np.pi * ((t - base_full_tide).total_seconds() / 3600) / cycle_hours) if not pd.isna(t) else np.nan for t in times]

def get_weather_info(code):
    if pd.isna(code): return "", "black"
    if code <= 2: return "晴", "#FF4500"
    if code <= 48: return "曇", "#696969"
    return "雨", "#00008B"

def process_wind_data(df, target_dirs):
    dirs = ALL_DIRECTIONS + ["北"]
    arrows = ["↓", "↙", "↙", "↙", "←", "↖", "↖", "↖", "↑", "↗", "↗", "↗", "→", "↘", "↘", "↘", "↓"]
    def judge(row):
        s = row['wind_speed_10m']
        idx = int((row['wind_direction_10m'] + 11.25) / 22.5) % 16
        dn = dirs[idx]
        if s < 3.0 or dn not in target_dirs: return "#D3D3D3", dn, arrows[idx]
        if s >= 10.0: return "crimson", dn, arrows[idx]
        return ("orange" if s >= 5.0 else "skyblue"), dn, arrows[idx]

    res = df.apply(judge, axis=1)
    df['color'], df['dir_name'], df['arrow'] = zip(*res)
    df['tide_level'] = get_tide_level(df['time'])
    w_info = df['weather_code'].apply(get_weather_info)
    df['w_text'], df['w_color'] = zip(*w_info)
    return df

#==========================================================================================
# グラフ描画サブルーチン群
#==========================================================================================
def render_wind_chart(ax, df, danger_v):
    bars = ax.bar(df['time'], df['wind_speed_10m'], color=df['color'], alpha=0.9, width=0.035)
    ax.axhline(y=danger_v, color='red', linestyle='--', linewidth=2)
    ax.set_ylabel('風速 (m/s)')
    fs, step, base = CONFIG["ANNOT_SIZE"], CONFIG["ANNOT_Y_STEP"], CONFIG["ANNOT_BASE_Y"]
    for i, bar in enumerate(bars):
        if i % 3 == 0:
            r = df.iloc[i]
            if pd.isna(r['wind_speed_10m']): continue
            by = bar.get_height()
            x = bar.get_x() + bar.get_width()/2.
            ax.text(x, by + base, f"{r['wind_speed_10m']:.0f}", ha='center', va='bottom', fontsize=fs-2)
            ax.text(x, by + base + step, r['arrow'], ha='center', va='bottom', fontsize=fs+2, fontweight='bold')
            ax.text(x, by + base + step*2, r['dir_name'], ha='center', va='bottom', fontsize=fs-2)
            ax.text(x, by + base + step*3, r['w_text'], ha='center', va='bottom', color=r['w_color'], fontweight='bold', fontsize=fs-1)

@st.cache_data(show_spinner="生成中...")
def generate_graph_image(lat, lon, danger_v, sel_dirs, show_temp, show_tide):
    df = fetch_weather_data(lat, lon)
    if df is None: return None
    pad = pd.DataFrame({'time': [df['time'].iloc[0] - timedelta(hours=i) for i in range(1, CONFIG["PADDING_HOURS"]+1)][::-1]})
    df = pd.concat([pad, df], ignore_index=True)
    df = process_wind_data(df, list(sel_dirs))
    
    fig, axes = plt.subplots(3, 1, figsize=(40, 11), dpi=CONFIG["DPI"], gridspec_kw={'height_ratios': CONFIG["HEIGHT_RATIOS"]})
    plt.subplots_adjust(hspace=0.6)
    now_jst = datetime.now(timezone(timedelta(hours=9))).replace(tzinfo=None)
    
    render_wind_chart(axes[0], df, danger_v)
    if show_temp:
        axes[1].plot(df['time'], df['temperature_2m'], color='#333333', linewidth=2, marker='o', markersize=3, markevery=3)
        axes[1].set_ylabel('気温 (℃)')
    if show_tide:
        axes[2].plot(df['time'], df['tide_level'], color='royalblue', linewidth=2.5)
        axes[2].fill_between(df['time'], df['tide_level'], -110, color='royalblue', alpha=0.15)
        axes[2].set_ylabel('潮位')

    jp_weeks = ["月", "火", "水", "木", "金", "土", "日"]
    def fmt(x, p):
        dt = mdates.num2date(x)
        return dt.strftime('%m/%d') + f'\n({jp_weeks[dt.weekday()]})\n' + dt.strftime('%H:%M') if dt.hour == 0 else dt.strftime('%H:%M') if dt.hour in [3,9,15,21] else ""

    for ax in axes:
        ax.axvline(now_jst, color='blue', linestyle='-', alpha=0.6, linewidth=2.5)
        ax.xaxis.set_major_locator(mdates.HourLocator(byhour=range(0, 24, 3)))
        ax.xaxis.set_major_formatter(plt.FuncFormatter(fmt))
        ax.set_xlim(df['time'].iloc[0], df['time'].iloc[-1])
        ax.grid(True, which='major', linestyle=':', alpha=0.6)

    buf = io.BytesIO()
    fig.savefig(buf, format="png", bbox_inches='tight')
    plt.close(fig)
    return base64.b64encode(buf.getvalue()).decode()

#==========================================================================================
# メイン・UI制御
#==========================================================================================
def main():
    setup_font()
    st.markdown(f'<h1 style="font-size:{CONFIG["TITLE_SIZE"]}px;">⛵ 高須風チェッカー</h1>', unsafe_allow_html=True)
    
    if 'lat' not in st.session_state: st.session_state.lat = CONFIG["DEFAULT_LAT"]
    if 'lon' not in st.session_state: st.session_state.lon = CONFIG["DEFAULT_LON"]
    if 'last_basho' not in st.session_state: st.session_state.last_basho = CONFIG["DEFAULT_BASHO"]
    if 'sel_map_lat' not in st.session_state: st.session_state.sel_map_lat = CONFIG["DEFAULT_LAT"]
    if 'sel_map_lon' not in st.session_state: st.session_state.sel_map_lon = CONFIG["DEFAULT_LON"]

    sync_storage_spec_2025()

    master = {
        "高須沖(鹿児島県)":(31.337, 130.795), "柏原沖(鹿児島県)":(31.380, 131.020), 
        "垂水港(鹿児島県)":(31.478, 130.668), "海潟(鹿児島県)":(31.539, 130.706), 
        "地図で指定": (st.session_state.lat, st.session_state.lon)
    }
    
    basho = st.selectbox("地点を選択してください", list(master.keys()), index=list(master.keys()).index(st.session_state.last_basho) if st.session_state.last_basho in master else 0)
    
    if basho != st.session_state.last_basho:
        st.session_state.last_basho = basho
        if basho != "地図で指定":
            st.session_state.lat, st.session_state.lon = master[basho]
        else: st.session_state.show_map = True
        st.rerun()

    show_map = st.checkbox("地図表示", value=st.session_state.get('show_map', False))
    st.session_state.show_map = show_map
    if show_map: render_3x3_map_ui()

    now = datetime.now(timezone(timedelta(hours=9)))
    st.markdown(f"<p style='font-size:{CONFIG['LOC_INFO_FONT_SIZE']}; color:{CONFIG['LOC_INFO_COLOR']}; font-weight:bold;'>📍 現在：{st.session_state.last_basho} ({st.session_state.lat:.4f}, {st.session_state.lon:.4f})<br><span style='font-size:12px; color:gray;'>取得時刻: {now.strftime('%Y/%m/%d %H:%M:%S')}</span></p>", unsafe_allow_html=True)
    
    # サイドバー
    st.sidebar.header("表示設定")
    dv = st.sidebar.number_input("危険風速ライン", value=st.session_state.get("danger_v", 12.0))
    st.session_state.danger_v = dv
    st.session_state.show_temp = st.sidebar.checkbox("気温グラフ表示", value=st.session_state.get("show_temp", True))
    st.session_state.show_tide = st.sidebar.checkbox("潮位グラフ表示", value=st.session_state.get("show_tide", True))
    
    st.sidebar.write("色付風向")
    sd = st.session_state.get("sel_dirs", CONFIG["DEFAULT_DIRS"])
    new_dirs = [d for d in ALL_DIRECTIONS if st.sidebar.checkbox(d, value=(d in sd), key=f"c_{d}")]
    st.session_state.sel_dirs = new_dirs
    
    if st.button("🔄 グラフ更新"): st.cache_data.clear(); st.rerun()

    img = generate_graph_image(st.session_state.lat, st.session_state.lon, dv, tuple(new_dirs), st.session_state.show_temp, st.session_state.show_tide)
    if img:
        st.markdown(f'<div style="overflow-x: auto; background: white;"><img src="data:image/png;base64,{img}" style="height: 850px; max-width: none;"></div>', unsafe_allow_html=True)
    
    st.sidebar.markdown("---")
    st.sidebar.caption("※設定はブラウザのローカルストレージに保存されます。")

if __name__ == "__main__":
    main()

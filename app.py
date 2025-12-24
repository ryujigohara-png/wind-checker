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

# ======================================================================================
# 1. 定数・基本設定 (仕様通りのCONFIG)
# ======================================================================================
CONFIG = {
    "TITLE_SIZE": 22,
    "SUBTITLE_SIZE": 16,
    "GRAPH_FONT_SIZE": 12,
    "LABEL_SIZE": 12,
    "DPI": 300,
    "MAP_HEIGHT": 350
}

ALL_DIRECTIONS = ["北", "北北東", "北東", "東北東", "東", "東南東", "南東", "南南東", "南", "南南西", "南西", "西南西", "西", "西北西", "北西", "北北西"]

# ======================================================================================
# 2. 補助サブルーチン
# ======================================================================================
def setup_font():
    font_url = "https://github.com/google/fonts/raw/main/ofl/notosansjp/NotoSansJP%5Bwght%5D.ttf"
    font_path = "NotoSansJP.ttf"
    if not os.path.exists(font_path):
        urllib.request.urlretrieve(font_url, font_path)
    fm.fontManager.addfont(font_path)
    plt.rc('font', family='Noto Sans JP', size=CONFIG["GRAPH_FONT_SIZE"])

def fetch_weather_data(lat, lon, days):
    url = f"https://api.open-meteo.com/v1/forecast?latitude={lat}&longitude={lon}&hourly=temperature_2m,wind_speed_10m,wind_direction_10m,weather_code&timezone=Asia%2FTokyo&wind_speed_unit=ms&forecast_days={days}"
    try:
        data = requests.get(url).json()
        df = pd.DataFrame(data["hourly"])
        df['time'] = pd.to_datetime(df['time'])
        # 【仕様】3時間空白パディング
        first_time = df['time'].iloc[0]
        padding = pd.DataFrame({
            'time': [first_time - timedelta(hours=i) for i in range(3, 0, -1)],
            'temperature_2m': [None]*3, 'wind_speed_10m': [None]*3, 'wind_direction_10m': [None]*3, 'weather_code': [None]*3
        })
        return pd.concat([padding, df], ignore_index=True)
    except: return None

def get_weather_info(code):
    if code is None: return "", "black"
    if code <= 2: return "晴", "#FF4500" # 【仕様】濃いオレンジ
    if code <= 48: return "曇", "#696969"
    if code <= 99: return "雨", "#00008B" # 【仕様】濃い青
    return "？", "black"

def process_wind_data(df, target_dirs, danger_v):
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
        if pd.isna(speed): return "none"
        if speed >= danger_v: return "crimson"
        if row['dir_name'] in target_dirs:
            if 6 <= speed < danger_v: return "orange"
            if 3 <= speed < 6: return "skyblue"
        return "#D3D3D3"
    df['color'] = df.apply(judge, axis=1)
    base_full_tide = datetime(2025, 1, 1, 6, 0)
    df['tide_level'] = df['time'].apply(lambda t: 100 * np.cos(2 * np.pi * (t - base_full_tide).total_seconds() / 3600 / 12.42) if pd.notna(t) else None)
    return df

# ======================================================================================
# 3. グラフ生成
# ======================================================================================
@st.cache_data(show_spinner=False)
def get_cached_graph(lat, lon, days, danger_v, selected_dirs_tuple):
    df = fetch_weather_data(lat, lon, days)
    if df is None: return None
    df = process_wind_data(df, list(selected_dirs_tuple), danger_v)
    wind_step = (1 if days <= 1 else (2 if days <= 3 else 3))
    time_step = (3 if days <= 2 else 6)
    fig_w = max(10, days * 4.5)
    fig, (ax1, ax2, ax3) = plt.subplots(3, 1, figsize=(fig_w, 10), dpi=CONFIG["DPI"], gridspec_kw={'height_ratios': [4.2, 1.2, 1.0]})
    plt.subplots_adjust(hspace=0.6)
    jp_weeks = ["月", "火", "水", "木", "金", "土", "日"]
    def formatter(x, p):
        dt = mdates.num2date(x)
        if dt.hour == 0: return dt.strftime('%m/%d') + f'\n({jp_weeks[dt.weekday()]})\n' + dt.strftime('%H:%M')
        else: return dt.strftime('%H:%M')
    
    bars = ax1.bar(df['time'], df['wind_speed_10m'], color=df['color'], alpha=0.9, width=0.03)
    ax1.axhline(y=danger_v, color='red', linestyle='--', alpha=0.6)
    ax1.set_ylabel('風速 (m/s)')
    max_val = df['wind_speed_10m'].max() if not df['wind_speed_10m'].empty else 0
    y_limit = max(max_val, danger_v) + 5
    ax1.set_ylim(0, y_limit)
    text_offset_weather = y_limit * 0.20 
    text_offset_wind = y_limit * 0.02
    now_jst = datetime.now(timezone(timedelta(hours=9))).replace(tzinfo=None)
    for ax in [ax1, ax2, ax3]:
        ax.axvline(now_jst, color='blue', linestyle='-', alpha=0.6, linewidth=2.5)
        ax.xaxis.set_major_locator(mdates.HourLocator(byhour=range(0, 24, time_step)))
        ax.xaxis.set_major_formatter(plt.FuncFormatter(formatter))
        ax.set_xlim(df['time'].iloc[0], df['time'].iloc[-1])
        ax.grid(True, linestyle=':', alpha=0.4, color='#000000')

    ax2.plot(df['time'], df['temperature_2m'], color='black', linewidth=1.5)
    ax2.set_ylabel('気温(℃)')
    ax3.plot(df['time'], df['tide_level'], color='royalblue', linewidth=2)
    ax3.fill_between(df['time'], df['tide_level'], -120, color='royalblue', alpha=0.2)
    ax3.set_ylabel('潮位'); ax3.set_yticks([])

    for i, bar in enumerate(bars):
        if not pd.isna(df['wind_speed_10m'].iloc[i]) and i % wind_step == 0:
            h = bar.get_height()
            ax1.text(bar.get_x() + bar.get_width()/2., h + text_offset_weather, df['w_text'].iloc[i], ha='center', va='bottom', color=df['w_color'].iloc[i], fontweight='bold', fontsize=CONFIG["GRAPH_FONT_SIZE"])
            txt = f"{df['dir_name'].iloc[i]}\n{df['arrow'].iloc[i]}\n{round(df['wind_speed_10m'].iloc[i])}m"
            ax1.text(bar.get_x() + bar.get_width()/2., h + text_offset_wind, txt, ha='center', va='bottom', fontweight='bold', color='black', fontsize=CONFIG["GRAPH_FONT_SIZE"])

    buf = io.BytesIO(); fig.savefig(buf, format="png", bbox_inches='tight', pad_inches=0.1)
    return base64.b64encode(buf.getvalue()).decode()

# ======================================================================================
# 4. 地図UI (3x3マトリックス仕様)
# ======================================================================================
def show_location_map():
    st.info("地図の中央地点を確定できます。")
    m = folium.Map(location=[st.session_state.lat, st.session_state.lon], zoom_start=13)
    folium.Marker([st.session_state.lat, st.session_state.lon], icon=folium.Icon(color='red')).add_to(m)
    col_l1, col_m1, col_r1 = st.columns([1, 18, 1])
    with col_m1: st.markdown("<div style='color:crimson; font-size:24px; font-weight:bold; text-align:center;'>▼</div>", unsafe_allow_html=True)
    col_l2, col_m2, col_r2 = st.columns([1, 18, 1])
    with col_l2: st.markdown(f"<div style='line-height:{CONFIG['MAP_HEIGHT']}px; text-align:right; color:crimson; font-size:24px; font-weight:bold;'>▶</div>", unsafe_allow_html=True)
    with col_m2: map_out = st_folium(m, width=None, height=CONFIG["MAP_HEIGHT"], key=f"map_{st.session_state.lat}", returned_objects=["center"])
    with col_r2: st.markdown(f"<div style='line-height:{CONFIG['MAP_HEIGHT']}px; text-align:left; color:crimson; font-size:24px; font-weight:bold;'>◀</div>", unsafe_allow_html=True)
    col_l3, col_m3, col_r3 = st.columns([1, 18, 1])
    with col_m3: st.markdown("<div style='color:crimson; font-size:24px; font-weight:bold; text-align:center;'>▲</div>", unsafe_allow_html=True)
    
    if map_out and map_out.get("center"):
        if st.button("グラフ描画地点（地図中央）確定", use_container_width=True):
            st.session_state.lat, st.session_state.lon = map_out["center"]["lat"], map_out["center"]["lng"]
            st.session_state.last_basho = "地図で指定"
            # 地図座標も記憶
            js_save = f"""<script>localStorage.setItem('wind_checker_basho', '地図で指定'); localStorage.setItem('wind_checker_lat', '{st.session_state.lat}'); localStorage.setItem('wind_checker_lon', '{st.session_state.lon}');</script>"""
            components.html(js_save, height=0)
            st.rerun()

# ======================================================================================
# 5. メインアプリ
# ======================================================================================
def main():
    setup_font()
    st.markdown(f'<h1 style="font-size:{CONFIG["TITLE_SIZE"]}px; margin-bottom: 5px;">⛵ 高須風チェッカー</h1>', unsafe_allow_html=True)
    
    coords_m = {
        "高須沖(鹿児島県)":(31.337, 130.795), "柏原沖(鹿児島県)":(31.380, 131.020), "垂水港(鹿児島県)":(31.478, 130.668),
        "海潟(鹿児島県)":(31.539, 130.706), "磯海岸沖(鹿児島県)":(31.614, 130.577), "江口浜沖(鹿児島県)":(31.643, 130.322),
        "錦江湾(鹿児島県)":(31.590, 130.600), "地図で指定": (None, None)
    }

    # --- 端末記憶の自動読み取り ---
    # ブラウザのlocalStorageに値があればURLパラメータを書き換えてリロード（初回のみ）
    if "init_loaded" not in st.session_state:
        components.html("""
            <script>
            const b = localStorage.getItem('wind_checker_basho');
            const url = new URL(window.location.href);
            if (b && url.searchParams.get('basho') !== b) {
                url.searchParams.set('basho', b);
                window.location.href = url.href;
            }
            </script>
        """, height=0)
        st.session_state.init_loaded = True

    # URLパラメータから地点を決定
    q_basho = st.query_params.get("basho", "高須沖(鹿児島県)")
    if q_basho not in coords_m: q_basho = "高須沖(鹿児島県)"
    
    # セッション状態をURLに同期
    if 'last_basho' not in st.session_state or st.session_state.last_basho != q_basho:
        st.session_state.last_basho = q_basho
        st.session_state.lat, st.session_state.lon = coords_m[q_basho]

    # UIコンポーネント
    basho = st.selectbox("地点を選択", list(coords_m.keys()), index=list(coords_m.keys()).index(st.session_state.last_basho))
    show_map = st.checkbox("地図表示", value=st.session_state.get('show_map_state', False))
    st.session_state.show_map_state = show_map
    
    st.markdown(f"📍 現在：**{st.session_state.last_basho}** ({st.session_state.lat:.4f}, {st.session_state.lon:.4f})")

    # 地点変更時の処理
    if basho != st.session_state.last_basho:
        lat, lon = coords_m[basho]
        components.html(f"""
            <script>
            localStorage.setItem('wind_checker_basho', '{basho}');
            const url = new URL(window.location.href);
            url.searchParams.set('basho', '{basho}');
            window.location.href = url.href;
            </script>
        """, height=0)
        st.stop() # JSのリロードを待つ

    if show_map:
        show_location_map()
    
    # サイドバー
    st.sidebar.header("表示設定")
    days = st.sidebar.slider("表示日数", 1, 8, 8)
    danger_v = st.sidebar.number_input("危険風速(m/s)", value=10.0)
    st.sidebar.header("乗れる風向")
    sel_dirs = [d for d in ALL_DIRECTIONS if st.sidebar.checkbox(d, value=(d in ["南", "南西", "西", "北西"]), key=f"sidebar_{d}")]

    # グラフ描画
    img = get_cached_graph(st.session_state.lat, st.session_state.lon, days, danger_v, tuple(sel_dirs))
    if img:
        st.markdown(f'<div style="overflow-x: auto; background: white;"><img src="data:image/png;base64,{img}" style="height: 900px; max-width: none;"></div>', unsafe_allow_html=True)

if __name__ == "__main__":
    main()

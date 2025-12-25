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
    "ANNOT_Y_STEP": 1.5,
    "ANNOT_BASE_Y": 0.5,
    "STORAGE_KEY_LAT": "wind_checker_lat",
    "STORAGE_KEY_LON": "wind_checker_lon",
    "STORAGE_KEY_BASHO": "wind_checker_basho",
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
def sync_settings_with_local_storage():
    """
    ブラウザのLocalStorageから設定を読み込み、SessionStateに反映、
    およびSessionStateの変化をLocalStorageに書き込むJavaScriptを注入する。
    """
    # 1. ブラウザから読み込み、SessionStateに未定義の場合のみ適用するJS
    # 2. 現在のSessionStateの値をLocalStorageに保存するJS
    storage_js = f"""
    <script>
    (function() {{
        const KEY_LAT = "{CONFIG['STORAGE_KEY_LAT']}";
        const KEY_LON = "{CONFIG['STORAGE_KEY_LON']}";
        const KEY_BASHO = "{CONFIG['STORAGE_KEY_BASHO']}";

        // 保存処理
        const currentLat = "{st.session_state.lat}";
        const currentLon = "{st.session_state.lon}";
        const currentBasho = "{st.session_state.last_basho}";

        if (currentBasho !== "{CONFIG['DEFAULT_BASHO']}" || currentLat !== "{CONFIG['DEFAULT_LAT']}") {{
            localStorage.setItem(KEY_LAT, currentLat);
            localStorage.setItem(KEY_LON, currentLon);
            localStorage.setItem(KEY_BASHO, currentBasho);
        }}

        // 読み込み処理（StreamlitのURLパラメータを利用してSessionStateへ擬似的に戻す手法は複雑なため、
        // 初回ロード時にJS側でコンボボックス等のDOMを直接操作するか、
        // StreamlitのQueryParam機能と連携するのが一般的ですが、
        // ここでは最も確実にLocalStorageへ「書き込まれる」ことを優先して修正します）
    }})();
    </script>
    """
    # components.html ではなく st.components.v1.html で直接実行
    components.html(storage_js, height=0)

#==========================================================================================
# 起動時に一度だけLocalStorageから値をSessionStateに復元するサブルーチン
#==========================================================================================
def restore_from_local_storage():
    """
    起動時にLocalStorageの値を読み取るための隠しコンポーネント。
    Streamlitの初回実行時にJSから値を受け取る。
    """
    # この処理には streamlit_js_eval などの外部ライブラリが最適ですが、
    # 標準機能で実現するために、読み取り専用のJSを埋め込みます。
    get_storage_js = f"""
        <script>
        const lat = localStorage.getItem("{CONFIG['STORAGE_KEY_LAT']}");
        const lon = localStorage.getItem("{CONFIG['STORAGE_KEY_LON']}");
        const basho = localStorage.getItem("{CONFIG['STORAGE_KEY_BASHO']}");
        
        if (lat && lon && basho) {{
            const url = new URL(window.location.href);
            if (!url.searchParams.has('lat')) {{
                url.searchParams.set('lat', lat);
                url.searchParams.set('lon', lon);
                url.searchParams.set('basho', basho);
                window.parent.location.href = url.href;
            }}
        }}
        </script>
    """
    # クエリパラメータによる復元を試みる（これが最も確実です）
    params = st.query_params
    if "lat" in params and st.session_state.get('initial_sync') is None:
        st.session_state.lat = float(params["lat"])
        st.session_state.lon = float(params["lon"])
        st.session_state.last_basho = params["basho"]
        st.session_state.initial_sync = True
    
    components.html(get_storage_js, height=0)
    
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
# 指定された時間リストに基づき簡易的な潮位を計算するサブルーチン
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
# 天気コードを日本語の名称と表示用の色に変換するサブルーチン
#==========================================================================================
def get_weather_info(code):
    if pd.isna(code): return "", "black"
    if code <= 2: return "晴", "#FF4500"
    if code <= 48: return "曇", "#696969"
    if code <= 99: return "雨", "#00008B"
    return "？", "black"

#==========================================================================================
# 風向角度を名称と矢印に変換し、条件に基づきグラフの色を判定するサブルーチン
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
# グラフのX軸ラベルを千鳥形式（3,9,15,21時を1行下げる）でフォーマットするサブルーチン
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
# 共通の軸設定（1h補助目盛・3h主要ラベル）を適用するサブルーチン
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
# 風速棒グラフ（着色・垂直アノテーション）を描画するサブルーチン
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
# 気温チャートを描画するサブルーチン
#==========================================================================================
def render_temp_line_chart(ax, df):
    ax.plot(df['time'], df['temperature_2m'], color='#333333', linewidth=2, marker='o', markersize=3, markevery=3)
    ax.set_ylabel('気温 (℃)', fontsize=CONFIG["LABEL_SIZE"])
    valid_temp = df['temperature_2m'].dropna()
    if not valid_temp.empty:
        ax.set_ylim(valid_temp.min() - 2, valid_temp.max() + 2)

#==========================================================================================
# 潮位チャートを描画するサブルーチン
#==========================================================================================
def render_tide_curve_chart(ax, df):
    ax.plot(df['time'], df['tide_level'], color='royalblue', linewidth=2.5)
    ax.fill_between(df['time'], df['tide_level'], -110, color='royalblue', alpha=0.15)
    ax.set_ylabel('潮位', fontsize=CONFIG["LABEL_SIZE"])
    ax.set_ylim(-120, 120)
    ax.set_yticks([])

#==========================================================================================
# 8日間の予測に基づき高解像度グラフ画像を生成するサブルーチン
#==========================================================================================
@st.cache_data(show_spinner="グラフを生成中...")
def generate_high_res_graph(lat, lon, danger_v, selected_dirs_tuple):
    days = 8
    df = fetch_weather_data(lat, lon, days)
    if df is None: return None
    padding_times = [df['time'].iloc[0] - timedelta(hours=i) for i in range(1, 4)][::-1]
    padding_df = pd.DataFrame({'time': padding_times})
    df = pd.concat([padding_df, df], ignore_index=True)
    df = process_wind_data(df, list(selected_dirs_tuple))
    fig_w = 40 
    fig, (ax1, ax2, ax3) = plt.subplots(3, 1, figsize=(fig_w, 11), dpi=CONFIG["DPI"], gridspec_kw={'height_ratios': CONFIG["HEIGHT_RATIOS"]})
    plt.subplots_adjust(hspace=0.6)
    formatter = get_x_axis_formatter()
    now_jst = datetime.now(timezone(timedelta(hours=9))).replace(tzinfo=None)
    render_wind_bar_chart(ax1, df, danger_v, 3)
    render_temp_line_chart(ax2, df)
    render_tide_curve_chart(ax3, df)
    for ax in [ax1, ax2, ax3]:
        apply_common_axis_settings(ax, df, formatter, now_jst)
    buf = io.BytesIO()
    fig.savefig(buf, format="png", bbox_inches='tight', pad_inches=0.1)
    plt.close(fig) 
    return base64.b64encode(buf.getvalue()).decode()

#==========================================================================================
# 地図表示サブルーチン（3x3格子・全幅中央・スマホ崩れ回避）
#==========================================================================================
def show_location_map():
    st.info("地図の中央地点のグラフを描画表示することができます。")
    st.markdown("""<style>
        div[data-testid="stHorizontalBlock"] { flex-wrap: nowrap !important; justify-content: center !important; }
        [data-testid="column"] { min-width: 0px !important; }
        .guide-mark { color: #eee; font-size: 10px; text-align: center; }
        .guide-arrow-main { color: crimson; font-size: 24px; font-weight: bold; text-align: center; }
        </style>""", unsafe_allow_html=True)
    m = folium.Map(location=[st.session_state.lat, st.session_state.lon], zoom_start=13)
    folium.Marker([st.session_state.lat, st.session_state.lon], icon=folium.Icon(color='red')).add_to(m)
    col_l1, col_m1, col_r1 = st.columns([1, 18, 1])
    with col_l1: st.markdown("<div class='guide-mark'>┼</div>", unsafe_allow_html=True)
    with col_m1: st.markdown("<div class='guide-arrow-main' style='display: flex; align-items: flex-end; justify-content: center; height: 40px;'>▼</div>", unsafe_allow_html=True)
    with col_r1: st.markdown("<div class='guide-mark'>┼</div>", unsafe_allow_html=True)
    col_l2, col_m2, col_r2 = st.columns([1, 18, 1])
    with col_l2: st.markdown(f"<div style='line-height:{CONFIG['MAP_HEIGHT']}px; text-align:right;' class='guide-arrow-main'>▶</div>", unsafe_allow_html=True)
    with col_m2: map_out = st_folium(m, width=None, height=CONFIG["MAP_HEIGHT"], key=f"map_{st.session_state.lat}", returned_objects=["center"])
    with col_r2: st.markdown(f"<div style='line-height:{CONFIG['MAP_HEIGHT']}px; text-align:left;' class='guide-arrow-main'>◀</div>", unsafe_allow_html=True)
    col_l3, col_m3, col_r3 = st.columns([1, 18, 1])
    with col_l3: st.markdown("<div class='guide-mark'>┼</div>", unsafe_allow_html=True)
    with col_m3: st.markdown("<div class='guide-arrow-main' style='display: flex; align-items: flex-start; justify-content: center; height: 40px; margin-top:-10px;'>▲</div>", unsafe_allow_html=True)
    with col_r3: st.markdown("<div class='guide-mark'>┼</div>", unsafe_allow_html=True)
    if map_out and map_out.get("center"):
        if st.button("グラフ描画地点確定", use_container_width=True):
            st.session_state.lat, st.session_state.lon = map_out["center"]["lat"], map_out["center"]["lng"]
            st.session_state.last_basho = "地図で指定"
            st.rerun()

#==========================================================================================
# 5.1/5.2 サイドバー設定項目を表示するサブルーチン
#==========================================================================================
def show_sidebar_controls():
    st.sidebar.header("表示設定")
    danger_v = st.sidebar.number_input("危険風速ライン(m/s)", value=12.0, step=0.5)
    st.sidebar.write("色付風向（3-10m/sで着色）")
    init_dirs = ["南","南南西","南西","西南西","西","西北西","北西","北北西"]
    sel_dirs = []
    cols = st.sidebar.columns(2)
    for i, d in enumerate(ALL_DIRECTIONS):
        with cols[i % 2]:
            if st.checkbox(d, value=(d in init_dirs), key=f"chk_{d}"):
                sel_dirs.append(d)
    st.sidebar.markdown("---")
    return danger_v, sel_dirs

#==========================================================================================
# アプリケーションの初期化とメインフロー制御を行うサブルーチン
#==========================================================================================
def main():
    setup_font()
    st.markdown(f'<h1 style="font-size:{CONFIG["TITLE_SIZE"]}px;">⛵ 高須風チェッカー</h1>', unsafe_allow_html=True)
    
    # 1. LocalStorageからの復元（クエリパラメータ経由）
    restore_from_local_storage()

    # 2. 初期値セット
    # SessionStateの初期化（LocalStorage同期を考慮）
    if 'lat' not in st.session_state: st.session_state.lat = CONFIG["DEFAULT_LAT"]
    if 'lon' not in st.session_state: st.session_state.lon = CONFIG["DEFAULT_LON"]
    if 'last_basho' not in st.session_state: st.session_state.last_basho = CONFIG["DEFAULT_BASHO"]
    
    # 3. 現在の状態をLocalStorageに保存
    # ブラウザLocalStorageとの同期実行
    sync_settings_with_local_storage()

    master = {
        "高須沖(鹿児島県)":(31.337, 130.795), "柏原沖(鹿児島県)":(31.380, 131.020), 
        "垂水港(鹿児島県)":(31.478, 130.668), "海潟(鹿児島県)":(31.539, 130.706), 
        "磯海岸沖(鹿児島県)":(31.614, 130.577), "江口浜沖(鹿児島県)":(31.643, 130.322),
        "錦江湾(鹿児島県)":(31.590, 130.600), "地図で指定": (None, None)
    }
    
    basho = st.selectbox("地点を選択してください", list(master.keys()), 
                         index=list(master.keys()).index(st.session_state.last_basho) if st.session_state.last_basho in master else 0)
    
    if basho != st.session_state.last_basho:
        st.session_state.last_basho = basho
        if basho != "地図で指定":
            st.session_state.lat, st.session_state.lon = master[basho]
            st.session_state.show_map_state = False
        else:
            st.session_state.show_map_state = True
        st.rerun()

    show_map = st.checkbox("地図表示", value=st.session_state.get('show_map_state', False))
    st.session_state.show_map_state = show_map
    
    st.markdown(f"<p style='font-size:{CONFIG['LOC_INFO_FONT_SIZE']}; color:{CONFIG['LOC_INFO_COLOR']}; font-weight:bold;'>📍 現在：{st.session_state.last_basho} ({st.session_state.lat:.4f}, {st.session_state.lon:.4f})</p>", unsafe_allow_html=True)
    
    if show_map:
        show_location_map()
    
    danger_v, sel_dirs = show_sidebar_controls()

    img = generate_high_res_graph(st.session_state.lat, st.session_state.lon, danger_v, tuple(sel_dirs))
    if img:
        with st.expander("📊 凡例"):
            st.write(f"■ 3-5m(青) ■ 5-10m(橙) ■ 10m以上(赤) --- [点線: 危険風速ライン {danger_v}m/s]")
        st.markdown(f'<div style="overflow-x: auto; background: white;"><img src="data:image/png;base64,{img}" style="height: 850px; max-width: none;"></div>', unsafe_allow_html=True)

if __name__ == "__main__":
    main()

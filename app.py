# -*- coding: utf-8 -*-
# 最終更新 2025.12.29 0210 ベータ版完全統合・UI復元・デザイン調整連動版
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
    "GRAPH_FONT_SIZE": 12,       # 12に変更
    "GRAPH_WIDTH": 20,
    "GRAPH_HIGHT": 3.0,          # 3.0に変更
    "LABEL_SIZE": 9,
    "LABEL_PAD": 0,              # 0に変更
    "ANNOT_SIZE": 10,
    "DPI": 200,
    "MAP_HEIGHT": 350,
    "DEFAULT_RATIOS": [4.4, 1.2, 0.8],
    "SHOW_WIND": True,
    "SHOW_TEMP": True,
    "SHOW_TIDE": False,          # NO(False)に変更
    "SHOW_W_TEXT": False,        # NO(False)に変更
    "SHOW_DIR_NAME": False,      # NO(False)に変更
    "HSPACE": 0.1,
    "DEFAULT_LAT": 31.337,
    "DEFAULT_LON": 130.795,
    "DEFAULT_BASHO": "高須沖(鹿児島県)",
    "DEFAULT_DANGER_V": 10.0,
    "DEFAULT_DIRS": ["南","南南西","南西","西南西","西","西北西","北西","北北西"],
    "ANNOT_Y_STEP": 1.5,
    "ANNOT_BASE_Y": 0.5,
    "STORAGE_KEY": "wind_checker_settings",
    "TEMP_COLOR": "darkorange",
    "ARROW_COLOR": "blue",
    "VLINE_WIDTH": 1.25,
    "HLINE_WIDTH": 1.0,
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
            # 0時の場合：時刻を表示せず、日付の下に曜日を表示
            return dt.strftime('%m/%d') + f'\n({jp_weeks[dt.weekday()]})'
        else:
            # 時刻から :00 を排除（時のみ表示）し、高さを合わせる空行を追加
            return dt.strftime('%H') + '\n '
    return formatter
    
#==========================================================================================
# 8. グラフの共通軸設定を適用するサブルーチン
#==========================================================================================
def apply_common_axis_settings(ax, df, formatter, now_jst, design_params):
    # ② 現在時刻ラインの太さを半分に変更
    ax.axvline(now_jst, color='blue', linestyle='-', alpha=0.6, linewidth=CONFIG["VLINE_WIDTH"])
    ax.xaxis.set_major_locator(mdates.HourLocator(byhour=range(0, 24, 3)))
    ax.xaxis.set_major_formatter(plt.FuncFormatter(formatter))
    ax.xaxis.set_minor_locator(mdates.HourLocator(interval=1))
    ax.set_xlim(df['time'].iloc[0], df['time'].iloc[-1])
    ax.grid(True, which='major', linestyle=':', alpha=0.6, color='#000000')
    ax.grid(True, which='minor', linestyle=':', alpha=0.2, color='#888888')
    
    l_size = design_params.get("label_font_size", CONFIG["LABEL_SIZE"])
    l_pad = design_params.get("label_pad", CONFIG["LABEL_PAD"])
    
    ax.tick_params(axis='x', which='major', labelsize=l_size, pad=l_pad)
    ax.tick_params(axis='y', labelsize=l_size)
    
#==========================================================================================
# 9. 風速棒グラフを描画するサブルーチン
#==========================================================================================
def render_wind_bar_chart(ax, df, danger_v, wind_step, design_params=None):
    bar_width = design_params.get("bar_width", 0.035) if design_params else 0.035
    bars = ax.bar(df['time'], df['wind_speed_10m'], color=df['color'], alpha=0.9, width=bar_width)
    ax.axhline(y=danger_v, color='red', linestyle='--', linewidth=CONFIG["HLINE_WIDTH"], alpha=0.8)
    
    # フォントサイズ取得
    fs = design_params.get("base_font_size", CONFIG["GRAPH_FONT_SIZE"]) if design_params else CONFIG["GRAPH_FONT_SIZE"]
    
    # 矢印・文字の間隔を「文字サイズの20%」に固定（1ポイント≒0.35mmですが、グラフ単位系に換算）
    # グラフのY軸単位に合わせて 0.12 * fs 程度で調整
    step = fs * 0.12 
    base = step * 0.5
    
    # 表示フラグ
    show_w = design_params.get("show_w_text", CONFIG["SHOW_W_TEXT"]) if design_params else CONFIG["SHOW_W_TEXT"]
    show_d = design_params.get("show_dir_name", CONFIG["SHOW_DIR_NAME"]) if design_params else CONFIG["SHOW_DIR_NAME"]
    
    # ２．上部余白の計算：max(最大風速 + 表示要素数に応じた高さ, 危険ライン + 余裕)
    max_speed = df['wind_speed_10m'].max()
    element_count = 1 + 1 + (1 if show_d else 0) + (1 if show_w else 0) # 数値+矢印+風向+天気
    required_top_space = element_count * step + 1.0
    y_limit = max(max_speed + required_top_space, danger_v + 3.0)
    
    ax.set_ylim(0, y_limit)
    ax.set_ylabel('風速 (m/s)', fontsize=CONFIG["LABEL_SIZE"])
    
    for i, bar in enumerate(bars):
        if i % wind_step == 0:
            row = df.iloc[i]
            if pd.isna(row['wind_speed_10m']): continue
            base_y = bar.get_height()
            x_pos = bar.get_x() + bar.get_width()/2.
            
            # 1段目：風速数値
            current_y = base_y + base
            ax.text(x_pos, current_y, f"{row['wind_speed_10m']:.0f}", ha='center', va='bottom', fontsize=fs-2)
            
            # 2段目：矢印
            current_y += step
            ax.text(x_pos, current_y, row['arrow'], ha='center', va='bottom', 
                    fontsize=fs+2, fontweight='bold', color=CONFIG["ARROW_COLOR"])
            
            # 3段目：風向名
            if show_d:
                current_y += step
                ax.text(x_pos, current_y, row['dir_name'], ha='center', va='bottom', fontsize=fs-2)
            
            # 4段目：天気文字
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
@st.cache_data(show_spinner="グラフを生成中...", ttl=600)
def generate_high_res_graph(lat, lon, danger_v, selected_dirs_tuple, design_params, now_jst):
    df = fetch_weather_data(lat, lon, 8)
    if df is None: return None, (0, 0)
    
    padding_df = pd.DataFrame({'time': [df['time'].iloc[0] - timedelta(hours=i) for i in range(1, 4)][::-1]})
    df = pd.concat([padding_df, df], ignore_index=True)
    df = process_wind_data(df, list(selected_dirs_tuple))
    
    active_plots = []
    if design_params.get("show_wind", True): active_plots.append("wind")
    if design_params.get("show_temp", True): active_plots.append("temp")
    if design_params.get("show_tide", True): active_plots.append("tide")
    
    if not active_plots: return None, (0, 0)
    
    ratios = design_params.get("ratios", CONFIG["DEFAULT_RATIOS"])
    current_ratios = []
    if "wind" in active_plots: current_ratios.append(ratios[0])
    if "temp" in active_plots: current_ratios.append(ratios[1])
    if "tide" in active_plots: current_ratios.append(ratios[2])
    
    fig_w = design_params.get("width", CONFIG["GRAPH_WIDTH"])
    fig_h = design_params.get("height", CONFIG["GRAPH_HIGHT"])
    
    fig, axes = plt.subplots(len(active_plots), 1, figsize=(fig_w, fig_h), dpi=CONFIG["DPI"], 
                             gridspec_kw={'height_ratios': current_ratios})
    
    if len(active_plots) == 1: axes = [axes]
    
    plt.subplots_adjust(hspace=design_params.get("hspace", CONFIG["HSPACE"]))
    
    formatter = get_x_axis_formatter()
    
    idx = 0
    if "wind" in active_plots:
        render_wind_bar_chart(axes[idx], df, danger_v, 3, design_params)
        idx += 1
    if "temp" in active_plots:
        render_temp_line_chart(axes[idx], df)
        idx += 1
    if "tide" in active_plots:
        render_tide_curve_chart(axes[idx], df)
        idx += 1

    for ax in axes:
        # 修正ポイント: ここで渡す引数が定義側と一致しました
        apply_common_axis_settings(ax, df, formatter, now_jst, design_params)

    fig.tight_layout(pad=1.0) 
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
    # display_width（px）を基準に、各アイコンの絶対位置を計算
    for i in range(3, len(df), 3):
        row = df.iloc[i]
        # (開始位置 + 時間経過幅) * 全体幅 = アイコンの左端からのpx位置
        pos_left_px = (start_x + (i * hour_w)) * display_width
        icon_html += f'''
            <div style="
                position: absolute; 
                left: {pos_left_px}px; 
                transform: translateX(-50%); 
                width: 80px; 
                text-align: center; 
                font-size: 32px;
                z-index: 10;">
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

#==========================================================================================
# 15. ブラウザのlocalStorageと設定を同期するサブルーチン
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
            st.session_state.initialized = True

    save_data = {
        "lat": st.session_state.lat,
        "lon": st.session_state.lon,
        "basho": st.session_state.last_basho,
        "danger_v": st.session_state.get("danger_v", CONFIG["DEFAULT_DANGER_V"]),
        "sel_dirs": st.session_state.get("sel_dirs", CONFIG["DEFAULT_DIRS"])
    }
    js_save = f"localStorage.setItem('{STORAGE_KEY}', '{json.dumps(save_data)}')"
    safe_key = f"save_storage_{st.session_state.last_basho}"
    streamlit_js_eval(js_expressions=js_save, key=safe_key)

#==========================================================================================
# 16. 現在地を取得しセッション状態を更新するサブルーチン
#==========================================================================================
def handle_current_location_update():
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
# 17. サイドバーの表示設定とデザイン調整を表示するサブルーチン
#==========================================================================================
def show_sidebar_controls():
    st.sidebar.header("表示設定")
    default_v = st.session_state.get("danger_v", CONFIG["DEFAULT_DANGER_V"])
    danger_v = st.sidebar.number_input("危険風速ライン(m/s)", value=default_v, step=0.5)
    st.session_state.danger_v = danger_v
    
    st.sidebar.markdown("---")
    is_dev = st.sidebar.checkbox("🔧 デザイン微調整(開発者用)", value=False)
    
    # 1. 各項目の表示・非表示（開発者以外でも変えられるように外に出すか検討可能ですが、一旦開発者用に配置）
    design_params = {
        "width": CONFIG["GRAPH_WIDTH"],
        "base_font_size": CONFIG["GRAPH_FONT_SIZE"],
        "label_font_size": CONFIG["LABEL_SIZE"],
        "label_pad": CONFIG["LABEL_PAD"],
        "bar_width": 0.035,
        "annot_size": CONFIG["ANNOT_SIZE"],
        "ratios": CONFIG["DEFAULT_RATIOS"],
        "hspace": CONFIG["HSPACE"],
        "show_wind": CONFIG["SHOW_WIND"],
        "show_temp": CONFIG["SHOW_TEMP"],
        "show_tide": CONFIG["SHOW_TIDE"],
        "show_w_text": CONFIG["SHOW_W_TEXT"],
        "show_dir_name": CONFIG["SHOW_DIR_NAME"]
    }

    if is_dev:
        st.sidebar.subheader("表示・非表示")
        design_params["show_wind"] = st.sidebar.toggle("風向グラフを表示", value=design_params["show_wind"])
        design_params["show_temp"] = st.sidebar.toggle("気温グラフを表示", value=design_params["show_temp"])
        design_params["show_tide"] = st.sidebar.toggle("潮位グラフを表示", value=design_params["show_tide"])
        design_params["show_w_text"] = st.sidebar.toggle("天気文字を表示", value=design_params["show_w_text"])
        design_params["show_dir_name"] = st.sidebar.toggle("風向名を表示", value=design_params["show_dir_name"])
        
        st.sidebar.subheader("サイズ・間隔")
        design_params["width"] = st.sidebar.slider("グラフ横幅 (inch)", 10, 80, design_params["width"])
        # 縦幅は自動計算を基本とするため、ここでは「基準高さの倍率」とするか、直接指定を残す
        design_params["height_manual"] = st.sidebar.slider("縦幅微調整 (inch)", 1.0, 15.0, CONFIG["GRAPH_HIGHT"])
        design_params["hspace"] = st.sidebar.slider("グラフ間余白 (hspace)", -0.1, 1.0, design_params["hspace"], step=0.05)
        design_params["label_pad"] = st.sidebar.slider("X軸ラベル距離", -5, 20, design_params["label_pad"])
        
        st.sidebar.subheader("高さ比率")
        r = design_params["ratios"]
        r[0] = st.sidebar.slider("比率:風向", 0.5, 10.0, r[0], step=0.1)
        r[1] = st.sidebar.slider("比率:気温", 0.5, 5.0, r[1], step=0.1)
        r[2] = st.sidebar.slider("比率:潮位", 0.5, 5.0, r[2], step=0.1)
        design_params["ratios"] = r
        
        st.sidebar.subheader("フォント")
        design_params["base_font_size"] = st.sidebar.slider("グラフ内文字サイズ", 6, 24, design_params["base_font_size"])
        design_params["label_font_size"] = st.sidebar.slider("X軸ラベルサイズ", 5, 20, design_params["label_font_size"])
    
    # --- 縦幅の自動計算ロジック ---
    # 比率 4.4 : 1.2 : 0.8 が合計 6.4 のとき height 3.0 ならば、1単位 = 3.0 / 6.4
    unit_h = 3.0 / sum(CONFIG["DEFAULT_RATIOS"])
    auto_height = 0
    if design_params["show_wind"]: auto_height += design_params["ratios"][0] * unit_h
    if design_params["show_temp"]: auto_height += design_params["ratios"][1] * unit_h
    if design_params["show_tide"]: auto_height += design_params["ratios"][2] * unit_h
    
    # 開発者モードで手動調整が有効な場合はそちらを優先、そうでなければ自動計算
    design_params["height"] = design_params.get("height_manual", auto_height) if is_dev else auto_height

    st.sidebar.markdown("---")
    st.sidebar.write("色付風向")
    saved_dirs = st.session_state.get("sel_dirs", CONFIG["DEFAULT_DIRS"])
    sel_dirs = []
    cols = st.sidebar.columns(2)
    for i, d in enumerate(ALL_DIRECTIONS):
        with cols[i % 2]:
            if st.checkbox(d, value=(d in saved_dirs), key=f"chk_{d}"):
                sel_dirs.append(d)
    st.session_state.sel_dirs = sel_dirs
    
    return danger_v, sel_dirs, design_params

#==========================================================================================
# 18. グラフ更新ボタンと日時情報を描画するサブルーチン
#==========================================================================================
def render_header_info(current_basho_name):
    now = datetime.now(timezone(timedelta(hours=9)))
    date_time_str = now.strftime('%Y/%m/%d %H:%M:%S')
    update_label = f"🔄 グラフ更新 ({date_time_str})　　      　"
    if st.button(update_label, use_container_width=True):
        st.cache_data.clear()
        st.rerun()

#==========================================================================================
# 19. アプリのメインフローを制御するメインルーチン
#==========================================================================================
def main():
    if 'lat' not in st.session_state: st.session_state.lat = CONFIG["DEFAULT_LAT"]
    if 'lon' not in st.session_state: st.session_state.lon = CONFIG["DEFAULT_LON"]
    if 'last_basho' not in st.session_state: st.session_state.last_basho = CONFIG["DEFAULT_BASHO"]
    
    sync_all_settings()
    danger_v, sel_dirs, design_params = show_sidebar_controls()
    setup_font(design_params["base_font_size"])

    # 現在時刻を10分単位で丸めて取得（キャッシュ効率のため）
    raw_now = datetime.now(timezone(timedelta(hours=9))).replace(tzinfo=None)
    now_jst = raw_now.replace(minute=(raw_now.minute // 10) * 10, second=0, microsecond=0)

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
            st.session_state.show_map_state = True
        st.cache_data.clear()
        st.rerun()

    show_map = st.checkbox("地図表示", value=st.session_state.get('show_map_state', False))
    st.session_state.show_map_state = show_map
    if show_map:
        show_location_map()

    col1, col2 = st.columns([1, 1]) 
    with col1:
        handle_current_location_update()
    with col2:
        render_header_info(basho) 
    
    # 引数に now_jst を追加。これにより時刻が変われば新しいキャッシュが作成されます。
    img_b64, ratio_info = generate_high_res_graph(
        st.session_state.lat, 
        st.session_state.lon, 
        danger_v, 
        tuple(sel_dirs), 
        design_params,
        now_jst
    )
    
    if img_b64:
        df_for_icons = fetch_weather_data(st.session_state.lat, st.session_state.lon, 8)
        if df_for_icons is not None:
            display_width = int(design_params["width"] * CONFIG["PX_PER_INCH"])
            
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

#==========================================================================================
# アプリケーション起動
#==========================================================================================
if __name__ == "__main__":
    main()

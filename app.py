#///// 最終更新 2025.12.27 0:30 コンプリート版//////////////////////////////////////////////////////////////
# -*- coding: utf-8 -*-
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
from streamlit_js_eval import streamlit_js_eval, get_geolocation

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
        return df
    except: return None

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
    if pd.isna(code): return "", "black"
    if code <= 2: return "晴", "#FF4500"
    if code <= 48: return "曇", "#696969"
    if code <= 99: return "雨", "#00008B"
    return "？", "black"

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
# 13. ブラウザのLocalStorageとSessionStateを同期するサブルーチン
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
    streamlit_js_eval(js_expressions=js_save, key=f"save_storage_{time.time()}")
    
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
# 15.. 現在地取得サブルーチン (修正版：専用関数利用・シンプル化)
#==========================================================================================
def handle_current_location_update():
    """
    スマホ環境で動作確認済みの位置情報取得ロジック。
    st.statusなどのコンテナを使わず、シンプルに実装してJSの発火を確実にする。
    """
    st.markdown("---")
    
    # ボタン押下時：待機フラグを立て、キーを更新してリラン
    if st.button("🔄 現在地グラフ更新", use_container_width=True):
        st.session_state.waiting_loc = True
        # キャッシュ回避用の新しいキーを発行
        st.session_state.geo_key = f"geo_{datetime.now().timestamp()}"
        st.rerun()

    # 待機モード時の処理
    if st.session_state.get("waiting_loc"):
        st.info("🛰️ 現在地を取得しています... (許可ポップアップが出たら「許可」を押してください)")
        
        # 専用関数 get_geolocation を使用（コンポーネントの非表示設定）
        # ここで動的なキーを使うことで、毎回必ず新しい取得リクエストが走る
        loc = get_geolocation(component_key=st.session_state.get("geo_key"))

        if loc:
            new_lat = round(loc['coords']['latitude'], 4)
            new_lon = round(loc['coords']['longitude'], 4)
            
            # データの同期（State更新）
            st.session_state.lat = new_lat
            st.session_state.lon = new_lon
            st.session_state.last_basho = "現在地"
            
            st.success("✅ 取得成功！描画を更新します。")
            st.session_state.waiting_loc = False
            st.rerun()
        
        # 明示的なエラーまたはタイムアウト（ユーザーがブロックした場合など）
        # loc が None の間はここを通過して画面は「取得しています...」のまま待機となる
        elif loc is False:
            st.error("❌ 位置情報の取得に失敗しました。ブラウザの設定を確認してください。")
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
# 17. 現在時刻と更新ボタンを表示するサブルーチン (動的キャプション ＆ 時刻独立版)
#==========================================================================================
def render_header_info(current_basho_name):
    # ① 選択された場所名と座標をボタン名にする
    # 設定ファイルから取得したフォントサイズ設定などは維持しつつ、ボタンとして構成
    button_label = f"🔄 {current_basho_name} ({st.session_state.lat:.4f}, {st.session_state.lon:.4f}) グラフ更新"
    
    if st.button(button_label, use_container_width=False):
        st.cache_data.clear()
        st.rerun()
    
    # ② 取得時刻を独立して表示 (ボタンのすぐ下に小さく配置)
    now = datetime.now(timezone(timedelta(hours=9)))
    now_str = now.strftime('%Y/%m/%d %H:%M:%S')
    
    st.markdown(
        f"""
        <p style='font-size:12px; color:gray; margin-top:-10px; margin-left:5px;'>
            最終データ取得時刻: {now_str}
        </p>
        """, 
        unsafe_allow_html=True
    )

#==========================================================================================
# 18. メインフロー (PC完全復元 ＆ スマホ安定表示版)
#==========================================================================================
def main():
    setup_font()

    st.markdown(f"""
        <style>
            .block-container {{ padding-top: 3.5rem !important; padding-bottom: 0rem !important; }}
            h1 {{ 
                margin-top: 0px !important; 
                margin-bottom: -15px !important; 
                line-height: 1.0 !important; 
            }}
            [data-testid="stVerticalBlock"] {{ gap: 0.3rem !important; }}
            hr {{ display: none !important; }}
            div.stButton {{ text-align: left !important; margin-top: -5px !important; }}
            div.stButton > button {{
                width: auto !important;
                min-width: 200px;
                padding-left: 20px !important;
                padding-right: 20px !important;
            }}
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

    master = CONFIG["LOCATION_MASTER"].copy()
    if st.session_state.last_basho == "現在地":
        master["現在地"] = (st.session_state.lat, st.session_state.lon)
    master["地図で指定"] = (st.session_state.lat, st.session_state.lon)
    
    current_idx = list(master.keys()).index(st.session_state.last_basho) if st.session_state.last_basho in master else 0
    basho = st.selectbox("地点を選択してください", list(master.keys()), index=current_idx)
    
    if basho != st.session_state.last_basho:
        st.session_state.last_basho = basho
        if basho not in ["地図で指定", "現在地"]:
            st.session_state.lat, st.session_state.lon = master[basho]
        st.rerun()

    # ① 現在地ボタン（名称変更版を呼び出し）
    handle_current_location_update()
    
    show_map = st.checkbox("地図表示", value=st.session_state.get('show_map_state', False))
    st.session_state.show_map_state = show_map
    if show_map:
        show_location_map()

    # ②・③ 動的ボタンと時刻（場所名を渡す）
    render_header_info(basho) 
    
    danger_v, sel_dirs = show_sidebar_controls()
    img = generate_high_res_graph(st.session_state.lat, st.session_state.lon, danger_v, tuple(sel_dirs))
    
    if img:
        st.markdown(f'<div style="overflow-x: auto; background: white;"><img src="data:image/png;base64,{img}" style="height: 850px; max-width: none;"></div>', unsafe_allow_html=True)
        
#==========================================================================================
# XX. 呼び出しコード
#==========================================================================================
if __name__ == "__main__":
    main()

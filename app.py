# -*- coding: utf-8 -*-
# ベータ版　更新 2026.1.1 0930 （デザイン調整・ブラウザ保存対応）
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
    "SHOW_TIDE": False,          # デフォルトOFF
    "SHOW_W_TEXT": False,        # デフォルトOFF
    "SHOW_DIR_NAME": False,      # デフォルトOFF
    "HSPACE": 1.0,
    "DEFAULT_LAT": 31.337,
    "DEFAULT_LON": 130.795,
    "DEFAULT_BASHO": "高須沖(鹿児島県)",
    "DEFAULT_DANGER_V": 10.0,
    "DEFAULT_DIRS": ["南","南南西","南西","西南西","西","西北西","北西","北北西"],
    "ANNOT_Y_STEP": 1.5,
    "ANNOT_BASE_Y": 0.5,
    "SHOW_DEV_MODE": False,  # ← これを追記 [1]
    "STORAGE_KEY": "wind_checker_settings_v2", # バージョン管理用にキー変更
    "TEMP_COLOR": "darkorange",
    "ARROW_COLOR": "blue",
    "VLINE_WIDTH": 1.25,
    "HLINE_WIDTH": 1.0,
    "PX_PER_INCH": 200,
    "DEFAULT_PRECIP_Y": 1.00,      # 降水量の表示高さ（グラフ枠を1.0とした相対値）
    "DEFAULT_ICON_MARGIN": 10,     # アイコンHTMLの下マージン(px)
    "SLIDER_PRECIP_Y": {"min": 0.95, "max": 1.30, "step": 0.01},
    "SLIDER_ICON_MARGIN": {"min": -20, "max": 50, "step": 5},
    # スライダーの範囲設定
    "SLIDER_WIDTH": {"min": 13.0, "max": 30.0, "step": 1.0},
    "SLIDER_HEIGHT": {"min": 1.5, "max": 5.0, "step": 0.5},
    "SLIDER_FONT": {"min": 6, "max": 14, "step": 1},
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
    """
    Open-Meteo APIから気象データを取得し、詳細な天気アイコンを割り当てる。
    WMO Weather interpretation codes (WW) に準拠。降水量データも取得。
    """
    url = f"https://api.open-meteo.com/v1/forecast?latitude={lat}&longitude={lon}&hourly=temperature_2m,wind_speed_10m,wind_direction_10m,weather_code,precipitation&timezone=Asia%2FTokyo&wind_speed_unit=ms&forecast_days={days}"
    try:
        data = requests.get(url).json()
        df = pd.DataFrame(data["hourly"])
        df['time'] = pd.to_datetime(df['time'])
        
        def get_icon(code):
            # 0: 晴天, 1-3: 晴れ時々曇り
            if code == 0: return "☀️"
            if code <= 3: return "🌤️"
            # 45, 48: 霧
            if code == 45 or code == 48: return "🌫️"
            # 51-67: 霧雨・雨
            if code <= 67: return "☔"
            # 71-77: 雪
            if code <= 77: return "❄️"
            # 80-82: 俄か雨
            if code <= 82: return "🌦️"
            # 85-86: 雪（にわか）
            if code <= 86: return "🌨️"
            # 95-99: 雷雨
            if code <= 99: return "⛈️"
            return "❓"
            
        df['weather_icon'] = df['weather_code'].apply(get_icon)
        return df
    except: 
        return None

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
    """
    WMO天気コードから表示用テキストと、文字色を決定して返す。
    """
    if pd.isna(code): return "", "black"
    
    # 0-3: 晴・薄曇
    if code <= 3: 
        return "晴", "#FF4500" # OrangeRed
    # 45, 48: 霧
    if code == 45 or code == 48: 
        return "霧", "#708090" # SlateGray
    # 51-67: 雨
    if code <= 67: 
        return "雨", "#00008B" # DarkBlue
    # 71-77: 雪
    if code <= 77: 
        return "雪", "#00BFFF" # DeepSkyBlue
    # 80-82: 俄か雨
    if code <= 82: 
        return "雨", "#00008B"
    # 85-86: 激しい雪
    if code <= 86: 
        return "雪", "#00BFFF"
    # 95-99: 雷雨
    if code <= 99: 
        return "雷", "#8B0000" # DarkRed
        
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
    """
    風速棒グラフを描画し、上部に風速数値、矢印を表示する。
    さらに、グラフ枠外の上部に降水量を表示する。
    文字サイズは軸ラベルサイズ(l_fs)と同一にし、位置は design_params['precip_y'] で制御する。
    """
    bar_width = design_params.get("bar_width", 0.035) if design_params else 0.035
    bars = ax.bar(df['time'], df['wind_speed_10m'], color=df['color'], alpha=0.9, width=bar_width)
    ax.axhline(y=danger_v, color='red', linestyle='--', linewidth=CONFIG["HLINE_WIDTH"], alpha=0.8)
    
    # フォントサイズ設定
    fs = design_params.get("base_font_size", CONFIG["GRAPH_FONT_SIZE"]) if design_params else CONFIG["GRAPH_FONT_SIZE"]
    l_fs = design_params.get("label_font_size", CONFIG["LABEL_SIZE"]) if design_params else CONFIG["LABEL_SIZE"]
    
    # サイドバーからの位置設定（なければデフォルト 1.0）
    precip_y = design_params.get("precip_y", 1.0) if design_params else 1.0
    
    step = fs * 0.144 
    base = step * 0.5
    
    show_w = design_params.get("show_w_text", CONFIG["SHOW_W_TEXT"]) if design_params else CONFIG["SHOW_W_TEXT"]
    show_d = design_params.get("show_dir_name", CONFIG["SHOW_DIR_NAME"]) if design_params else CONFIG["SHOW_DIR_NAME"]
    
    max_speed = df['wind_speed_10m'].max() if not df['wind_speed_10m'].dropna().empty else 0
    element_count = 1 + 1 + (1 if show_d else 0) + (1 if show_w else 0)
    required_top_space = element_count * step + 1.0
    y_limit = max(max_speed + required_top_space, danger_v + 3.0)
    
    ax.set_ylim(0, y_limit)
    ax.set_ylabel('風速 (m/s)', fontsize=l_fs) # 軸ラベルサイズを適用
    
    for i, bar in enumerate(bars):
        row = df.iloc[i]
        dt = row['time']
        
        # グラフ内部の描画（風速・矢印）
        if i % wind_step == 0:
            if pd.isna(row['wind_speed_10m']): continue
            base_y = bar.get_height()
            x_pos = bar.get_x() + bar.get_width()/2.
            
            # 数値・矢印等の描画は以前のロジックを維持
            ax.text(x_pos, base_y + base, f"{row['wind_speed_10m']:.0f}", ha='center', va='bottom', fontsize=fs-2)
            # ... (矢印・風向・天気文字の描画は省略) ...

        # --- 降水量表示（軸ラベルサイズ l_fs と同一に設定） ---
        if dt.hour % 3 == 0:
            precip = row.get('precipitation')
            if pd.notna(precip) and str(precip).lower() != 'nan' and precip > 0:
                ax.text(
                    dt, 
                    precip_y, 
                    f"{precip:.0f}", 
                    ha='center', 
                    va='bottom', 
                    fontsize=l_fs,  # 軸ラベルと同じサイズに変更
                    color="blue",
                    fontweight='bold',
                    transform=ax.get_xaxis_transform(),
                    clip_on=False
                )
                
#==========================================================================================
# 10. 気温折れ線グラフを描画するサブルーチン
#==========================================================================================
def render_temp_line_chart(ax, df):
    """
    気温の折れ線グラフを描画し、各時刻（0時と3の倍数）の気温数値をグラフ枠外の上部に表示する。
    数値のフォントサイズは軸ラベルの設定（CONFIG["LABEL_SIZE"]）に従い、単位「℃」を付与する。
    """
    # メインの折れ線描画
    ax.plot(df['time'], df['temperature_2m'], color=CONFIG["TEMP_COLOR"], linewidth=2, marker='o', markersize=3, markevery=3)
    ax.set_ylabel('気温 (℃)', fontsize=CONFIG["LABEL_SIZE"])
    
    # フォントサイズは軸ラベルのサイズを取得
    label_fs = CONFIG["LABEL_SIZE"]
    
    # y軸の範囲設定（数値表示用に上部に少しだけ余白を持たせるが、数値自体は枠外へ飛ばす）
    t_max = df['temperature_2m'].max()
    t_min = df['temperature_2m'].min()
    y_range = t_max - t_min if t_max != t_min else 1.0
    ax.set_ylim(t_min - (y_range * 0.1), t_max + (y_range * 0.1))

    # 各時刻の気温数値を描画
    for i in range(len(df)):
        dt = df['time'].iloc[i]
        temp = df['temperature_2m'].iloc[i]
        
        # 0時、または3の倍数の時刻のみ数値を表示
        if not pd.isna(temp) and (dt.hour % 3 == 0):
            # transform=ax.get_xaxis_transform() を使用して、
            # Xは時刻データ、Yは「グラフ枠のすぐ上(1.02)」に固定して描画
            ax.text(
                dt, 
                1.02, 
                f"{temp:.0f}", 
                ha='center', 
                va='bottom', 
                fontsize=label_fs,
                color=CONFIG["TEMP_COLOR"],
                transform=ax.get_xaxis_transform(), # Y軸の値を0(下端)〜1(上端)の相対位置にする
                clip_on=False                       # 枠外への描画を許可
            )
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
    """
    指定されたパラメータに基づき、高解像度の気象グラフ画像を生成してBase64形式で返す。
    描画開始時刻を現在時刻の直前の3時間区切り（0,3,6,9,12,15,18,21時）に設定する。
    hspaceの値を確実に反映させるため、自動レイアウト調整を無効化している。
    """
    df_raw = fetch_weather_data(lat, lon, 8)
    if df_raw is None: return None, (0, 0)
    
    # --- 描画開始基準時刻の計算 ---
    base_hour = (now_jst.hour // 3) * 3
    start_time = now_jst.replace(hour=base_hour, minute=0, second=0, microsecond=0)
    
    # 基準時刻以降のデータを抽出
    df = df_raw[df_raw['time'] >= start_time].copy().reset_index(drop=True)
    
    # --- 左端の3時間空白（パディング）処理 ---
    padding_df = pd.DataFrame({'time': [df['time'].iloc[0] - timedelta(hours=i) for i in range(1, 4)][::-1]})
    df = pd.concat([padding_df, df], ignore_index=True)
    
    # 風データ等の処理
    df = process_wind_data(df, list(selected_dirs_tuple))
    
    # 表示するプロットの決定
    active_plots = []
    if design_params.get("show_wind", True): active_plots.append("wind")
    if design_params.get("show_temp", True): active_plots.append("temp")
    if design_params.get("show_tide", True): active_plots.append("tide")
    
    if not active_plots: return None, (0, 0)
    
    # レイアウト設定
    ratios = design_params.get("ratios", CONFIG["DEFAULT_RATIOS"])
    current_ratios = []
    if "wind" in active_plots: current_ratios.append(ratios[0])
    if "temp" in active_plots: current_ratios.append(ratios[1])
    if "tide" in active_plots: current_ratios.append(ratios[2])
    
    fig_w = design_params.get("width", CONFIG["GRAPH_WIDTH"])
    fig_h = design_params.get("height", CONFIG["GRAPH_HIGHT"])
    dpi_value = design_params.get("graph_dpi", CONFIG.get("DPI", 200))
    
    fig, axes = plt.subplots(len(active_plots), 1, figsize=(fig_w, fig_h), dpi=dpi_value, 
                             gridspec_kw={'height_ratios': current_ratios})
    
    if len(active_plots) == 1: axes = [axes]
    
    formatter = get_x_axis_formatter()
    
    # 各チャートの描画
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

    # 共通軸設定の適用
    for ax in axes:
        apply_common_axis_settings(ax, df, formatter, now_jst, design_params)

    # 【重要】tight_layoutを無効化し、手動のsubplots_adjustを優先させる
    # fig.tight_layout(pad=1.0) # ← これをコメントアウト
    
    # サイドバーのhspaceを適用
    plt.subplots_adjust(
        left=0.05, right=0.95, top=0.95, bottom=0.15,
        hspace=design_params.get("hspace", CONFIG["HSPACE"])
    )

    pos = axes[0].get_position() 
    # HTMLアイコン配置用の比率情報を計算
    ratio_info = (pos.x0, pos.width / (len(df) - 1))
    
    # 画像のバイナリ化
    buf = io.BytesIO()
    fig.savefig(buf, format="png", bbox_inches=None, pad_inches=0, dpi=dpi_value)
    plt.close(fig) 
    
    img_b64 = base64.b64encode(buf.getvalue()).decode()
    return img_b64, ratio_info
    
#==========================================================================================
# 13. お天気アイコンのHTMLを生成するサブルーチン
#==========================================================================================
def generate_weather_icons_html(df, ratio_info, display_width, icon_margin=0):
    """
    お天気アイコンのHTMLを生成し、下のグラフとの余白を icon_margin で調整する。
    """
    start_x, hour_w = ratio_info
    icon_html = ""
    
    for i in range(len(df)):
        row = df.iloc[i]
        dt = row['time']
        if dt.hour % 3 == 0:
            if pd.isna(row.get('weather_icon')) or pd.isna(dt): continue
            pos_left_px = (start_x + (i * hour_w)) * display_width
            icon_html += f'''
                <div style="position: absolute; left: {pos_left_px}px; top: 10px; 
                            transform: translateX(-50%); width: 80px; text-align: center; 
                            font-size: 32px; line-height: 1; z-index: 5;">
                    {row["weather_icon"]}
                </div>'''
    
    # 調整用の margin-bottom を適用
    return f'<div style="position: relative; width: {display_width}px; height: 35px; margin-bottom: {icon_margin}px; overflow: visible;">{icon_html}</div>'
    
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
    
    # すでに初期化済みの場合は、サイドバー操作時の再実行を防ぐために即リターン
    if st.session_state.get("initialized"):
        return

    ## 初回起動時のみブラウザからデータを読み込む
    ## stored_data = streamlit_js_eval(js_expressions=f"localStorage.getItem('{STORAGE_KEY}')", key="init_load_settings")
    ## ブラウザからデータを取得
    # stored_data = streamlit_js_eval(js_expressions=f"localStorage.getItem('{STORAGE_KEY}')", key="init_load_settings")

    ## 【重要】データが取得できるまでここで止める（これが「戻ってしまう」現象の対策）
    # if stored_data is None:
    #     st.stop() 
    # 
    #if stored_data:

    #--------------------------------------------------------------------------------------------
    # JS側で、データがない場合に "EMPTY" という文字列を返すように細工する
    js_query = f"localStorage.getItem('{STORAGE_KEY}') || 'EMPTY'"
    stored_data = streamlit_js_eval(js_expressions=js_query, key="init_load_settings_v3")

    if stored_data is None:
        st.stop()  # 本当に通信待ちの間だけ止める

    if stored_data == "EMPTY":
        # データがない場合は、何もせず初期化完了として進む
        st.session_state.initialized = True
    elif stored_data == "":
        # データが存在しない場合も初期化済みとする
        st.session_state.initialized = True
    else:
    #-----------------------------------------------------------------------------------------    
        try:
            data = json.loads(stored_data)
            # 地点情報の復元
            st.session_state.lat = float(data.get("lat", CONFIG["DEFAULT_LAT"]))
            st.session_state.lon = float(data.get("lon", CONFIG["DEFAULT_LON"]))
            st.session_state.last_basho = data.get("basho", CONFIG["DEFAULT_BASHO"])
            
            # 表示スイッチの復元
            st.session_state.show_wind = data.get("show_wind", CONFIG["SHOW_WIND"])
            st.session_state.show_temp = data.get("show_temp", CONFIG["SHOW_TEMP"])
            st.session_state.show_tide = data.get("show_tide", CONFIG["SHOW_TIDE"])
            
            # サイズ・文字設定の復元
            st.session_state.width = float(data.get("width", CONFIG["GRAPH_WIDTH"]))
            st.session_state.base_height = float(data.get("base_height", CONFIG["GRAPH_HIGHT"]))
            st.session_state.base_font_size = int(data.get("base_font_size", CONFIG["GRAPH_FONT_SIZE"]))
            st.session_state.label_font_size = int(data.get("label_font_size", CONFIG["LABEL_SIZE"]))
            
            # 危険風速・選択風向の復元
            st.session_state.danger_v = float(data.get("danger_v", CONFIG["DEFAULT_DANGER_V"]))
            st.session_state.sel_dirs = data.get("sel_dirs", CONFIG["DEFAULT_DIRS"])
            
            # 開発者用パラメータもあれば復元
            st.session_state.is_dev_mode = data.get("is_dev_mode", CONFIG.get("SHOW_DEV_MODE", False)) # [4, 6]
            st.session_state.label_pad = data.get("label_pad", CONFIG["LABEL_PAD"])
            st.session_state.hspace = data.get("hspace", CONFIG["HSPACE"])
            st.session_state.show_w_text = data.get("show_w_text", CONFIG["SHOW_W_TEXT"])
            st.session_state.show_dir_name = data.get("show_dir_name", CONFIG["SHOW_DIR_NAME"])
            st.session_state.ratios = data.get("ratios", CONFIG["DEFAULT_RATIOS"])
            
            # フラグを立ててリラン（初回のみ）
            st.session_state.initialized = True
            st.rerun()
        except Exception:
            # パース失敗時はデフォルト値で進む
            st.session_state.initialized = True

            
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
# 16_x. ブラウザへの保存を実行するサブルーチン（隠し要素）
#==========================================================================================
def save_settings_to_browser():
    """セッション状態にある現在の全設定をブラウザのlocalStorageに書き込む"""
    save_data = {
        "lat": st.session_state.lat,
        "lon": st.session_state.lon,
        "basho": st.session_state.last_basho,
        "show_wind": st.session_state.show_wind,
        "show_temp": st.session_state.show_temp,
        "show_tide": st.session_state.show_tide,
        "width": st.session_state.width,
        "base_height": st.session_state.base_height,
        "base_font_size": st.session_state.base_font_size,
        "label_font_size": st.session_state.label_font_size,
        "danger_v": st.session_state.danger_v,
        "sel_dirs": st.session_state.sel_dirs,
        "is_dev_mode": st.session_state.get("is_dev_mode", False), # ← これを追加 [5, 6]
        "label_pad": st.session_state.get("label_pad", CONFIG["LABEL_PAD"]),
        "hspace": st.session_state.get("hspace", CONFIG["HSPACE"]),
        "show_w_text": st.session_state.get("show_w_text", CONFIG["SHOW_W_TEXT"]),
        "show_dir_name": st.session_state.get("show_dir_name", CONFIG["SHOW_DIR_NAME"]),
        "ratios": st.session_state.get("ratios", CONFIG["DEFAULT_RATIOS"])
    }
    
    json_data = json.dumps(save_data, ensure_ascii=False)
    
    # JavaScriptを実行して保存。height=0でUIには影響を与えません。
    components.html(
        f"""
        <script>
        localStorage.setItem("{CONFIG['STORAGE_KEY']}", '{json_data}');
        </script>
        """,
        height=0,
    )

#==========================================================================================
# 17. サイドバーの表示設定とデザイン調整を表示するサブルーチン
#==========================================================================================
def show_sidebar_controls():
    is_beta = True 

    # --- 1. URLパラメータから mode=dev を取得するロジックを復活 ---
    # st.query_params を使用します
    is_dev_url = st.query_params.get("mode") == "dev" [2], [3]

    st.sidebar.header("表示設定")
     
    show_wind = st.sidebar.toggle("風向・風速", value=st.session_state.get("show_wind", CONFIG["SHOW_WIND"]))
    show_temp = st.sidebar.toggle("気温", value=st.session_state.get("show_temp", CONFIG["SHOW_TEMP"]))
    show_tide = st.sidebar.toggle("潮位", value=st.session_state.get("show_tide", CONFIG["SHOW_TIDE"]))
    
    w_cfg = CONFIG["SLIDER_WIDTH"]
    h_cfg = CONFIG["SLIDER_HEIGHT"]
    f_cfg = CONFIG["SLIDER_FONT"]
    
    width = st.sidebar.slider("横幅 (inch)", w_cfg["min"], w_cfg["max"], float(st.session_state.get("width", CONFIG["GRAPH_WIDTH"])), step=w_cfg["step"])
    base_height = st.sidebar.slider("基準縦幅 (inch)", h_cfg["min"], h_cfg["max"], float(st.session_state.get("base_height", CONFIG["GRAPH_HIGHT"])), step=h_cfg["step"])
    base_font_size = st.sidebar.slider("グラフ内文字", f_cfg["min"], f_cfg["max"], st.session_state.get("base_font_size", CONFIG["GRAPH_FONT_SIZE"]), step=f_cfg["step"])
    label_font_size = st.sidebar.slider("軸ラベル文字", f_cfg["min"], f_cfg["max"], st.session_state.get("label_font_size", CONFIG["LABEL_SIZE"]), step=f_cfg["step"])

    st.sidebar.markdown("---")
    # --- 2. チェックボックスの初期値に URL判定の結果を組み込む ---
    # URLが dev モード、またはセッションに保存された値が True なら有効にする
    default_dev_val = is_dev_url or st.session_state.get("is_dev_mode", False)
    is_dev = st.sidebar.checkbox("🔧 開発者用マイクロ調整", value=default_dev_val)  #  [1]
    # is_dev = st.sidebar.checkbox("🔧 開発者用マイクロ調整", value=st.session_state.get("is_dev_mode", False))
    st.session_state.is_dev_mode = is_dev

    # 初期値セット
    if "min_container_width" not in st.session_state: st.session_state.min_container_width = 2500
    if "graph_dpi" not in st.session_state: st.session_state.graph_dpi = 200

    design_params = {
        "width": width, "base_height": base_height,
        "base_font_size": base_font_size, "label_font_size": label_font_size,
        "label_pad": st.session_state.get("label_pad", CONFIG["LABEL_PAD"]),
        "hspace": st.session_state.get("hspace", CONFIG["HSPACE"]),
        "show_wind": show_wind, "show_temp": show_temp, "show_tide": show_tide,
        "show_w_text": st.session_state.get("show_w_text", CONFIG["SHOW_W_TEXT"]),
        "show_dir_name": st.session_state.get("show_dir_name", CONFIG["SHOW_DIR_NAME"]),
        "ratios": list(st.session_state.get("ratios", CONFIG["DEFAULT_RATIOS"])),
        "min_container_width": st.session_state.min_container_width,
        "graph_dpi": st.session_state.graph_dpi
    }

    if is_dev:
        st.sidebar.info("開発用詳細設定")
        # ユーザーによる修正を反映 (500~3000)
        design_params["min_container_width"] = st.sidebar.select_slider(
            "コンテナ最小幅 (px)", options=[500, 1000, 1500, 2000, 2500, 3000], value=design_params["min_container_width"]
        )
        design_params["graph_dpi"] = st.sidebar.radio("解像度 (DPI)", options=[200, 300], index=(0 if design_params["graph_dpi"] == 200 else 1), horizontal=True)
        design_params["show_w_text"] = st.sidebar.toggle("天気詳細文字を表示", value=design_params["show_w_text"])
        design_params["show_dir_name"] = st.sidebar.toggle("風向名を表示", value=design_params["show_dir_name"])
        design_params["hspace"] = st.sidebar.slider("グラフ間余白", -0.2, 1.5, design_params["hspace"], step=0.05)
        design_params["label_pad"] = st.sidebar.slider("ラベル距離", -5, 10, design_params["label_pad"])
        # サイドバーの実装例（既存のスライダー群に追加）
        st.sidebar.markdown("### 降水量・アイコン位置調整")
        precip_y = st.sidebar.slider("降水量ラベル高さ", 
                                   CONFIG["SLIDER_PRECIP_Y"]["min"], 
                                   CONFIG["SLIDER_PRECIP_Y"]["max"], 
                                   CONFIG["DEFAULT_PRECIP_Y"], 0.01)
        
        icon_margin = st.sidebar.slider("天気アイコン下余白", 
                                      CONFIG["SLIDER_ICON_MARGIN"]["min"], 
                                      CONFIG["SLIDER_ICON_MARGIN"]["max"], 
                                      CONFIG["DEFAULT_ICON_MARGIN"], 5)
        
        # これらを design_params に入れて generate_high_res_graph に渡す
        design_params["precip_y"] = precip_y
        design_params["icon_margin"] = icon_margin

        
        r = design_params["ratios"]
        r[0] = st.sidebar.number_input("比率:風向", 0.5, 10.0, r[0], step=0.1)
        r[1] = st.sidebar.number_input("比率:気温", 0.5, 5.0, r[1], step=0.1)
        r[2] = st.sidebar.number_input("比率:潮位", 0.5, 5.0, r[2], step=0.1)
        design_params["ratios"] = r

    # 縦幅計算
    base_ratio_total = design_params["ratios"][0] + design_params["ratios"][1]
    fixed_unit_h = base_height / base_ratio_total 
    icon_margin = 0.45 if show_wind else 0.0
    auto_height = icon_margin
    if show_wind: auto_height += design_params["ratios"][0] * fixed_unit_h
    if show_temp: auto_height += design_params["ratios"][1] * fixed_unit_h
    if show_tide: auto_height += design_params["ratios"][2] * fixed_unit_h
    design_params["height"] = auto_height

    st.sidebar.markdown("---")
    danger_v = st.sidebar.number_input("危険風速ライン(m/s)", value=st.session_state.get("danger_v", CONFIG["DEFAULT_DANGER_V"]), step=0.5)
    
    st.sidebar.write("色付風向選択")
    saved_dirs = st.session_state.get("sel_dirs", CONFIG["DEFAULT_DIRS"])
    sel_dirs = []
    cols = st.sidebar.columns(2)
    for i, d in enumerate(ALL_DIRECTIONS):
        with cols[i % 2]:
            if st.checkbox(d, value=(d in saved_dirs), key=f"chk_{d}"):
                sel_dirs.append(d)

    st.session_state.update({
        "show_wind": show_wind, "show_temp": show_temp, "show_tide": show_tide,
        "width": width, "base_height": base_height, "base_font_size": base_font_size,
        "label_font_size": label_font_size, "danger_v": danger_v, "sel_dirs": sel_dirs,
        "label_pad": design_params["label_pad"], "hspace": design_params["hspace"],
        "show_w_text": design_params["show_w_text"], "show_dir_name": design_params["show_dir_name"],
        "ratios": design_params["ratios"], "min_container_width": design_params["min_container_width"],
        "graph_dpi": design_params["graph_dpi"]
    })

    save_settings_to_browser()
    return danger_v, sel_dirs, design_params
    
#==========================================================================================
# 18. グラフ更新ボタンと日時情報を描画するサブルーチン
#==========================================================================================
def render_header_info(current_basho_name):
    now = datetime.now(timezone(timedelta(hours=9)))
    date_time_str = now.strftime('%Y/%m/%d %H:%M:%S')
    update_label = f"🔄 グラフ更新 ({date_time_str})　　        　"
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

    raw_now = datetime.now(timezone(timedelta(hours=9))).replace(tzinfo=None)
    now_jst = raw_now.replace(minute=(raw_now.minute // 10) * 10, second=0, microsecond=0)

    st.markdown(f"""
        <style>
            .block-container {{ padding-top: 2rem !important; padding-bottom: 0rem !important; }}
            .scroll-container {{ overflow-x: auto; background: white; border: 1px solid #ddd; width: 100%; }}
        </style>
    """, unsafe_allow_html=True)

    st.markdown(f'<h1 style="font-size:{CONFIG["TITLE_SIZE"]}px;">⛵ Wind_Checker! </h1>', unsafe_allow_html=True)
    
    # (地点選択・地図表示ロジックは既存のものを維持)
    # --- 地点選択コンボボックス（座標を名前に統合） ---
    master = CONFIG["LOCATION_MASTER"].copy()
    display_options = {}
    for name, coords in master.items():
        display_options[f"{name} ({coords[0]:.4f}, {coords[1]:.4f})"] = name

    # 【復活】現在地ラベルに座標を表示
    current_loc_label = f"📍 現在地 ({st.session_state.lat:.4f}, {st.session_state.lon:.4f})  "
    display_options[current_loc_label] = "現在地"
    map_loc_label = f"🗺️ 地図で指定 ({st.session_state.lat:.4f}, {st.session_state.lon:.4f})   "
    display_options[map_loc_label] = "地図で指定"

    
    # current_loc_label = f"📍 現在地 ({st.session_state.lat:.4f}, {st.session_state.lon:.4f})"
    # display_options[current_loc_label] = "現在地"
    # display_options["🗺️ 地図で指定"] = "地図で指定"

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
        st.cache_data.clear() # 地点変更時は即座にクリア
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
    
    # ..................................................................... 

    img_b64, ratio_info = generate_high_res_graph(
        st.session_state.lat, st.session_state.lon, danger_v, tuple(sel_dirs), design_params, now_jst
    )
    
    if img_b64:
        df_for_icons = fetch_weather_data(st.session_state.lat, st.session_state.lon, 8)
        if df_for_icons is not None:
            dpi = design_params["graph_dpi"]
            display_width = int(design_params["width"] * dpi)
            min_w = design_params["min_container_width"]
            
            padding_df = pd.DataFrame({'time': [df_for_icons['time'].iloc[0] - timedelta(hours=i) for i in range(1, 4)][::-1]})
            df_full = pd.concat([padding_df, df_for_icons], ignore_index=True)
            
            icons_html = generate_weather_icons_html(df_full, ratio_info, display_width)
            graph_html = f'<img src="data:image/png;base64,{img_b64}" style="width: {display_width}px; display: block;">'
            
            st.markdown(
                f'<div class="scroll-container">'
                f'<div style="width: {display_width}px; min-width: {min_w}px;">'
                f'{icons_html}{graph_html}'
                f'</div></div>', 
                unsafe_allow_html=True
            )
            
#==========================================================================================
# アプリケーション起動
#==========================================================================================
if __name__ == "__main__":
    main()

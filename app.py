# -*- coding: utf-8 -*-
# ベータ版　更新 2026.1.2 1130 コンプリート版
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
            # 曜日によって色を決定 (月-金: 青, 土日: 赤)
            # Matplotlibのテキスト内での色指定は、描画側(apply_common_axis_settings)で
            # 個別に制御するため、ここでは情報のみ保持。
            # または、描画時に判定するためここでは文字列のみ返す
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

    # --- 曜日の色分け設定（平日: 青, 土日: 赤） ---
    fig = ax.figure
    fig.canvas.draw()  # ラベルを確定させるために一度描画計算を行う
    labels = ax.get_xticklabels()
    for label in labels:
        text = label.get_text()
        if '(' in text:  # 曜日が含まれるラベル（0時）を特定
            if '土' in text or '日' in text:
                label.set_color('red')
            else:
                label.set_color('blue')
                
# ======================================================================================
# 9. 風速棒グラフを描画するサブルーチン
# ======================================================================================
def render_wind_bar_chart(ax, df, danger_v, wind_step, design_params=None):
    """
    風速棒グラフを描画し、上部に各種情報を配置する。
    左端の3時間パディングを考慮し、グラフ枠の左端（インデックス3）から描画基準を合わせる。
    降水量は0より大きい場合のみ、小数点第1位まで表示する。
    """
    bar_width = design_params.get("bar_width", 0.035) if design_params else 0.035
    bars = ax.bar(df['time'], df['wind_speed_10m'], color=df['color'], alpha=0.9, width=bar_width)
    ax.axhline(y=danger_v, color='red', linestyle='--', linewidth=CONFIG["HLINE_WIDTH"], alpha=0.8)
    
    # 基本サイズ設定
    fs = design_params.get("base_font_size", CONFIG["GRAPH_FONT_SIZE"]) if design_params else CONFIG["GRAPH_FONT_SIZE"]
    l_fs = design_params.get("label_font_size", CONFIG["LABEL_SIZE"]) if design_params else CONFIG["LABEL_SIZE"]
    precip_y = design_params.get("precip_y", 1.0) if design_params else 1.0
    
    # レイアウト計算
    step = fs * 0.144 
    base = step * 0.5
    show_w = design_params.get("show_w_text", CONFIG["SHOW_W_TEXT"]) if design_params else CONFIG["SHOW_W_TEXT"]
    show_d = design_params.get("show_dir_name", CONFIG["SHOW_DIR_NAME"]) if design_params else CONFIG["SHOW_DIR_NAME"]
    
    max_speed = df['wind_speed_10m'].max() if not df['wind_speed_10m'].dropna().empty else 0
    y_limit = max(max_speed + (4 * step) + 1.0, danger_v + 3.0)
    ax.set_ylim(0, y_limit)
    ax.set_ylabel('風速 (m/s)', fontsize=l_fs) 

    # --- ①「降水量mm」の見出し位置修正 ---
    # グラフの左端（パディング直後の時刻）を取得
    graph_left_time = df['time'].iloc[3] 
    ax.text(graph_left_time, precip_y, "降水量mm", 
            ha='right', va='bottom', fontsize=l_fs, color="blue", 
            transform=ax.get_xaxis_transform(), clip_on=False)
    
    for i, bar in enumerate(bars):
        # 0, 1, 2番目のインデックス（パディング期間）は描画をスキップ
        if i < 3: continue
        
        row = df.iloc[i]
        dt = row['time']
        x_pos = bar.get_x() + bar.get_width()/2.
        
        # --- ② 風速数値・矢印の描画（3時間ステップごと） ---
        if (i - 3) % wind_step == 0:
            if pd.isna(row['wind_speed_10m']): continue
            base_y = bar.get_height()
            
            # 風速数値
            ax.text(x_pos, base_y + base, f"{row['wind_speed_10m']:.0f}", ha='center', va='bottom', fontsize=fs-2)
            # 矢印
            current_y = base_y + base + step
            ax.text(x_pos, current_y, row['arrow'], ha='center', va='bottom', 
                    fontsize=fs+2, fontweight='bold', color=CONFIG["ARROW_COLOR"])
            # 風向名
            if show_d:
                current_y += step
                ax.text(x_pos, current_y, row['dir_name'], ha='center', va='bottom', fontsize=fs-2)
            # 天気文字
            if show_w:
                current_y += step
                ax.text(x_pos, current_y, row['w_text'], ha='center', va='bottom', 
                        color=row['w_color'], fontweight='bold', fontsize=fs-1)

        # --- ③ 降水量数値の表示（3時間ごと、0より大きい場合のみ） ---
        if (i - 3) % 3 == 0:
            precip = row.get('precipitation', 0)
            if pd.notna(precip) and precip > 0:
                # 棒グラフの中心(x_pos)を使用して、横ズレを完全に防ぐ
                ax.text(dt, precip_y, f"{precip:.1f}", ha='center', va='bottom', 
                        fontsize=l_fs, color="blue", transform=ax.get_xaxis_transform(), clip_on=False)
                
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

# ======================================================================================
# 12. 高解像度グラフ画像を生成するサブルーチン
# ======================================================================================
@st.cache_data(show_spinner="グラフを生成中...", ttl=600)
def generate_high_res_graph(lat, lon, danger_v, selected_dirs_tuple, design_params, now_jst):
    """
    指定されたパラメータに基づき、高解像度の気象グラフ画像を生成してBase64形式で返す。
    データの抽出範囲をパディングを含めて厳密に定義し、HTML配置用の比率を正確に算出する。
    """
    import pandas as pd
    import io
    import base64
    from datetime import timedelta

    df_raw = fetch_weather_data(lat, lon, 9)
    if df_raw is None: return None, (0, 0), 0, None
    
    # 描画開始（グラフ左端）は現在時刻の直前の3の倍数時
    display_start_time = now_jst.replace(hour=(now_jst.hour // 3) * 3, minute=0, second=0, microsecond=0)
    # パディング開始はその3時間前
    padding_start_time = display_start_time - timedelta(hours=3)
    
    # データを切り出し、インデックスを 0 から振り直す
    # これにより i=3 が必ず display_start_time になる（左端の空白を確保）
    df = df_raw[df_raw['time'] >= padding_start_time].copy().reset_index(drop=True)
    
    # 表示期間を 192時間(8日) + パディング3時間 = 195行に固定
    df = df.head(195)
    
    # アイコン同期用：パディングを含めたこの構造では、描画開始インデックスは 3
    start_idx = 3
    
    df = process_wind_data(df, list(selected_dirs_tuple))
    
    active_plots = []
    if design_params.get("show_wind", True): active_plots.append("wind")
    if design_params.get("show_temp", True): active_plots.append("temp")
    if design_params.get("show_tide", True): active_plots.append("tide")
    
    if not active_plots: return None, (0, 0), start_idx, df
    
    ratios = design_params.get("ratios", CONFIG["DEFAULT_RATIOS"])
    current_ratios = [ratios[i] for i, p in enumerate(["wind", "temp", "tide"]) if p in active_plots]
    
    fig_w = design_params.get("width", CONFIG["GRAPH_WIDTH"])
    fig_h = design_params.get("height", CONFIG["GRAPH_HIGHT"])
    dpi_value = design_params.get("graph_dpi", CONFIG.get("DPI", 200))
    
    fig, axes = plt.subplots(len(active_plots), 1, figsize=(fig_w, fig_h), dpi=dpi_value, 
                             gridspec_kw={'height_ratios': current_ratios})
    
    if len(active_plots) == 1: axes = [axes]
    
    formatter = get_x_axis_formatter()
    
    idx = 0
    if "wind" in active_plots:
        render_wind_bar_chart(axes[idx], df, danger_v, start_idx, design_params)
        idx += 1
    if "temp" in active_plots:
        render_temp_line_chart(axes[idx], df)
        idx += 1
    if "tide" in active_plots:
        render_tide_curve_chart(axes[idx], df)
        idx += 1

    for ax in axes:
        apply_common_axis_settings(ax, df, formatter, now_jst, design_params)

    plt.subplots_adjust(left=0.05, right=0.95, top=0.95, bottom=0.15,
                        hspace=design_params.get("hspace", CONFIG["HSPACE"]))

    # 比率計算: 全データ区間(len(df)-1)に対する1時間幅
    pos = axes[0].get_position() 
    ratio_info = (pos.x0, pos.width / (len(df) - 1))
    
    buf = io.BytesIO()
    fig.savefig(buf, format="png", bbox_inches=None, pad_inches=0, dpi=dpi_value)
    plt.close(fig) 
    
    return base64.b64encode(buf.getvalue()).decode(), ratio_info, start_idx, df
    
# ======================================================================================
# 13. お天気アイコンのHTMLを生成するサブルーチン
# ======================================================================================
def generate_weather_icons_html(df, ratio_info, display_width, start_idx, icon_margin=0):
    """
    12番で生成されたdfと物理座標情報を元に、正確な位置へ天気アイコンを配置する。
    見出し「天気」の位置をグラフ内の「降水量mm」と垂直に揃える。
    """
    import pandas as pd
    start_x, hour_w = ratio_info
    icon_html = ""
    
    l_size_pt = CONFIG.get("LABEL_SIZE", 7)
    # グラフ内のフォントサイズ(pt)をpx相当に変換
    header_fs_px = l_size_pt * 1.33
    
    # 「天気」見出しの配置：start_x（グラフ枠の左端）を基準にする
    # 12番の ax.text(graph_left_time, ..., ha='right') と揃えるため translateX(-100%) を使用
    label_pos_x = (start_x * display_width)
    icon_html += f'''
        <div style="position: absolute; left: {label_pos_x}px; top: 22px; 
                    transform: translateX(-105%); font-size: {header_fs_px}px; 
                    font-family: 'Noto Sans JP', sans-serif; color: #333; z-index: 5; white-space: nowrap;">
            天気
        </div>'''

    # 指定された開始位置から3時間おきにアイコンを配置
    for i in range(int(start_idx), len(df), 3):
        row = df.iloc[i]
        icon = row.get('weather_icon')
        if not icon or pd.isna(icon): continue
        
        # 物理位置計算：start_x（0行目の位置）＋ i時間分の幅
        pos_left_px = (start_x + (i * hour_w)) * display_width
        
        icon_html += f'''
            <div style="position: absolute; left: {pos_left_px}px; top: 10px; 
                        transform: translateX(-50%); width: 80px; text-align: center; 
                        font-size: 32px; line-height: 1; z-index: 5;">
                {icon}
            </div>'''
    
    # 最終的なHTMLコンテナ（デバッグ用の高さを35pxに戻す）
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
            new_lat = map_out["center"]["lat"]
            new_lon = map_out["center"]["lng"]
            
            # 1. 強化したサブルーチン14を呼び出す
            detail_name = fetch_location_name(new_lat, new_lon)
            
            # 2. セッションに代入（ここで "現在地" と書かずに detail_name を使う）
            st.session_state.lat = new_lat
            st.session_state.lon = new_lon
            st.session_state.last_basho = detail_name  # ← ここが重要です
            
            st.rerun()

# ======================================================================================
# 14. 逆ジオコーディングにより緯度経度から地名を取得するサブルーチン（市町村名連結版）
# ======================================================================================
def fetch_location_name(lat, lon):
    """
    OpenStreetMapのNominatim APIを使用し、「市町村名 + 町名」の形式で地名を返す。
    """
    import requests
    
    headers = {
        "User-Agent": "WindChecker_App_v2_PreciseName",
        "Accept-Language": "ja"
    }
    url = f"https://nominatim.openstreetmap.org/reverse?lat={lat}&lon={lon}&format=json"
    
    try:
        response = requests.get(url, headers=headers, timeout=5)
        if response.status_code == 200:
            data = response.json()
            address = data.get("address", {})
            
            # 1. 市町村レベルを取得 (霧島市など)
            city = address.get("city") or address.get("town") or address.get("village") or ""
            
            # 2. 町名・街区レベルを取得 (国分広瀬二丁目など)
            # neighbourhood(丁目レベル) > suburb(町名レベル)
            suburb = address.get("neighbourhood") or address.get("suburb") or address.get("city_district") or ""
            
            # 3. 組み合わせ処理
            # 市町村名と町名が同じ（例：垂水市垂水）場合は重複させない
            if city and suburb:
                if suburb in city:
                    full_name = city
                else:
                    full_name = f"{city}{suburb}"
            else:
                full_name = suburb or city or "地図で指定地点"
                
            return full_name
            
    except:
        pass
    
    return "地図で指定地点"
    
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

# ======================================================================================
# 17. サイドバーの表示設定とデザイン調整を表示するサブルーチン
# ======================================================================================
def show_sidebar_controls():
    """
    ユーザー設定と開発者設定を分離して表示。
    st.session_state への直接アクセスを廃止し、.get() とローカル変数を使用することで
    AttributeError を完全に防止する。
    """
    import streamlit as st

    # --- 1. 開発者モード判定 ---
    is_dev_url = st.query_params.get("mode") == "dev"

    with st.sidebar.form("sidebar_setting_form"):
        # ==========================================
        # 【上段】一般ユーザー設定セクション
        # ==========================================
        st.header("表示設定")
        
        show_wind = st.toggle("風向・風速", value=st.session_state.get("show_wind", CONFIG["SHOW_WIND"]))
        show_temp = st.toggle("気温", value=st.session_state.get("show_temp", CONFIG["SHOW_TEMP"]))
        show_tide = st.toggle("潮位", value=st.session_state.get("show_tide", CONFIG["SHOW_TIDE"]))
        
        st.markdown("---")
        
        w_cfg, h_cfg, f_cfg = CONFIG["SLIDER_WIDTH"], CONFIG["SLIDER_HEIGHT"], CONFIG["SLIDER_FONT"]
        width = st.slider("横幅 (inch)", w_cfg["min"], w_cfg["max"], float(st.session_state.get("width", CONFIG["GRAPH_WIDTH"])), step=w_cfg["step"])
        base_height = st.slider("基準縦幅 (inch)", h_cfg["min"], h_cfg["max"], float(st.session_state.get("base_height", CONFIG["GRAPH_HIGHT"])), step=h_cfg["step"])
        base_font_size = st.slider("グラフ内文字", f_cfg["min"], f_cfg["max"], st.session_state.get("base_font_size", CONFIG["GRAPH_FONT_SIZE"]), step=f_cfg["step"])
        label_font_size = st.slider("軸ラベル文字", f_cfg["min"], f_cfg["max"], st.session_state.get("label_font_size", CONFIG["LABEL_SIZE"]), step=f_cfg["step"])

        st.markdown("---")
        
        danger_v = st.number_input("危険風速ライン(m/s)", value=st.session_state.get("danger_v", CONFIG["DEFAULT_DANGER_V"]), step=0.5)
        
        st.write("色付風向選択")
        saved_dirs = st.session_state.get("sel_dirs", CONFIG["DEFAULT_DIRS"])
        sel_dirs = []
        cols = st.columns(2)
        for i, d in enumerate(ALL_DIRECTIONS):
            with cols[i % 2]:
                if st.checkbox(d, value=(d in saved_dirs), key=f"chk_{d}"):
                    sel_dirs.append(d)

        # ==========================================
        # 【下段】開発者用マイクロ調整
        # ==========================================
        # 現在の値をローカル変数にコピー（AttributeError防止）
        d_min_w = st.session_state.get("min_container_width", 2500)
        d_dpi = st.session_state.get("graph_dpi", 200)
        d_w_text = st.session_state.get("show_w_text", CONFIG["SHOW_W_TEXT"])
        d_dir_name = st.session_state.get("show_dir_name", CONFIG["SHOW_DIR_NAME"])
        d_hspace = st.session_state.get("hspace", CONFIG["HSPACE"])
        d_l_pad = st.session_state.get("label_pad", CONFIG["LABEL_PAD"])
        d_precip_y = st.session_state.get("precip_y", CONFIG.get("DEFAULT_PRECIP_Y", 0.5))
        d_icon_m = st.session_state.get("icon_margin", CONFIG.get("DEFAULT_ICON_MARGIN", 0))
        d_ratios = list(st.session_state.get("ratios", CONFIG["DEFAULT_RATIOS"]))

        if is_dev_url:
            st.markdown("---")
            st.warning("🔧 開発者用マイクロ調整")
            d_min_w = st.select_slider("コンテナ最小幅 (px)", options=[500, 1000, 1500, 2000, 2500, 3000], value=d_min_w)
            d_dpi = st.radio("解像度 (DPI)", options=[200, 300], index=(0 if d_dpi == 200 else 1), horizontal=True)
            d_w_text = st.toggle("天気詳細文字を表示", value=d_w_text)
            d_dir_name = st.toggle("風向名を表示", value=d_dir_name)
            d_hspace = st.slider("グラフ間余白", -0.2, 1.5, d_hspace, step=0.05)
            d_l_pad = st.slider("ラベル距離", -5, 10, d_l_pad)
            d_precip_y = st.slider("降水量高さ", 0.0, 1.0, d_precip_y, 0.01)
            d_icon_m = st.slider("アイコン下余白", 0, 100, d_icon_m, 5)
            
            st.write("各グラフ比率調整")
            d_ratios[0] = st.number_input("比率:風向", 0.5, 10.0, d_ratios[0], step=0.1)
            d_ratios[1] = st.number_input("比率:気温", 0.5, 5.0, d_ratios[1], step=0.1)
            d_ratios[2] = st.number_input("比率:潮位", 0.5, 5.0, d_ratios[2], step=0.1)

        submitted = st.form_submit_button("設定を適用してグラフ更新", use_container_width=True)

    # --- 3. 確定データの構築 ---
    # フォーム内の最新値を辞書にまとめる
    current_settings = {
        "show_wind": show_wind, "show_temp": show_temp, "show_tide": show_tide,
        "width": width, "base_height": base_height, 
        "base_font_size": base_font_size, "label_font_size": label_font_size,
        "danger_v": danger_v, "sel_dirs": sel_dirs,
        "min_container_width": d_min_w, "graph_dpi": d_dpi, "show_w_text": d_w_text,
        "show_dir_name": d_dir_name, "hspace": d_hspace, "label_pad": d_l_pad,
        "precip_y": d_precip_y, "icon_margin": d_icon_m, "ratios": d_ratios
    }

    # 初回起動時、またはボタン押下時にセッションを更新
    if submitted or "width" not in st.session_state:
        st.session_state.update(current_settings)
        if submitted:
            st.cache_data.clear()
            st.rerun()

    # --- 4. 戻り値の作成（セッションではなくローカル変数 current_settings を参照する） ---
    h = calculate_graph_height(
        current_settings["base_height"], 
        current_settings["ratios"], 
        current_settings["show_wind"], 
        current_settings["show_temp"], 
        current_settings["show_tide"]
    )
    
    design_params = {
        "width": current_settings["width"],
        "height": h,
        "base_font_size": current_settings["base_font_size"],
        "label_font_size": current_settings["label_font_size"],
        "label_pad": current_settings["label_pad"],
        "hspace": current_settings["hspace"],
        "show_wind": current_settings["show_wind"],
        "show_temp": current_settings["show_temp"],
        "show_tide": current_settings["show_tide"],
        "show_w_text": current_settings["show_w_text"],
        "show_dir_name": current_settings["show_dir_name"],
        "ratios": current_settings["ratios"],
        "min_container_width": current_settings["min_container_width"],
        "graph_dpi": current_settings["graph_dpi"],
        "precip_y": current_settings["precip_y"],
        "icon_margin": current_settings["icon_margin"]
    }
    
    return current_settings["danger_v"], current_settings["sel_dirs"], design_params
    
# ======================================================================================
# 20. グラフの表示高さを一括計算するサブルーチン
# ======================================================================================
def calculate_graph_height(base_height, ratios, show_wind, show_temp, show_tide):
    """
    各グラフの表示比率と基準縦幅から、最終的なグラフの合計高さを計算する。
    """
    # 1. 基本となる比率の合計（風向・風速 + 気温）
    base_ratio_total = ratios[0] + ratios[1]
    
    # 2. 1単位あたりのピクセル高さ
    fixed_unit_h = base_height / base_ratio_total 
    
    # 3. アイコン表示用のマージン（風向きが表示されている時のみ）
    icon_margin = 0.45 if show_wind else 0.0
    
    # 4. 各項目の表示可否に応じた高さの積み上げ
    auto_height = icon_margin
    if show_wind:
        auto_height += ratios[0] * fixed_unit_h
    if show_temp:
        auto_height += ratios[1] * fixed_unit_h
    if show_tide:
        auto_height += ratios[2] * fixed_unit_h
        
    return auto_height
    
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
    
    # ==================================================================================
    # 地点選択ロジック（最終安定版）：詳細地名と「地図で指定」を共存
    # ==================================================================================
    master = CONFIG["LOCATION_MASTER"].copy()
    display_options = {}
    
    # 1. マスター（固定の場所）を登録
    for name, coords in master.items():
        display_options[f"{name} ({coords[0]:.4f}, {coords[1]:.4f})"] = name

    # 2. 地図で取得した詳細地名を登録（マスターにない場合のみ）
    current_name = st.session_state.last_basho
    if current_name not in master and current_name != "地図で指定":
        dynamic_label = f"📍 {current_name} ({st.session_state.lat:.4f}, {st.session_state.lon:.4f})"
        display_options[dynamic_label] = current_name

    # 3. 「地図で指定」スイッチを必ずリストに含める
    # これにより、地図表示がOFFでもこれを選べば地図が開く機能を維持します
    map_label = f"🗺️ 地図で指定"
    display_options[map_label] = "地図で指定"

    # 4. 逆引き辞書と現在の選択位置の特定
    reverse_display = {v: k for k, v in display_options.items()}
    current_display_val = reverse_display.get(current_name, map_label)
    
    options_list = list(display_options.keys())
    try:
        default_idx = options_list.index(current_display_val)
    except ValueError:
        default_idx = 0

    # 5. セレクトボックス表示
    selected_display = st.selectbox("地点を選択してください", options_list, index=default_idx)
    basho = display_options[selected_display]

    # 6. 選択変更時の制御（既存の自動地図表示ロジックを維持）
    if basho != st.session_state.last_basho:
        st.session_state.last_basho = basho
        if basho in master:
            st.session_state.lat, st.session_state.lon = master[basho]
            st.session_state.show_map_state = False # 固定地点なら地図を閉じる
        elif basho == "地図で指定":
            st.session_state.show_map_state = True  # 【重要】地図を自動表示
        
        st.cache_data.clear() 
        st.rerun()

        
    # ==================================================================================
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

    # --- グラフ生成の呼び出し (戻り値に start_idx, df を追加) ---
    img_b64, ratio_info, start_idx, df_from_graph = generate_high_res_graph(
        st.session_state.lat, st.session_state.lon, danger_v, tuple(sel_dirs), design_params, now_jst
    )
    
    if img_b64:
        df_for_icons = fetch_weather_data(st.session_state.lat, st.session_state.lon, 8)
        if df_for_icons is not None:
            dpi = design_params["graph_dpi"]
            display_width = int(design_params["width"] * dpi)
            min_w = design_params["min_container_width"]
            # design_params から icon_margin を取得（なければ 0）
            icon_margin = design_params.get("icon_margin", 0)
        
            
            # padding_df = pd.DataFrame({'time': [df_for_icons['time'].iloc[0] - timedelta(hours=i) for i in range(1, 4)][::-1]})
            # df_full = pd.concat([padding_df, df_for_icons], ignore_index=True)
            
            icons_html = generate_weather_icons_html(
                df_from_graph, ratio_info, display_width, start_idx, icon_margin
            )
            
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

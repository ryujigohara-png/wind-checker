# -*- coding: utf-8 -*-
# ベータ版　更新 2026.1.8 2245 map改造中 4列column方式比率スライドバーするも縦崩壊は治らない。
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
    "DIAL_H_GAP": 0,      # ダイアログ内カラムの水平余白（初期値）
    "DIAL_V_GAP": 0,      # ダイアログ内セクションの垂直余白（初期値）
    "MAP_WIDTH": 400,     # 地図の幅
    "MAP_HEIGHT": 350,    # 地図の高さ
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
    "DEFAULT_ICON_MARGIN": 0,     # アイコンHTMLの下マージン(px)
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
        "錦江湾(鹿児島県)": (31.590, 130.600),
        "ニューヨーク(米国)": (40.7128, -74.0060),
        "ロンドン(英国)": (51.5074, -0.1278)
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

# ======================================================================================
# 3. 気象データをAPIから取得するサブルーチン
# ======================================================================================
def fetch_weather_data(lat, lon, days):
    import requests
    import pandas as pd
    
    # timezone=auto を指定
    url = f"https://api.open-meteo.com/v1/forecast?latitude={lat}&longitude={lon}&hourly=temperature_2m,wind_speed_10m,wind_direction_10m,weather_code,precipitation&timezone=auto&wind_speed_unit=ms&forecast_days={days}"
    
    try:
        response = requests.get(url).json()
        df = pd.DataFrame(response["hourly"])
        
        # 変数 y: APIが返す現地のUTC時差（秒）
        local_offset_s = response.get("utc_offset_seconds", 0)
        
        # APIが返した「現地時間の数字」をそのままNaive（時差情報なし）で保持
        df['time'] = pd.to_datetime(df['time']).dt.tz_localize(None)
        
        # 現地の時差秒数を属性として保存
        df.attrs['local_offset_seconds'] = local_offset_s
        
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
    except Exception as e:
        print(f"Error fetching weather data: {e}")
        return None

# ======================================================================================
# 4. 潮位レベルを計算するサブルーチン
# ======================================================================================
def get_tide_level(times):
    from datetime import datetime
    import numpy as np
    import pandas as pd
    
    # 基準となる満潮時刻（Naive）
    # 2025/1/1 06:00 (UTC想定) を基準点とする
    base_full_tide = datetime(2025, 1, 1, 6, 0)
    cycle_hours = 12.42
    levels = []
    
    for t in times:
        if pd.isna(t):
            levels.append(np.nan)
            continue
        
        # --- 修正の核心：計算の不整合を防ぐ ---
        # df['time'] が今回の修正で Naive（タイムゾーンなし）に統一されたため、
        # そのまま naive な datetime として扱い、基準時刻との差分を計算します。
        # 万が一タイムゾーン情報が含まれていた場合でも、replace(tzinfo=None) で除去して
        # 型エラー（TypeError）を確実に防ぎます。
        t_naive = t.replace(tzinfo=None) if hasattr(t, 'tzinfo') and t.tzinfo is not None else t
        
        # 基準時刻からの経過時間（時間単位）を算出
        hours_from_base = (t_naive - base_full_tide).total_seconds() / 3600
        
        # 正弦波による潮位計算（-100 ～ 100 の範囲）
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
    
# ======================================================================================
# 8. グラフの共通軸設定を適用するサブルーチン
# ======================================================================================
def apply_common_axis_settings(ax, df, formatter, now_jst, design_params):
    """
    グラフの共通軸設定を適用する。
    ブラウザの時差(x)と、現地の時差(y)を動的に取得し、現在時刻のラインを算出する。
    """
    import matplotlib.dates as mdates
    import matplotlib.pyplot as plt
    from datetime import timedelta

    # 変数 x: ブラウザ（実行環境）の時差を動的に取得
    # now_jst がタイムゾーン情報を持っている場合、そのオフセットを秒で取得する
    browser_offset = now_jst.utcoffset()
    browser_offset_s = browser_offset.total_seconds() if browser_offset else 0
    
    # 変数 y: 現地のUTC時差
    local_offset_s = df.attrs.get('local_offset_seconds', 0)
    
    # 計算：[ブラウザ時刻] - [ブラウザ時差x] + [現地時差y] = 現地の今の数字
    # 一旦 UTC に戻してから現地の時差を足す計算を、すべて秒単位で行う
    draw_now = now_jst.replace(tzinfo=None) - timedelta(seconds=browser_offset_s) + timedelta(seconds=local_offset_s)

    # 現在時刻ラインを描画
    ax.axvline(draw_now, color='blue', linestyle='-', alpha=0.6, linewidth=CONFIG["VLINE_WIDTH"])
    
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

    # 曜日の色分け設定
    fig = ax.figure
    fig.canvas.draw()
    labels = ax.get_xticklabels()
    for label in labels:
        text = label.get_text()
        if '(' in text:
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
    ブラウザの時差と現地の時差の差分を用いて、表示範囲を現地時間基準で切り出す。
    """
    import pandas as pd
    import io
    import base64
    from datetime import timedelta
    import matplotlib.pyplot as plt

    # 1. データ取得
    df_raw = fetch_weather_data(lat, lon, 9)
    if df_raw is None: return None, (0, 0), 0, None
    
    # 2. ブラウザと現地の時差から、現地の現在時刻を計算
    browser_offset = now_jst.utcoffset()
    browser_offset_s = browser_offset.total_seconds() if browser_offset else 0
    local_offset_s = df_raw.attrs.get('local_offset_seconds', 0)
    
    # 現地の現在時刻（数字のみ）を算出
    now_local = now_jst.replace(tzinfo=None) - timedelta(seconds=browser_offset_s) + timedelta(seconds=local_offset_s)
    
    # 3. 描画開始（グラフ左端）の設定
    display_start_time = now_local.replace(hour=(now_local.hour // 3) * 3, minute=0, second=0, microsecond=0)
    padding_start_time = display_start_time - timedelta(hours=3)
    
    # 4. データの切り出し
    df = df_raw[df_raw['time'] >= padding_start_time].copy().reset_index(drop=True)
    df = df.head(195)
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
                    font-family: 'Noto Sans JP', sans-serif; color: #333; z-index: 5;
                    white-space: nowrap;">
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
                        font-size: 32px; line-height: 1;
                        z-index: 5;">
                {icon}
            </div>'''
    
    # 最終的なHTMLコンテナ（デバッグ用の高さを35pxに戻す）
    return f'<div style="position: relative; width: {display_width}px; height: 35px; margin-bottom: {icon_margin}px; overflow: visible;">{icon_html}</div>'
    

# ======================================================================================
# 20. サイドバーからグラフ表示設定を詳細ダイアログで一括変更するサブルーチン（正規版表現・完全復旧）
# ======================================================================================
@st.dialog("グラフ表示設定の詳細")
def show_settings_dialog():
    """
    正規版のスクリーンショットに基づき、文言・順序・刻み値を完全に復元したダイアログ。
    開発者モード時のみ、地図ダイアログ用の余白調整スライダーを表示する。
    適用ボタン押下時にのみ session_state と localStorage を更新する。
    """
    import streamlit as st

    # --- 1. 表示設定（トグル） ---
    st.subheader("表示設定")
    d_show_wind = st.toggle("風向・風速", value=st.session_state.get("show_wind", CONFIG["SHOW_WIND"]))
    d_show_temp = st.toggle("気温", value=st.session_state.get("show_temp", CONFIG["SHOW_TEMP"]))
    d_show_tide = st.toggle("潮位", value=st.session_state.get("show_tide", CONFIG["SHOW_TIDE"]))
    d_show_w_text = st.toggle("天気詳細文字を表示", value=st.session_state.get("show_w_text", CONFIG["SHOW_W_TEXT"]))
    d_show_dir_name = st.toggle("風向名を表示", value=st.session_state.get("show_dir_name", CONFIG["SHOW_DIR_NAME"]))

    # --- 2. サイズ・文字（スライダー） ---
    w_cfg, h_cfg, f_cfg = CONFIG["SLIDER_WIDTH"], CONFIG["SLIDER_HEIGHT"], CONFIG["SLIDER_FONT"]
    d_width = st.slider("横幅 (inch)", w_cfg["min"], w_cfg["max"], float(st.session_state.get("width", CONFIG["GRAPH_WIDTH"])), step=w_cfg["step"])
    d_base_h = st.slider("基準縦幅 (inch)", h_cfg["min"], h_cfg["max"], float(st.session_state.get("base_height", CONFIG["GRAPH_HIGHT"])), step=h_cfg["step"])
    d_base_f = st.slider("グラフ内文字", f_cfg["min"], f_cfg["max"], int(st.session_state.get("base_font_size", CONFIG["GRAPH_FONT_SIZE"])))
    d_label_f = st.slider("軸ラベル文字", f_cfg["min"], f_cfg["max"], int(st.session_state.get("label_font_size", CONFIG["LABEL_SIZE"])))
    
    st.markdown("---")
    d_danger_v = st.number_input("危険風速ライン(m/s)", value=float(st.session_state.get("danger_v", CONFIG["DEFAULT_DANGER_V"])), step=1.0)

    # --- 3. 色付風向選択（2列チェックボックス） ---
    st.subheader("色付風向選択")
    current_sel = st.session_state.get("sel_dirs", list(CONFIG["DEFAULT_DIRS"]))
    new_sel_dirs = []
    cols = st.columns(2)
    for i, d in enumerate(ALL_DIRECTIONS):
        with cols[i % 2]:
            if st.checkbox(d, value=(d in current_sel), key=f"dlg_dir_{d}"):
                new_sel_dirs.append(d)

    # --- 4. 開発者用調整（地図ダイアログ余白調整を追加） ---
    is_dev_url = st.query_params.get("mode") == "dev"
    if is_dev_url:
        st.markdown("---")
        st.subheader("開発用詳細設定")
        d_min_w = st.slider("コンテナ最小幅 (px)", 500, 5000, int(st.session_state.get("min_container_width", 2500)), 100)
        d_dpi = st.radio("解像度 (DPI)", [200, 300], index=0 if st.session_state.get("graph_dpi", 200) == 200 else 1, horizontal=True)
        d_hspace = st.slider("グラフ間余白", -0.2, 1.5, float(st.session_state.get("hspace", CONFIG["HSPACE"])), 0.05)
        d_label_pad = st.slider("ラベル距離", -5, 10, int(st.session_state.get("label_pad", CONFIG["LABEL_PAD"])))

        # --- 新設：地図ダイアログ物理調整 ---
        st.subheader("地図ダイアログ物理調整")
        d_dial_h = st.slider("地図横余白 (H-Gap)", 0, 20, int(st.session_state.get("dial_h_gap", CONFIG["DIAL_H_GAP"])))
        d_dial_v = st.slider("地図縦余白 (V-Gap)", 0, 20, int(st.session_state.get("dial_v_gap", CONFIG["DIAL_V_GAP"])))

        st.subheader("降水量・アイコン位置調整")
        d_precip_y = st.slider("降水量ラベル高さ", 0.0, 2.0, float(st.session_state.get("precip_y", 1.0)), 0.05)
        d_icon_margin = st.slider("天気アイコン下余白", 0, 100, int(st.session_state.get("icon_margin", 10)), 5)

        st.subheader("比率設定")
        r = st.session_state.get("ratios", CONFIG["DEFAULT_RATIOS"])
        r0 = st.number_input("比率:風向", 0.5, 10.0, float(r[0]), 0.1)
        r1 = st.number_input("比率:気温", 0.5, 5.0, float(r[1]), 0.1)
        r2 = st.number_input("比率:潮位", 0.5, 5.0, float(r[2]), 0.1)
        d_ratios = [r0, r1, r2]
    else:
        # 非開発者モード時は現在の値またはCONFIG値を引き継ぐ
        d_min_w = st.session_state.get("min_container_width", 2500)
        d_dpi = st.session_state.get("graph_dpi", 200)
        d_hspace = st.session_state.get("hspace", CONFIG["HSPACE"])
        d_label_pad = st.session_state.get("label_pad", CONFIG["LABEL_PAD"])
        d_dial_h = st.session_state.get("dial_h_gap", CONFIG["DIAL_H_GAP"])
        d_dial_v = st.session_state.get("dial_v_gap", CONFIG["DIAL_V_GAP"])
        d_precip_y = st.session_state.get("precip_y", 1.0)
        d_icon_margin = st.session_state.get("icon_margin", 10)
        d_ratios = st.session_state.get("ratios", CONFIG["DEFAULT_RATIOS"])

    st.markdown("---")
    
    # --- 5. 適用ボタン ---
    if st.button("設定を適用してグラフ更新", type="primary", use_container_width=True):
        st.session_state.update({
            "show_wind": d_show_wind, "show_temp": d_show_temp, "show_tide": d_show_tide,
            "width": d_width, "base_height": d_base_h, "base_font_size": d_base_f,
            "label_font_size": d_label_f, "danger_v": d_danger_v, "sel_dirs": new_sel_dirs,
            "min_container_width": d_min_w, "graph_dpi": d_dpi, "show_w_text": d_show_w_text,
            "show_dir_name": d_show_dir_name, "hspace": d_hspace, "label_pad": d_label_pad,
            "dial_h_gap": d_dial_h, "dial_v_gap": d_dial_v,
            "precip_y": d_precip_y, "icon_margin": d_icon_margin, "ratios": d_ratios
        })
        save_settings_to_browser() # localStorage へ書き込み
        st.cache_data.clear()      # キャッシュクリア
        st.rerun()

# ======================================================================================
# 21. サイドバー、パラメータ設定
# ======================================================================================
def show_sidebar_controls():
    """
    サイドバーの入り口。ボタン一つでダイアログを起動する。
    """
    st.sidebar.header("表示設定")
    if st.sidebar.button("⚙ 詳細設定を変更する", use_container_width=True):
        show_settings_dialog()

    # 現時点の session_state を反映した design_params を返す
    h = calculate_graph_height(
        st.session_state.get("base_height", CONFIG["GRAPH_HIGHT"]),
        st.session_state.get("ratios", CONFIG["DEFAULT_RATIOS"]),
        st.session_state.get("show_wind", True),
        st.session_state.get("show_temp", True),
        st.session_state.get("show_tide", False)
    )

    design_params = {
        "width": st.session_state.get("width", CONFIG["GRAPH_WIDTH"]),
        "height": h,
        "base_font_size": st.session_state.get("base_font_size", CONFIG["GRAPH_FONT_SIZE"]),
        "label_font_size": st.session_state.get("label_font_size", CONFIG["LABEL_SIZE"]),
        "label_pad": st.session_state.get("label_pad", CONFIG["LABEL_PAD"]),
        "hspace": st.session_state.get("hspace", CONFIG["HSPACE"]),
        "show_wind": st.session_state.get("show_wind", CONFIG["SHOW_WIND"]),
        "show_temp": st.session_state.get("show_temp", CONFIG["SHOW_TEMP"]),
        "show_tide": st.session_state.get("show_tide", CONFIG["SHOW_TIDE"]),
        "show_w_text": st.session_state.get("show_w_text", CONFIG["SHOW_W_TEXT"]),
        "show_dir_name": st.session_state.get("show_dir_name", CONFIG["SHOW_DIR_NAME"]),
        "ratios": st.session_state.get("ratios", CONFIG["DEFAULT_RATIOS"]),
        "precip_y": st.session_state.get("precip_y", 1.0),
        "icon_margin": st.session_state.get("icon_margin", 10),
        "min_container_width": st.session_state.get("min_container_width", 2500),
        "graph_dpi": st.session_state.get("graph_dpi", 200)
    }
    return st.session_state.get("danger_v", 10.0), st.session_state.get("sel_dirs", []), design_params

# ======================================================================================
# 22. グラフの表示高さを一括計算するサブルーチン
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


# ==========================================================================================
# 30. 地図UIをダイアログで表示するサブルーチン (完全復旧・安定版)
# ==========================================================================================
@st.dialog("📍 地図で指定")
def show_location_map_dialog():
    """
    既存の仕様（地名表示、📍移動、確定処理）をすべて復旧。
    崩れの原因となっていた矢印のみを排除し、地図幅は環境に合わせて自動最適化。
    """
    import folium
    from streamlit_folium import st_folium

    # --- 1. 座標と名称の取得 (一時保存領域 temp を活用) ---
    # 開いた直後は現在の値を temp にコピー
    if "temp_lat" not in st.session_state:
        st.session_state.temp_lat = st.session_state.lat
    if "temp_lon" not in st.session_state:
        st.session_state.temp_lon = st.session_state.lon
    if "temp_basho" not in st.session_state:
        st.session_state.temp_basho = st.session_state.last_basho

    # 画面表示用の現在値
    d_lat = st.session_state.temp_lat
    d_lon = st.session_state.temp_lon
    d_basho = st.session_state.temp_basho

    # --- 2. 既存仕様: タイトル下の地点情報表示 ---
    st.markdown(f"📍 **{d_basho}**")
    st.caption(f"({d_lat:.4f}, {d_lon:.4f})")

    # --- 3. メインUI (Fragment構造) ---
    @st.fragment
    def map_restore_fragment():
        # 地図の高さ設定 (幅はNoneで自動追従)
        h_px = st.session_state.get("map_h", 350)

        # 地図オブジェクト作成
        m = folium.Map(location=[d_lat, d_lon], zoom_start=13)
        # 📍マーカーを中心座標に固定して描画 (ここが動かない原因でした)
        folium.Marker(
            [st.session_state.temp_lat, st.session_state.temp_lon], 
            icon=folium.Icon(color='red')
        ).add_to(m)
        
        # 地図の描画 (width=Noneで親コンテナに合わせる)
        map_out = st_folium(
            m, width=None, height=h_px, 
            key=f"map_v35_fixed",
            returned_objects=["center"]
        )

        st.write("") # スペーサー

        # 既存仕様: 「地図中心に📍」ボタン
        if st.button("地図中心に📍", use_container_width=True):
            if map_out and map_out.get("center"):
                # 地図の中心座標を取得して temp に保存
                st.session_state.temp_lat = map_out["center"]["lat"]
                st.session_state.temp_lon = map_out["center"]["lng"]
                # 名称を再取得
                with st.spinner("地名取得中..."):
                    st.session_state.temp_basho = fetch_location_name(
                        st.session_state.temp_lat, st.session_state.temp_lon
                    )
                st.rerun(scope="fragment") # 📍を移動させるためにフラグメント内を再描画

        # 確定・中止ボタン
        c1, c2 = st.columns(2)
        with c1:
            if st.button("確定", use_container_width=True):
                # temp から本番環境へ書き戻し
                st.session_state.lat = st.session_state.temp_lat
                st.session_state.lon = st.session_state.temp_lon
                st.session_state.last_basho = st.session_state.temp_basho
                # メイン画面の更新フラグを立てる
                st.session_state.needs_graph_update = True
                # tempを掃除して閉じる
                for k in ["temp_lat", "temp_lon", "temp_basho"]: st.session_state.pop(k, None)
                st.rerun()

        with c2:
            if st.button("中止", use_container_width=True):
                for k in ["temp_lat", "temp_lon", "temp_basho"]: st.session_state.pop(k, None)
                st.rerun()

    map_restore_fragment()
    
# ==========================================================================================
# 30_1. 座標から地名を取得するサブルーチン (fetch_location_name)
# ==========================================================================================
def fetch_location_name(lat, lon):
    """Nominatim APIから「当該レベル＋その1つ下のレベル」を確実に結合して取得する"""
    try:
        url = f"https://nominatim.openstreetmap.org/reverse?format=json&lat={lat}&lon={lon}&zoom=18"
        headers = {"User-Agent": "WindChecker/2.0"}
        response = requests.get(url, headers=headers, timeout=5)
        if response.status_code == 200:
            addr = response.json().get("address", {})
            
            # 階層の定義（広域から詳細へ）
            levels = [
                addr.get("city") or addr.get("town") or addr.get("village") or addr.get("suburb"), # 市町村・区
                addr.get("neighbourhood") or addr.get("road") or addr.get("quarter") or addr.get("hamlet") # 町丁・道路
            ]
            
            # Noneを除去し、重複を除いて有効なものを最大2つ選ぶ
            valid_parts = []
            for p in levels:
                if p and p not in valid_parts:
                    valid_parts.append(p)
            
            if len(valid_parts) >= 2:
                return f"{valid_parts[0]} {valid_parts[1]}"
            elif len(valid_parts) == 1:
                return valid_parts[0]
            
            return "指定地点"
        return "指定地点"
    except:
        return "指定地点"

# ==========================================================================================
# 82. ブラウザへの保存を実行するサブルーチン
# ==========================================================================================
def save_settings_to_browser():
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
        "is_dev_mode": st.session_state.get("is_dev_mode", False),
        "label_pad": st.session_state.get("label_pad", CONFIG["LABEL_PAD"]),
        "hspace": st.session_state.get("hspace", CONFIG["HSPACE"]),
        "show_w_text": st.session_state.get("show_w_text", CONFIG["SHOW_W_TEXT"]),
        "show_dir_name": st.session_state.get("show_dir_name", CONFIG["SHOW_DIR_NAME"]),
        "ratios": st.session_state.get("ratios", CONFIG["DEFAULT_RATIOS"]),
        # 【重要】お気に入りリストを保存対象に含める
        "user_locations": st.session_state.get("user_locations", []),
        "map_lat": st.session_state.get("map_lat", st.session_state.lat),
        "map_lon": st.session_state.get("map_lon", st.session_state.lon),
        "temp_label": st.session_state.get("temp_label", None)
    }
    json_data = json.dumps(save_data, ensure_ascii=False)
    # クォートのエスケープ処理を追加してJSエラーを防止
    escaped_json = json_data.replace("'", "\\'")
    components.html(
        f"""<script>localStorage.setItem("{CONFIG['STORAGE_KEY']}", '{escaped_json}');</script>""",
        height=0,    )

# ==========================================================================================
# 83. ステート更新・保存・再描画を一本化するサブルーチン (新規追加)
# ==========================================================================================
def update_state_and_save(updates_dict):
    """
    引数 updates_dict に基づき st.session_state を更新し、
    LocalStorageへ即座に書き出し、st.rerun() を実行する。
    """
    for key, value in updates_dict.items():
        st.session_state[key] = value
    save_settings_to_browser()
    time.sleep(0.1)
    st.rerun()

# ==========================================================================================
# 90. ブラウザのlocalStorageと設定を同期するサブルーチン
# ==========================================================================================
def sync_all_settings():
    STORAGE_KEY = CONFIG['STORAGE_KEY']
    
    # 初期化回避
    init_vars = {
        "show_wind": CONFIG["SHOW_WIND"],
        "show_temp": CONFIG["SHOW_TEMP"],
        "show_tide": CONFIG["SHOW_TIDE"],
        "lat": CONFIG["DEFAULT_LAT"],
        "lon": CONFIG["DEFAULT_LON"],
        "last_basho": CONFIG["DEFAULT_BASHO"],
        "width": CONFIG["GRAPH_WIDTH"],
        "base_height": CONFIG["GRAPH_HIGHT"],
        "base_font_size": CONFIG["GRAPH_FONT_SIZE"],
        "label_font_size": CONFIG["LABEL_SIZE"],
        "danger_v": CONFIG["DEFAULT_DANGER_V"],
        "sel_dirs": CONFIG["DEFAULT_DIRS"]
    }
    
    for var_name, default_val in init_vars.items():
        if var_name not in st.session_state:
            st.session_state[var_name] = default_val

    if st.session_state.get("initialized"):
        return

    js_query = f"localStorage.getItem('{STORAGE_KEY}') || 'EMPTY'"
    stored_data = streamlit_js_eval(js_expressions=js_query, key="init_load_settings_v3")

    if stored_data is None:
        st.stop()

    if stored_data == "EMPTY" or stored_data == "":
        st.session_state.initialized = True
    else:
        try:
            data = json.loads(stored_data)
            st.session_state.lat = float(data.get("lat", CONFIG["DEFAULT_LAT"]))
            st.session_state.lon = float(data.get("lon", CONFIG["DEFAULT_LON"]))
            st.session_state.last_basho = data.get("basho", CONFIG["DEFAULT_BASHO"])
            st.session_state.user_locations = data.get("user_locations", [])
            st.session_state.map_lat = float(data.get("map_lat", st.session_state.lat))
            st.session_state.map_lon = float(data.get("map_lon", st.session_state.lon))
            st.session_state.temp_label = data.get("temp_label", None)
            st.session_state.show_wind = data.get("show_wind", CONFIG["SHOW_WIND"])
            st.session_state.show_temp = data.get("show_temp", CONFIG["SHOW_TEMP"])
            st.session_state.show_tide = data.get("show_tide", CONFIG["SHOW_TIDE"])
            st.session_state.width = float(data.get("width", CONFIG["GRAPH_WIDTH"]))
            st.session_state.base_height = float(data.get("base_height", CONFIG["GRAPH_HIGHT"]))
            st.session_state.base_font_size = int(data.get("base_font_size", CONFIG["GRAPH_FONT_SIZE"]))
            st.session_state.label_font_size = int(data.get("label_font_size", CONFIG["LABEL_SIZE"]))
            st.session_state.danger_v = float(data.get("danger_v", CONFIG["DEFAULT_DANGER_V"]))
            st.session_state.sel_dirs = data.get("sel_dirs", CONFIG["DEFAULT_DIRS"])
            st.session_state.is_dev_mode = data.get("is_dev_mode", CONFIG.get("SHOW_DEV_MODE", False))
            st.session_state.label_pad = data.get("label_pad", CONFIG["LABEL_PAD"])
            st.session_state.hspace = data.get("hspace", CONFIG["HSPACE"])
            st.session_state.show_w_text = data.get("show_w_text", CONFIG["SHOW_W_TEXT"])
            st.session_state.show_dir_name = data.get("show_dir_name", CONFIG["SHOW_DIR_NAME"])
            st.session_state.ratios = data.get("ratios", CONFIG["DEFAULT_RATIOS"])
            # 【重要】お気に入りリストの復元
            st.session_state.user_locations = data.get("user_locations", [])
            st.session_state.initialized = True
            st.rerun()
        except Exception:
            st.session_state.initialized = True

# ======================================================================================
# 91. アプリ全体の共通スタイルを定義するサブルーチン
# ======================================================================================
def render_custom_css():
    """
    アプリ全体のCSSスタイルを定義する。
    正規版で定義されていたスクロールコンテナ等のスタイルを管理。
    """
    st.markdown("""
        <style>
            .block-container { padding-top: 2rem !important; padding-bottom: 0rem !important; }
            .scroll-container { 
                overflow-x: auto; 
                background: white; 
                border: 1px solid #ddd; 
                width: 100%; 
            }
        </style>
    """, unsafe_allow_html=True)

# ======================================================================================
# 92. 地点選択を管理するモジュール（正規版コードを忠実に再現）
# ======================================================================================
def render_location_selector_module():
    """
    メイン画面上部に場所選択バーとお気に入りボタンを表示し、選択変更を監視する。
    """
    # 19番のサブルーチンで選択肢リストを作成
    display_list, total_data = get_combined_location_list(
        CONFIG["LOCATION_MASTER"], 
        st.session_state.lat, 
        st.session_state.lon
    )

    # 18番のサブルーチンで選択バーを表示
    selected_label = show_favorite_control_bar(
        display_list, 
        st.session_state.last_basho, 
        st.session_state.lat, 
        st.session_state.lon, 
        st.session_state.last_basho
    )

    # 選択が変更された場合の処理
    if selected_label == "地図で指定":
        show_location_map_dialog()
    elif selected_label != st.session_state.last_basho:
        # 新しい地点の座標と名前を取得
        new_lat, new_lon, new_name = total_data[selected_label]
        # 状態更新・保存・描画フラグON
        update_state_and_save({
            "lat": new_lat, 
            "lon": new_lon, 
            "last_basho": selected_label,
            "needs_graph_update": True
        })
        st.rerun()
    
    return st.session_state.last_basho

# ======================================================================================
# 92_1. お気に入り・プリセット・地図指定を統合するサブルーチン（構造化・完全版）
# ======================================================================================
def get_combined_location_list(preset_master, current_lat, current_lon):
    """
    お気に入り(user_locations)、既定値(preset_master)、一時地点、地図指定を統合したリストを返す。
    """
    # LocalStorageから読み込まれているユーザー保存地点を取得
    favorites = st.session_state.get("user_locations", [])
    total_data = {}
    display_list = []

    # 1. 📍お気に入り（LocalStorage保存分）を最優先
    for fav in favorites:
        # 地名に 📍 がなければ付与して区別しやすくする
        name = fav['name'] if fav['name'].startswith("📍") else f"📍 {fav['name']}"
        label = f"{name} ({fav['lat']:.4f}, {fav['lon']:.4f})"
        display_list.append(label)
        total_data[label] = (fav['lat'], fav['lon'], name)

    # 2. プリセット（CONFIG["LOCATION_MASTER"] 定義分）
    for name, coords in preset_master.items():
        if name not in ["現在地を取得", "地図で指定"]:
            label = f"{name} ({coords[0]:.4f}, {coords[1]:.4f})"
            display_list.append(label)
            total_data[label] = (coords[0], coords[1], name)

    # 3. 一時的な確定地点（地図で指定した直後など、まだ保存されていない地点）
    t_label = st.session_state.get("temp_label")
    if t_label and t_label not in display_list:
        display_list.insert(0, t_label) # リストの先頭に挿入
        total_data[t_label] = (current_lat, current_lon, t_label.split(" (")[0])

    # 4. 地図で指定（操作トリガーとしての項目）
    map_label = "地図で指定"
    display_list.append(map_label)
    total_data[map_label] = (current_lat, current_lon, "地図で指定")

    return display_list, total_data

# ======================================================================================
# 92_2. 地点選択とお気に入り保存を1行に集約するサブルーチン（ダイアログ・保存フラグ対応）
# ======================================================================================
def show_favorite_control_bar(location_options, current_display_label, current_lat, current_lon, raw_name):
    """
    メイン画面上で地点選択と「⭐」保存ボタンを1行に表示する。
    """
    # --- お気に入り状態の判定（座標一致でチェック） ---
    favorites = st.session_state.get("user_locations", [])
    saved_data = next((f for f in favorites if abs(f['lat'] - current_lat) < 0.0001 and abs(f['lon'] - current_lon) < 0.0001), None)
    
    is_saved = saved_data is not None

    # --- 1行レイアウト (選択ボックスとボタン) ---
    c1, c2 = st.columns([0.92, 0.08])
    with c1:
        selected = st.selectbox(
            "地点を選択してください", 
            options=location_options, 
            index=location_options.index(current_display_label) if current_display_label in location_options else 0,
            label_visibility="collapsed"
        )
    with c2:
        if is_saved:
            # すでに保存されている地点はチェックマーク（無効ボタン）を表示
            st.button("✅", key="fav_saved_icon", disabled=True, help="お気に入り登録済み")
        else:
            # 未保存の地点（地図指定後など）の場合のみ、保存ボタンを表示
            if st.button("⭐", key="fav_save_action", help="この場所をお気に入りに登録"):
                # 地名部分を抽出し、ダイアログを起動
                pure_name = raw_name.split(" (")[0]
                show_favorite_registration_dialog(pure_name, current_lat, current_lon)

    return selected

# ======================================================================================
# 92_3. お気に入り地点の名称登録ダイアログ
# ======================================================================================
@st.dialog("お気に入り地点の名称確認")
def show_favorite_registration_dialog(default_name, lat, lon):
    """
    お気に入り登録時に「地名（逆引き住所）」を確認・修正してLocalStorageへ永続保存する。
    """
    st.write("この地点に名前をつけて「お気に入り」に保存します。")
    # 📍をデフォルトで付与
    initial_val = default_name if default_name.startswith("📍") else f"📍 {default_name}"
    new_name = st.text_input("登録名（修正可）", value=initial_val)
    
    col1, col2 = st.columns(2)
    with col1:
        if st.button("OK（保存実行）", use_container_width=True):
            if "user_locations" not in st.session_state:
                st.session_state.user_locations = []
            
            # リストに追加
            st.session_state.user_locations.append({
                "name": new_name,
                "lat": lat,
                "lon": lon
            })
            
            # LocalStorageへの保存と、再描画フラグを立てる
            update_state_and_save({
                "last_basho": new_name,
                "temp_label": None, # 一時ラベルはクリア
                "needs_graph_update": True
            })
            st.success(f"「{new_name}」を保存しました。")
            time.sleep(1)
            st.rerun()
            
    with col2:
        if st.button("Cancel", use_container_width=True):
            st.rerun()

    


# ======================================================================================
# 93. 【main機能分離】②地図表示モジュール
# ======================================================================================
def render_map_module():
    if st.button("🗺️ 地図表示", use_container_width=True):
        show_location_map_dialog()
        
# ======================================================================================
# 94. 【main機能分離】④グラフ更新・設定モジュール
# ======================================================================================
def render_update_control_module(basho):
    """
    現在地取得ボタンと、グラフ更新・時刻情報表示ボタンを1行に並べて表示する。
    """
    col1, col2 = st.columns([1, 1])
    with col1:
        handle_current_location_update_integrated()
    with col2:
        render_header_info(basho)

# ==========================================================================================
# 94_1. 現在地を取得し、状態を保存するサブルーチン
# ==========================================================================================
def handle_current_location_update_integrated():
    """
    「現在地を取得」ボタンを処理し、取得成功時に座標と地名を更新・保存する。
    """
    if st.button("🔄 📍現在地を取得　　　　　　　　　　", use_container_width=True):
        st.session_state.waiting_loc = True
        st.session_state.geo_key = f"geo_{datetime.now().timestamp()}"
        st.rerun()

    if st.session_state.get("waiting_loc"):
        # メッセージ表示（toastを使用して余白を最小化）
        st.toast("🛰️ 現在地を取得中...", icon="📍")
        
        # --- ここからロジックを高速版に差し替え ---
        # 従来の get_geolocation(component_key=...) ではなく、JSを直接実行して高速化
        js_code = """
        new Promise((resolve, reject) => {
            navigator.geolocation.getCurrentPosition(
                (pos) => {
                    resolve({
                        'coords': {
                            'latitude': pos.coords.latitude,
                            'longitude': pos.coords.longitude
                        }
                    });
                },
                (err) => { resolve(false); },
                { enableHighAccuracy: true, timeout: 5000, maximumAge: 0 }
            );
        })
        """
        # 実際の取得実行
        loc = streamlit_js_eval(js_expressions=js_code, key=st.session_state.get("geo_key"))
        # --- 差し替えここまで ---

        if loc:
            new_lat = round(loc['coords']['latitude'], 4)
            new_lon = round(loc['coords']['longitude'], 4)
            with st.spinner("現在地の地名を特定中..."):
                place_name = fetch_location_name(new_lat, new_lon)
            new_temp_label = f"{place_name} ({new_lat:.4f}, {new_lon:.4f})"
            st.session_state.waiting_loc = False
            
            # 座標が更新されるため、グラフ描画フラグをTrueにして保存
            # update_state_and_save ロジックは一切変更せず維持
            update_state_and_save({
                "lat": new_lat,
                "lon": new_lon,
                "last_basho": place_name,
                "temp_label": new_temp_label,
                "show_map": False,
                "needs_graph_update": True
            })
            st.rerun()
        elif loc is False:
            st.session_state.waiting_loc = False
            st.error("❌ 位置情報の取得に失敗しました。")
            if st.button("キャンセル"):
                st.rerun()

# ======================================================================================
# 94_2. グラフ更新ボタンと日時情報を描画するサブルーチン
# ======================================================================================
def render_header_info(current_basho_name):
    """
    グラフ更新ボタンと日時情報を描画する。
    ブラウザの現在時刻(now_jst)と現地の時差を使い、選択地点の正確な現地時刻を表示する。
    """
    # 関数冒頭で必要なものを定義・インポートし、UnboundLocalErrorを完全に回避
    import streamlit as st
    from datetime import datetime, timedelta

    # 1. 描画フラグの確認とクリア
    if st.session_state.get("needs_graph_update", True):
        # 描画が終わったらフラグを下ろす
        st.session_state.needs_graph_update = False
        
    # --- ここから下の時刻計算・表示ロジックは一切変更せず維持 ---
    import streamlit as st
    from datetime import datetime, timedelta

    # 基準となるブラウザ時刻（メイン処理から渡される now_jst を想定）
    now_jst = st.session_state.get('now_jst', datetime.now())

    try:
        # 1. 現地の時差情報を取得するために軽量なデータ取得を行う
        df_tmp = fetch_weather_data(st.session_state.lat, st.session_state.lon, 1)
        
        # 変数 x: ブラウザの時差を動的に取得
        browser_offset = now_jst.utcoffset()
        browser_offset_s = browser_offset.total_seconds() if browser_offset else 0
        
        # 変数 y: 現地の時差（fetch_weather_data で付与された属性）
        local_offset_s = df_tmp.attrs.get('local_offset_seconds', 0)
        
        # 2. 計算：[ブラウザ時刻] - [ブラウザ時差x] + [現地時差y]
        now_local = now_jst.replace(tzinfo=None) - timedelta(seconds=browser_offset_s) + timedelta(seconds=local_offset_s)
        
    except Exception:
        # エラー時はフォールバックとしてブラウザ時刻をそのまま表示
        now_local = now_jst.replace(tzinfo=None)

    date_time_str = now_local.strftime('%Y/%m/%d %H:%M:%S')
    # ボタンのラベルに現地時刻を反映
    update_label = f"🔄 グラフ更新 ({date_time_str})"
    
    if st.button(update_label, use_container_width=True):
        st.cache_data.clear()
        # 更新ボタン押下時も描画を許可する
        st.session_state.needs_graph_update = True
        st.rerun()

# ======================================================================================
# 95. 【main機能分離】⑤グラフ描画エリアモジュール
# ======================================================================================
def render_graph_area_module(danger_v, sel_dirs, design_params, now_jst):
    """
    グラフ描画エリアを管理するモジュール。
    正規版のスクロール構造を再現し、横長のグラフを適切に表示する。
    """
    # ---グラフ生成（サブルーチン12の戻り値4つ：img, ratio, idx, df） ---
    img_b64, ratio_info, start_idx, df_from_graph = generate_high_res_graph(
        st.session_state.lat, 
        st.session_state.lon, 
        danger_v, 
        tuple(sel_dirs), 
        design_params, 
        now_jst
    )
    
    # ---アイコン・グラフ描画 ---
    if img_b64:
        # 正規版のロジックに基づき、表示幅を計算
        dpi = design_params.get("graph_dpi", CONFIG.get("DPI", 200))
        display_width = int(design_params.get("width", CONFIG["GRAPH_WIDTH"]) * dpi)
        min_w = design_params.get("min_container_width", 800)
        icon_margin = design_params.get("icon_margin", 0)
        
        # アイコンHTML生成
        icons_html = generate_weather_icons_html(
            df_from_graph, 
            ratio_info, 
            display_width, 
            start_idx, 
            icon_margin
        )
        
        # グラフ本体のHTML（正規版通り width を指定して縮小を防ぐ）
        graph_html = f'<img src="data:image/png;base64,{img_b64}" style="width: {display_width}px; display: block;">'
        
        # スクロールコンテナ内に描画
        st.markdown(
            f'<div class="scroll-container">'
            f'<div style="width: {display_width}px; min-width: {min_w}px;">'
            f'{icons_html}{graph_html}'
            f'</div></div>', 
            unsafe_allow_html=True
        )

# ======================================================================================
# 100. メイン処理 (再構築版・スクロール対応)
# ======================================================================================
def main():
    # --- 1. 状態の初期化 ---
    if 'lat' not in st.session_state: st.session_state.lat = CONFIG["DEFAULT_LAT"]
    if 'lon' not in st.session_state: st.session_state.lon = CONFIG["DEFAULT_LON"]
    if 'last_basho' not in st.session_state: st.session_state.last_basho = CONFIG["DEFAULT_BASHO"]
    # 描画抑制フラグ：このフラグが True のときだけ重い処理を実行する
    if 'needs_graph_update' not in st.session_state:
        st.session_state.needs_graph_update = True

    # LocalStorageからの復元
    sync_all_settings()
    
    # スタイルとフォントの設定
    render_custom_css()
    setup_font(st.session_state.get("base_font_size", CONFIG["GRAPH_FONT_SIZE"]))
    
    # サイドバーのコントロール（設定変更があれば内部で needs_graph_update = True になる）
    danger_v, sel_dirs, design_params = show_sidebar_controls()
    
    st.title("Wind Checker v2")
    
    # 時間設定
    now_jst = datetime.now(timezone(timedelta(hours=9)))

    # --- 2. 各モジュールの描画 ---
    # 場所選択モジュール（返り値 basho は表示用の文字列）
    basho = render_location_selector_module()
    
    # 地図表示モジュール
    render_map_module()
    
    # 更新・情報表示モジュール（ここに basho を渡す）
    render_update_control_module(basho)
    
    # グラフエリア（ここでフラグを見て描画を行う）
    render_graph_area_module(danger_v, sel_dirs, design_params, now_jst)
    
    if st.session_state.get("is_dev_mode"):
        st.divider()
        st.write("Debug: Session State", st.session_state)

if __name__ == "__main__":
    main()
    

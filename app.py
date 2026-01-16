# -*- coding: utf-8 -*-
# 正規版　更新 2026.1.14 2200 daialog Cancel コンプリート版
"""
⛵ Pin_Weather! 機能仕様書（2026.01.14 改訂版）

1. データ統合・取得仕様
　• 気象データソース: Open-Meteo APIを使用し、全世界の陸上気象データを取得します。
　• 取得項目: 気温(2m)、風速(10m)、風向、天気コード、降水量を網羅。
　• 時間軸と時差対応: 最大9日間の予報を表示。APIの timezone=auto 設定を利用し、実行環境（ブラウザ）の時差と現地時間の時差を動的に計算してグラフの現在時刻ラインや数値表示に反映させます。
　• 潮位データ（大幅変更点）: 従来のシミュレーション方式から、Open-Meteo Marine APIによる実測値・予測値ベースの取得に変更されました。
    ◦ 近傍探索ロジック: 指定された座標が陸地などでデータがない場合、周囲30km圏内を8方向、複数の距離ステップ（0.05度〜0.25度）でランダムスキャンし、最初に見つかった海洋データポイントを採用します。
    ◦ 情報開示: 地点から離れた場所のデータを使用している場合、「〇〇方向 約〇kmのデータ」である旨をグラフ下部に赤字で明示します。
    ◦ 非表示制御: 30km圏内に海洋データが存在しない場合は、グラフエリアにその旨を表示してエラーを回避します。

2. 視覚化（グラフ描画）仕様
　• 高解像度画像生成: 風速・気温・潮位を統合したグラフを、サーバー側で高解像度（200/300 DPI選択可）な1枚のPNG画像として生成し、Base64形式でクライアントに転送します。
　• 風速棒グラフ:
    ◦ カラー判定: 10m/s以上は「クリムゾン（赤）」、特定風向かつ5m/s以上は「オレンジ」、3m/s以上は「スカイブルー」に色分けします。
    ◦ 垂直情報配置: 棒グラフの上部に風速数値、風向矢印、降水量（0mm超のみ）、設定により風向名や天気テキストを垂直に並べて表示します。
　• 気温折れ線グラフ: 3時間ごとの数値を**グラフ枠外（上部）**に配置し、視認性を高めています。
　• 潮位曲線グラフ: 海洋APIから取得したMSL（平均海面）基準の潮位データをcm単位でプロットし、曲線と塗りつぶしで視覚化します。
　• 天気アイコン: ☀️や☔などの絵文字アイコンを、グラフ画像上のタイムラインと物理的に一致する座標へ、HTMLコンテナを通じて動的に重ね合わせます。

3. 地点管理・操作仕様
　• コンパクト・コントロールパネル: スマホ閲覧を考慮し、場所選択、地図起動、現在地取得、更新ボタンを3行の省スペースに凝縮したUIを採用。
　• 現在地取得（高速版）: ブラウザのGPS機能を直接叩くJavaScript実行により、高速に現在地の座標を取得します。
　• 逆引き地名取得: Nominatim APIを使用し、座標から市町村名や町名を取得して表示・保存します。
　• 地図ダイアログ: Folium地図上でピンを動かし、中心地点の座標を確定できるダイアログ機能を搭載。操作時のズーム倍率保持にも対応しています。
　• お気に入り（My Spot）機能: 最大10件まで地点を保存可能。名称の編集や並べ替え、削除、10件超過時の警告機能を備えています。

4. システム仕様・カスタマイズ
　• LocalStorage永続化: 全てのグラフ設定（横幅、縦幅、文字サイズ、表示項目、危険風速設定、比率など）および「お気に入り地点」は、ブラウザのLocalStorageに自動保存され、再訪問時に復元されます。
　• 初期化フリーズ回避: ブラウザのストレージが空の状態でもアプリが停止しないよう、待機状態と空状態を判別する起動ロジックを実装しています。
　• 詳細設定ダイアログ: スライダーを用いたUIにより、グラフの余白、比率、文字サイズ、DPI、降水量ラベルの高さなどを微調整可能です。
　• 開発者モード: URLパラメータに ?mode=dev を付加することで、通常のユーザーには隠されている「コンテナ最小幅」や「地図ダイアログ余白」などのマイクロ調整機能が解放されます。

💡 補足: 今回の修正により、潮位グラフが「計算上の波」ではなく、**実際にその海域で予測されている潮位データ（海洋予報データ）**を反映するようになり、実用性が大幅に向上しました。
"""
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
# 0. 定数・基本設定 (CONFIG)
# ======================================================================================
CONFIG = {
    "TITLE_SIZE": 20,
    "SUBTITLE_SIZE": 16,
    # 表示設定（ユーザー設定）              
    "MAP_HEIGHT": 350,                  # 地図の高さ
    "SHOW_WIND": True,                  # 風向・風速グラフ表示
    "SHOW_TEMP": True,                  # 気温グラフ表示
    "SHOW_TIDE": False,                 # 潮位グラフ表示
    "SHOW_W_TEXT": False,               # 天気文字表示
    "SHOW_DIR_NAME": False,             # 風向名表示
    "GRAPH_WIDTH": 15,                  # グラフ横幅(inch)
    "GRAPH_HIGHT": 2.5,                 # グラフ縦幅(inch)
    "GRAPH_FONT_SIZE": 11,              # グラフ内文字サイズ
    "LABEL_SIZE": 7,                    # 軸ラベル文字サイズ
    "DEFAULT_DANGER_V": 10.0,           # 危険風速
    #開発者詳細設定
    "CONTENA_MIN_W": 2500,              # コンテナ最小幅(px)
    "DPI": 200,                         # 解像度 (DPI)
    "HSPACE": 0.75,                     # グラフ間余白
    "LABEL_PAD": 0,                     # ラベル距離
    "DIAL_H_GAP": 0,                    # 地図ダイアログ横余白 (H-Gap)
    "DIAL_V_GAP": 0,                    # 地図ダイアログ縦余白（V-Gap）
    "FAV_BTN_WIDTH": 30,                # MySpot編集ダイアログ ボタン幅(%)
    "FAV_NAME_LEN": 12,                 # MySpot編集ダイアログ 地名表示制限（文字）
    "DEFAULT_PRECIP_Y": 1.00,           # 降水量ラベル高さ（グラフ枠を1.0とした相対値）
    "DEFAULT_ICON_MARGIN": 0,           # 天気アイコン下余白(px)
    "DEFAULT_RATIOS": [4.0, 1.2, 0.8],  # グラフ比率設定
    # その他既定値
    "SHOW_DEV_MODE": False,                    # 開発者モード初期値
    "STORAGE_KEY": "wind_checker_settings_v2", # ローカルストレージキー
    "ANNOT_Y_STEP": 1.5,                       # 風向グラフ内文字間隔（文字高さに対する倍率）
    "ANNOT_BASE_Y": 0.5,                       # 風向グラフ内文字間隔1文字目まで（文字高さに対する倍率）
    "TEMP_COLOR": "darkorange",                # 危険風速色
    "ARROW_COLOR": "blue",                     # 弱風職
    "VLINE_WIDTH": 1.0,                        # 現在時刻ライン太さ
    "HLINE_WIDTH": 1.0,                        # 危険風速ライン太さ
    # スライダーの範囲設定
    "SLIDER_WIDTH": {"min": 13.0, "max": 30.0, "step": 1.0},
    "SLIDER_HEIGHT": {"min": 1.5, "max": 5.0, "step": 0.5},
    "SLIDER_FONT": {"min": 6, "max": 14, "step": 1},
    #ロケーション情報
    "DEFAULT_LAT": 31.337,                     # "高須沖(鹿児島県)"緯度
    "DEFAULT_LON": 130.795,                    # "高須沖(鹿児島県)"経度
    "DEFAULT_BASHO": "高須沖(鹿児島県)",        # 場所選定コンボボックスの選択値
    "DEFAULT_DIRS": ["南","南南西","南西","西南西","西","西北西","北西","北北西"],
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

# ======================================================================================
# 1. アプリケーション初期化サブルーチン (st.logo 導入版)
# ======================================================================================
def initialize_app():
    """
    ページ設定および、アプリ画面内へのロゴ表示 (st.logo) を実行する。
    ※この関数はアプリの実行開始直後に一度だけ呼び出すこと。
    """
    import streamlit as st
    import os
    from PIL import Image

    icon_path = "pin_weather_01.png"
    
    # 1. ページ設定（ブラウザタブ用）
    if os.path.exists(icon_path):
        app_icon = Image.open(icon_path)
        # アプリ画面内にロゴを表示 (サイドバー上部などに配置される)
        st.logo(icon_path, size="large") 
    else:
        app_icon = "⛵"

    st.set_page_config(
        page_title="Pin_Weather!",
        page_icon=app_icon,
        layout="wide"
    )
    
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
# 4. 潮位レベルを計算（既存仕様を厳守し、戻り値のみ拡張したバージョン）
# ======================================================================================
def get_tide_level(times, lat, lon):
    """
    Open-Meteo Marine APIを使用して潮位データを取得します。
    
    【変更点】
    1. ValueError防止のため if not times を if times is None or len(times) == 0 に変更。
    2. 戻り値を、データ(levels)と近傍フラグ(is_nearby)のタプルに変更。
    
    【厳守事項】
    時刻の参照（times[0], times[len(times)-1], t_naive の作成）は、
    以前正常に動作していたコードの記述をそのまま使用し、一切変更しません。
    """
    import requests
    import pandas as pd
    import numpy as np
    import time

    # 空判定の修正（Pandasの仕様によるValueErrorを物理的に回避）
    if times is None or len(times) == 0:
        return [], False

    # 型変換と NaN チェック
    try:
        f_lat = float(lat)
        f_lon = float(lon)
        if np.isnan(f_lat) or np.isnan(f_lon):
            return "NOT_SEA", False
    except:
        return "NOT_SEA", False

    # 【時刻参照：変更禁止】以前の記述をそのまま再現
    start_date = times[0].strftime('%Y-%m-%d')
    end_date = times[len(times) - 1].strftime('%Y-%m-%d')

    # 探索ステップの設定
    steps = [0.0, 0.05, 0.1, 0.2]
    search_offsets = []
    for s in steps:
        if s == 0.0:
            search_offsets.append((0.0, 0.0))
        else:
            search_offsets.extend([(s, 0), (-s, 0), (0, s), (0, -s)])

    res_json = None
    is_nearby = False

    # APIリクエスト実行
    for i, (d_lat, d_lon) in enumerate(search_offsets):
        target_lat = round(f_lat + d_lat, 4)
        target_lon = round(f_lon + d_lon, 4)
        
        url = "https://marine-api.open-meteo.com/v1/marine"
        params = {
            "latitude": target_lat,
            "longitude": target_lon,
            "hourly": "sea_level_height_msl",
            "start_date": start_date,
            "end_date": end_date,
            "timezone": "auto"
        }

        try:
            response = requests.get(url, params=params, timeout=5)
            if response.status_code == 200:
                data = response.json()
                t_list = data.get("hourly", {}).get("sea_level_height_msl", [])
                if t_list and any(v is not None for v in t_list[:24]):
                    # --- 修正箇所：データが見つかった時点で res_json を確定させる ---
                    res_json = data
                    # 0番目なら False（指定地点）、それ以外なら True（近傍地点）
                    is_nearby = True if i > 0 else False
                    break
        except:
            continue
        time.sleep(0.02)

    # ここで res_json があれば、i が 0 であっても確実にデータ処理へ進む
    if not res_json:
        return "NOT_SEA", False

    # データマッピング
    try:
        df_api = pd.DataFrame({
            "time": pd.to_datetime(res_json["hourly"]["time"]),
            "tide_height": res_json["hourly"]["sea_level_height_msl"]
        })
        df_api["time"] = df_api["time"].dt.tz_localize(None)

        levels = []
        for t in times:
            # 【時刻参照：変更禁止】以前の記述をそのまま再現
            t_naive = t.replace(tzinfo=None) if hasattr(t, 'tzinfo') and t.tzinfo is not None else t
            match_row = df_api[df_api["time"] == t_naive]
            if not match_row.empty:
                val = match_row.iloc[0]["tide_height"]
                levels.append(val if val is not None else np.nan)
            else:
                levels.append(np.nan)
        
        return levels, is_nearby
    except:
        return "NOT_SEA", False
      
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
    #潮位なぜか入っていた  df['tide_level'] = get_tide_level(df['time'])
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
    precip_y = design_params.get("precip_y", CONFIG["DEFAULT_PRECIP_Y"]) if design_params else 1.0
    
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
    graph_left_time = df['time'].iloc[0] 
    ax.text(graph_left_time, precip_y, "降水量mm　", 
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

# ======================================================================================
# 11. 潮位曲線グラフを描画するサブルーチン（ランダムスキャン・海洋データ版）
# ======================================================================================
def render_tide_curve_chart(ax, df):
    """
    Open-Meteo Marine APIから潮位を取得。
    探索の開始方向をランダムに決定し、30km圏内で最初に見つかった「海洋データ」を採用します。
    """
    import requests
    import pandas as pd
    import numpy as np
    import time
    import random
    from matplotlib.transforms import ScaledTranslation

    lat = df.attrs.get('lat', 35.0)
    lon = df.attrs.get('lon', 135.0)
    start_str = df['time'].iloc[0].strftime('%Y-%m-%d')
    end_str = df['time'].iloc[-1].strftime('%Y-%m-%d')
    label_fs = CONFIG.get("LABEL_SIZE", 10)

    tide_levels = None
    info_text = ""
    
    # --- 探索座標リストの作成（南北・東西を正しく定義） ---
    steps = [0.0, 0.05, 0.1, 0.15, 0.2, 0.25]
    search_points = []

    for s in steps:
        if s == 0:
            search_points.append((0, 0))
        else:
            # 8方向の定義（緯度プラスが北、経度プラスが東）
            ring = [
                (s, 0),    # 北
                (s, s),    # 北東
                (0, s),    # 東
                (-s, s),   # 南東
                (-s, 0),   # 南
                (-s, -s),  # 南西
                (0, -s),   # 西
                (s, -s)    # 北西
            ]
            # 各ステップごとに、開始地点をランダムにずらす
            start_idx = random.randint(0, 7)
            rotated_ring = ring[start_idx:] + ring[:start_idx]
            search_points.extend(rotated_ring)

    # 探索実行
    found = False
    for d_lat, d_lon in search_points:
        target_lat = lat + d_lat
        target_lon = lon + d_lon
        
        # [Open-Meteo Marine API](open-meteo.com) を使用
        # url = "marine-api.open-meteo.com"
        url = "https://marine-api.open-meteo.com/v1/marine"
        params = {
            "latitude": target_lat, "longitude": target_lon,
            "hourly": "sea_level_height_msl", "start_date": start_str, "end_date": end_str, "timezone": "auto"
        }
        
        try:
            response = requests.get(url, params=params, timeout=5)
            if response.status_code == 200:
                data = response.json()
                api_h = data.get("hourly", {}).get("sea_level_height_msl", [])

                if api_h and any(v is not None for v in api_h):
                    dist_km = round(np.sqrt((d_lat * 111)**2 + (d_lon * 111 * np.cos(np.radians(lat)))**2), 1)

                    if dist_km > 0.5: # わずかな誤差を除きメッセージ表示
                        # 方位の計算
                        angle = np.rad2deg(np.arctan2(d_lon * np.cos(np.radians(lat)), d_lat))
                        directions = ["北", "北東", "東", "南東", "南", "南西", "西", "北西", "北"]
                        res_dir = directions[int((angle + 22.5) % 360 // 45)]
                        # メッセージをより自然な表現に修正
                        info_text = f"※指定地点の最寄り（{res_dir}約{dist_km}km）の海洋データを表示しています。"
                    
                    df_api = pd.DataFrame({"api_t": pd.to_datetime(data["hourly"]["time"]), "h": api_h})
                    df_api["api_t"] = df_api["api_t"].dt.tz_localize(None)
                    tide_levels = [df_api[df_api["api_t"] == t.replace(tzinfo=None)].iloc[0]["h"] 
                                   if not df_api[df_api["api_t"] == t.replace(tzinfo=None)].empty else np.nan 
                                   for t in df['time']]
                    found = True
                    break
        except:
            continue
        time.sleep(0.01)

    # データなし処理
    if not found or tide_levels is None:
        ax.clear()
        ax.set_axis_off()
        ax.text(0.0, 0.5, "※指定地点の近傍(30km圏内)に有効な海洋データがないため表示されません", 
                transform=ax.transAxes, color="gray", fontsize=label_fs, ha='left', va='center')
        return

    # 描画処理
    df['tide_cm'] = [v * 100 if v is not None else np.nan for v in tide_levels]
    ax.plot(df['time'], df['tide_cm'], color="#1f77b4", linewidth=2, marker='o', markersize=3, markevery=3)
    ax.set_ylabel("潮位 (cm)", fontsize=label_fs)
    ax.grid(True, axis='y', linestyle='--', alpha=0.5)

    # 数値ラベル
    for i in range(0, len(df), 3):
        dt, val = df['time'].iloc[i], df['tide_cm'].iloc[i]
        if not pd.isna(val):
            ax.text(dt, 1.05, f"{val:.0f}", ha='center', va='bottom', color="#1f77b4", 
                    fontsize=label_fs, transform=ax.get_xaxis_transform())

    # メッセージ表示位置
    if info_text:
        offset = ScaledTranslation(0, - (label_fs * 3.5) / 72, ax.figure.dpi_scale_trans)
        trans = ax.transAxes + offset
        ax.text(0.0, 0.0, info_text, transform=trans, color="#d62728", 
                fontsize=label_fs - 1, ha='left', va='top')
      
# ======================================================================================
# 12. 高解像度グラフ画像を生成するサブルーチン（完全復旧版）
# ======================================================================================
@st.cache_data(show_spinner="グラフを生成中...", ttl=600)
def generate_high_res_graph(lat, lon, danger_v, selected_dirs_tuple, design_params, now_jst):
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
    
    now_local = now_jst.replace(tzinfo=None) - timedelta(seconds=browser_offset_s) + timedelta(seconds=local_offset_s)
    
    # 3. 描画開始の設定
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
        # 【修正の核心】戻り値を受け取らず、(ax, df) のみで呼び出す元の形に戻します
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
    
    # l_size_pt = CONFIG.get("LABEL_SIZE", 7)
    l_size_pt = st.session_state.get("label_font_size", CONFIG.get("LABEL_SIZE", 7))
    # グラフ内のフォントサイズ(pt)をpx相当に変換
    # header_fs_px = l_size_pt * 1.33
    header_fs_px = l_size_pt * 2.5
  
    # 「天気」見出しの配置：start_x（グラフ枠の左端）を基準にする
    # 12番の ax.text(graph_left_time, ..., ha='right') と揃えるため translateX(-100%) を使用
    label_pos_x = (start_x * display_width) - 16
    icon_html += f'''
        <div style="position: absolute; left: {label_pos_x}px; top: 15px; 
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
# 20. サイドバーからグラフ表示設定を詳細ダイアログで一括変更するサブルーチン
# ======================================================================================
@st.dialog("グラフ表示設定の詳細", dismissible=False)
def show_settings_dialog():
    """
    開発者モード時のみ、お気に入り管理ダイアログの「ボタン幅」と「文字数制限」を
    調整するためのスライダーを表示する機能を追加した完全版。
    """
    import streamlit as st

    # --- 1. 表示設定（トグル） ---
    st.subheader("表示設定")
    d_show_wind = st.toggle("風向・風速グラフ表示", value=st.session_state.get("show_wind", CONFIG["SHOW_WIND"]))
    d_show_temp = st.toggle("気温グラフ表示", value=st.session_state.get("show_temp", CONFIG["SHOW_TEMP"]))
    d_show_tide = st.toggle("潮位グラフ表示", value=st.session_state.get("show_tide", CONFIG["SHOW_TIDE"]))
    d_show_w_text = st.toggle("天気文字表示", value=st.session_state.get("show_w_text", CONFIG["SHOW_W_TEXT"]))
    d_show_dir_name = st.toggle("風向名表示", value=st.session_state.get("show_dir_name", CONFIG["SHOW_DIR_NAME"]))
    
    # --- 2. サイズ・文字（スライダー） ---
    w_cfg, h_cfg, f_cfg = CONFIG["SLIDER_WIDTH"], CONFIG["SLIDER_HEIGHT"], CONFIG["SLIDER_FONT"]
    d_width = st.slider("グラフ枠横幅 (inch)", w_cfg["min"], w_cfg["max"], float(st.session_state.get("width", CONFIG["GRAPH_WIDTH"])), step=w_cfg["step"])
    d_base_h = st.slider("グラフ枠縦幅 (inch)", h_cfg["min"], h_cfg["max"], float(st.session_state.get("base_height", CONFIG["GRAPH_HIGHT"])), step=h_cfg["step"])
    d_base_f = st.slider("グラフ内文字サイズ", f_cfg["min"], f_cfg["max"], int(st.session_state.get("base_font_size", CONFIG["GRAPH_FONT_SIZE"])))
    d_label_f = st.slider("軸ラベル文字サイズ", f_cfg["min"], f_cfg["max"], int(st.session_state.get("label_font_size", CONFIG["LABEL_SIZE"])))
    
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
    
    # --- 4. 開発者用調整 ---
    is_dev_url = st.query_params.get("mode") == "dev"
    if is_dev_url:
        st.markdown("---")
        st.subheader("開発用詳細設定")
        d_min_w = st.slider("コンテナ最小幅 (px)", 500, 5000, int(st.session_state.get("min_container_width", CONFIG["CONTENA_MIN_W"])), 100)
        d_dpi = st.radio("解像度 (DPI)", [200, 300], index=0 if st.session_state.get("graph_dpi", 200) == 200 else 1, horizontal=True)
        d_hspace = st.slider("グラフ間余白", -0.2, 1.5, float(st.session_state.get("hspace", CONFIG["HSPACE"])), 0.05)
        d_label_pad = st.slider("ラベル距離", -5, 10, int(st.session_state.get("label_pad", CONFIG["LABEL_PAD"])))
    
        st.subheader("地図ダイアログ調整")
        d_dial_h = st.slider("地図ダイアログ横余白 (H-Gap)", 0, 20, int(st.session_state.get("dial_h_gap", CONFIG["DIAL_H_GAP"])))
        d_dial_v = st.slider("地図ダイアログ縦余白 (V-Gap)", 0, 20, int(st.session_state.get("dial_v_gap", CONFIG["DIAL_V_GAP"])))
    
        st.subheader("MySpot編集ダイアログ調整")
        d_fav_w = st.slider("ボタン幅 (%)", 10, 45, int(st.session_state.get("fav_btn_width", CONFIG.get("FAV_BTN_WIDTH", 30))), 1)
        d_fav_len = st.slider("地名表示制限 (文字)", 5, 25, int(st.session_state.get("fav_name_len", CONFIG.get("FAV_NAME_LEN", 12))), 1)
    
        st.subheader("降水量・アイコン位置調整")
        d_precip_y = st.slider("降水量ラベル高さ", 0.0, 2.0, float(st.session_state.get("precip_y", CONFIG["DEFAULT_PRECIP_Y"])), 0.05)
        d_icon_margin = st.slider("天気アイコン下余白", 0, 100, int(st.session_state.get("icon_margin", CONFIG["DEFAULT_ICON_MARGIN"])), 5)
    
        st.subheader("グラフ縦比率設定")
        r = st.session_state.get("ratios", CONFIG["DEFAULT_RATIOS"])
        r0 = st.number_input("比率:風向", 0.5, 10.0, float(r[0]), 0.1)
        r1 = st.number_input("比率:気温", 0.5, 5.0, float(r[1]), 0.1)
        r2 = st.number_input("比率:潮位", 0.5, 5.0, float(r[2]), 0.1)
        d_ratios = [r0, r1, r2]
    else:
        d_min_w = st.session_state.get("min_container_width", CONFIG["CONTENA_MIN_W"])
        d_dpi = st.session_state.get("graph_dpi", CONFIG["DPI"])
        d_hspace = st.session_state.get("hspace", CONFIG["HSPACE"])
        d_label_pad = st.session_state.get("label_pad", CONFIG["LABEL_PAD"])
        d_dial_h = st.session_state.get("dial_h_gap", CONFIG["DIAL_H_GAP"])
        d_dial_v = st.session_state.get("dial_v_gap", CONFIG["DIAL_V_GAP"])
        d_fav_w = st.session_state.get("fav_btn_width", CONFIG.get("FAV_BTN_WIDTH", 30))
        d_fav_len = st.session_state.get("fav_name_len", CONFIG.get("FAV_NAME_LEN", 12))
        d_precip_y = st.session_state.get("precip_y", CONFIG["DEFAULT_PRECIP_Y"])
        d_icon_margin = st.session_state.get("icon_margin", CONFIG["DEFAULT_ICON_MARGIN"])
        d_ratios = st.session_state.get("ratios", CONFIG["DEFAULT_RATIOS"])
    
    st.markdown("---")
    
    # --- 5. リセットボタン (誤操作防止のため少し離して配置) ---
    if st.button("設定をすべて初期値に戻す", key="reset_all_settings", use_container_width=True):
        st.session_state.update({
            "show_wind": CONFIG["SHOW_WIND"], "show_temp": CONFIG["SHOW_TEMP"], "show_tide": CONFIG["SHOW_TIDE"],
            "width": CONFIG["GRAPH_WIDTH"], "base_height": CONFIG["GRAPH_HIGHT"], "base_font_size": CONFIG["GRAPH_FONT_SIZE"],
            "label_font_size": CONFIG["LABEL_SIZE"], "danger_v": CONFIG["DEFAULT_DANGER_V"], "sel_dirs": list(CONFIG["DEFAULT_DIRS"]),
            "min_container_width": CONFIG["CONTENA_MIN_W"], "graph_dpi": CONFIG["DPI"], "show_w_text": CONFIG["SHOW_W_TEXT"],
            "show_dir_name": CONFIG["SHOW_DIR_NAME"], "hspace": CONFIG["HSPACE"], "label_pad": CONFIG["LABEL_PAD"],
            "dial_h_gap": CONFIG["DIAL_H_GAP"], "dial_v_gap": CONFIG["DIAL_V_GAP"],
            "fav_btn_width": CONFIG.get("FAV_BTN_WIDTH", 30), "fav_name_len": CONFIG.get("FAV_NAME_LEN", 12),
            "precip_y": CONFIG["DEFAULT_PRECIP_Y"], "icon_margin": CONFIG["DEFAULT_ICON_MARGIN"], "ratios": CONFIG["DEFAULT_RATIOS"]
        })
        save_settings_to_browser()
        st.cache_data.clear()
        st.rerun()
    
    # --- 6. 実行・キャンセルボタン ---
    c_exec, c_cancel = st.columns(2)
    with c_exec:
        if st.button("設定を適用して更新", key="apply_all_settings", type="primary", use_container_width=True):
            st.session_state.update({
                "show_wind": d_show_wind, "show_temp": d_show_temp, "show_tide": d_show_tide,
                "width": d_width, "base_height": d_base_h, "base_font_size": d_base_f,
                "label_font_size": d_label_f, "danger_v": d_danger_v, "sel_dirs": new_sel_dirs,
                "min_container_width": d_min_w, "graph_dpi": d_dpi, "show_w_text": d_show_w_text,
                "show_dir_name": d_show_dir_name, "hspace": d_hspace, "label_pad": d_label_pad,
                "dial_h_gap": d_dial_h, "dial_v_gap": d_dial_v,
                "fav_btn_width": d_fav_w, "fav_name_len": d_fav_len,
                "precip_y": d_precip_y, "icon_margin": d_icon_margin, "ratios": d_ratios
            })
            save_settings_to_browser()
            st.cache_data.clear()
            st.rerun()
    with c_cancel:
        if st.button("キャンセルして戻る", key="cancel_all_settings", use_container_width=True):
            st.rerun()
      


# ======================================================================================
# 21. サイドバー、パラメータ設定（既存仕様維持・縦並び）
# ======================================================================================
def show_sidebar_controls():
    """
    サイドバーの入り口。ボタンは縦に並べる既存仕様を維持。
    """
    import streamlit as st
    
    st.sidebar.header("表示設定")
    
    # ユーザー指定通りの縦並び
    if st.sidebar.button("⚙ 詳細設定", use_container_width=True):
        show_settings_dialog()

    if st.sidebar.button("📍 My Spot 編集", use_container_width=True):
        manage_favorites_dialog()

    # 既存の計算ロジック（一切変更せず維持）
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
        "precip_y": st.session_state.get("precip_y", CONFIG["DEFAULT_PRECIP_Y"]),
        "icon_margin": st.session_state.get("icon_margin", CONFIG["DEFAULT_ICON_MARGIN"]),
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
# 30. 地図UIをダイアログで表示するサブルーチン (倍率維持・完全版)
# ==========================================================================================
@st.dialog("📍 地図で指定", dismissible=False)
def show_location_map_dialog():
    """
    タイトル下の重複表示を整理。
    「地図中心に📍」ボタン押下時に、マーカーを地図の物理的な中心に確実に表示させる。
    ユーザーが変更した倍率を維持したまま、地図中心を📍に合わせる。
    """
    import folium
    from streamlit_folium import st_folium

    # --- 1. 座標と名称の初期管理 ---
    if "temp_lat" not in st.session_state:
        st.session_state.temp_lat = st.session_state.lat
    if "temp_lon" not in st.session_state:
        st.session_state.temp_lon = st.session_state.lon
    if "temp_basho" not in st.session_state:
        # 初回表示時は現在の地名を表示
        st.session_state.temp_basho = st.session_state.last_basho
    
    # [追加] 現在の倍率を管理する変数（初期値は13）
    if "temp_zoom" not in st.session_state:
        st.session_state.temp_zoom = 13
    
    # --- 2. メインUI (Fragment構造) ---
    @st.fragment
    def map_final_fixed_fragment():
        # 表示整理
        st.markdown(f"📍 **{st.session_state.temp_basho}**")
    
        h_px = st.session_state.get("map_h", CONFIG["MAP_HEIGHT"])
    
        # 地図オブジェクト作成
        # [修正] zoom_startを固定せず、保持している倍率を適用する
        m = folium.Map(
            location=[st.session_state.temp_lat, st.session_state.temp_lon], 
            zoom_start=st.session_state.temp_zoom
        )
        
        # マーカーを中心座標に設置
        folium.Marker(
            [st.session_state.temp_lat, st.session_state.temp_lon], 
            icon=folium.Icon(color='red')
        ).add_to(m)
        
        # 地図の描画
        # [修正] returned_objectsに "zoom" を追加し、現在の倍率を取得可能にする
        map_out = st_folium(
            m, width=None, height=h_px, 
            key=f"map_v36_final",
            returned_objects=["center", "zoom"]
        )
    
        st.write("") 
    
        # 「地図中心に📍」ボタンのロジック
        if st.button("地図中心に📍", use_container_width=True):
            if map_out:
                # [追加] ユーザーが変更した「今の倍率」を保存
                if map_out.get("zoom") is not None:
                    st.session_state.temp_zoom = map_out["zoom"]
                
                # 地図の「現在の中心」を temp に保存
                if map_out.get("center"):
                    st.session_state.temp_lat = map_out["center"]["lat"]
                    st.session_state.temp_lon = map_out["center"]["lng"]
                    
                    # 名称を更新
                    with st.spinner("地名取得中..."):
                        raw_name = fetch_location_name(
                            st.session_state.temp_lat, st.session_state.temp_lon
                        )
                        st.session_state.temp_basho = f"{raw_name} ({st.session_state.temp_lat:.4f}, {st.session_state.temp_lon:.4f})"
                    
                    # フラグメント内を再描画して、テキスト・地図中心・📍をすべて同期
                    st.rerun(scope="fragment")
    
        # 確定・中止ボタン
        c1, c2 = st.columns(2)
        with c1:
            if st.button("確定", use_container_width=True):
                # メインの状態を更新
                st.session_state.lat = st.session_state.temp_lat
                st.session_state.lon = st.session_state.temp_lon
                st.session_state.last_basho = st.session_state.temp_basho
                
                # コンボボックスの選択肢に表示させるため temp_label に格納
                st.session_state.temp_label = st.session_state.temp_basho
                
                # グラフ描画を行うフラグを立てる
                st.session_state.needs_graph_update = True
                
                # 一時変数をクリア
                for k in ["temp_lat", "temp_lon", "temp_basho", "temp_zoom"]: 
                    st.session_state.pop(k, None)
                st.rerun()
    
        with c2:
            if st.button("中止", use_container_width=True):
                # グラフ描画を行わずに閉じる
                for k in ["temp_lat", "temp_lon", "temp_basho", "temp_zoom"]: 
                    st.session_state.pop(k, None)
                st.rerun()
    
    # フラグメントの実行
    map_final_fixed_fragment()
    
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

    # 選択が変更された場合の処理　地図Uと合わせる必要あり
    if selected_label == "地図で指定":
        show_location_map_dialog()
    elif selected_label != st.session_state.last_basho:
        # 新しい地点の座標と名前を取得
        new_lat, new_lon, new_name = total_data[selected_label]
        st.session_state.temp_lat, st.session_state.temp_lon, st.session_state.temp_basho = total_data[selected_label]
        
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
    import streamlit as st

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
# 92_3. お気に入り地点の名称登録ダイアログ（10件制限・選択維持対応）
# ======================================================================================
@st.dialog("お気に入り地点の名称確認", dismissible=False)
def show_favorite_registration_dialog(default_name, lat, lon):
    """
    お気に入り登録時に「地名」を確認・修正してLocalStorageへ永続保存する。
    10件制限チェックを行い、超過時は保存をブロックして警告を表示する。
    """
    import streamlit as st

    # 現在の登録件数を確認
    favorites = st.session_state.get("user_locations", [])
    if len(favorites) >= 10:
        st.error("🚨 お気に入りの登録制限（10件）に達しています。")
        st.write("「My Spot 編集」から不要な地点を削除してください。")
        if st.button("閉じる", use_container_width=True):
            st.rerun()
        return

    st.write(f"この地点を「お気に入り」に保存します。（現在: {len(favorites)}/10件）")
    # 📍をデフォルトで付与
    initial_val = default_name if default_name.startswith("📍") else f"📍 {default_name}"
    new_name = st.text_input("登録名（修正可）", value=initial_val)
    
    col1, col2 = st.columns(2)
    with col1:
        if st.button("OK（保存実行）", use_container_width=True, type="primary"):
            if "user_locations" not in st.session_state:
                st.session_state.user_locations = []
            
            # リストに追加
            st.session_state.user_locations.append({
                "name": new_name,
                "lat": lat,
                "lon": lon
            })
            
            # 📍付きの名前を現在の選択地点として保持
            st.session_state["last_basho"] = new_name
            st.session_state["temp_label"] = None

            # 保存処理
            if "save_settings_to_browser" in globals():
                save_settings_to_browser()
            elif "update_state_and_save" in globals():
                update_state_and_save({})

            st.rerun()
            
    with col2:
        if st.button("Cancel", use_container_width=True):
            st.rerun()

# ======================================================================================
# 92_4. My Spot（お気に入り）管理ダイアログ（2段構成・堅牢版）
# ======================================================================================
@st.dialog("My Spot（お気に入り）の編集", dismissible=False)
def manage_favorites_dialog():
    """
    スマホの標準挙動（縦並び）に準拠した設計。
    1段目に地名、2段目に操作ボタンを配置することで、横幅不足による崩れを根本的に回避する。
    """
    import streamlit as st

    # CSSは最小限。ボタンの押しやすさと視認性のみを調整
    st.markdown("""
        <style>
            /* ボタンの高さを指で押しやすいサイズに固定 */
            .stButton > button {
                height: 42px !important;
                margin-bottom: 4px !important;
            }
            /* 1地点ごとの区切りを明確にする */
            .spot-container {
                border: 1px solid rgba(151,166,195,0.2);
                border-radius: 8px;
                padding: 10px;
                margin-bottom: 12px;
                background-color: rgba(151,166,195,0.05);
            }
        </style>
    """, unsafe_allow_html=True)
    
    @st.fragment
    def internal_manager():
        if "user_locations" not in st.session_state:
            st.session_state.user_locations = []
        
        current_favs = list(st.session_state.user_locations)
        
        # 地点がある場合の表示
        if not current_favs:
            st.info("登録されている地点はありません。")
        else:
            st.caption(f"登録: {len(current_favs)} / 10 件")
    
            action_idx = None
            direction = 0 
            
            for i in range(len(current_favs)):
                item = current_favs[i]
                row_id = f"v_row_{i}_{item['lat']}_{item['lon']}"
                edit_key = f"is_editing_{row_id}"
                
                if edit_key not in st.session_state:
                    st.session_state[edit_key] = False
    
                # 地点ごとに枠で囲む
                with st.container(border=True):
                    if st.session_state[edit_key]:
                        # 名称編集モード
                        new_name = st.text_input("名前を変更", value=item['name'], key=f"in_{row_id}")
                        c_s, c_c = st.columns(2)
                        if c_s.button("保存", key=f"s_{row_id}", type="primary", use_container_width=True):
                            st.session_state.user_locations[i]['name'] = new_name
                            st.session_state[edit_key] = False
                            if "save_settings_to_browser" in globals(): save_settings_to_browser()
                            st.rerun(scope="fragment")
                        if c_c.button("戻る", key=f"c_{row_id}", use_container_width=True):
                            st.session_state[edit_key] = False
                            st.rerun(scope="fragment")
                    else:
                        # --- 1段目：地名（幅一杯に使用） ---
                        display_label = f" {item['name']} ({item['lat']:.3f}, {item['lon']:.3f})"
                        if st.button(display_label, key=f"b_{row_id}", use_container_width=True):
                            st.session_state[edit_key] = True
                            st.rerun(scope="fragment")
    
                        # --- 2段目：操作ボタン（3分割） ---
                        c1, c2, c3 = st.columns(3)
                        with c1:
                            if st.button("▲", key=f"u_{row_id}", disabled=(i==0), use_container_width=True):
                                action_idx, direction = i, -1
                        with c2:
                            if st.button("▼", key=f"d_{row_id}", disabled=(i==len(current_favs)-1), use_container_width=True):
                                action_idx, direction = i, 1
                        with c3:
                            if st.button("🗑️", key=f"x_{row_id}", use_container_width=True):
                                action_idx, direction = i, 99
    
            # --- ロジック実行 (変更なし) ---
            if action_idx is not None:
                if direction == 99:
                    st.session_state["pending_del_idx"] = action_idx
                else:
                    target_idx = action_idx + direction
                    current_favs[action_idx], current_favs[target_idx] = current_favs[target_idx], current_favs[action_idx]
                    st.session_state.user_locations = current_favs
                    if "save_settings_to_browser" in globals(): save_settings_to_browser()
                    st.rerun(scope="fragment")
    
            # 削除確認
            del_target = st.session_state.get("pending_del_idx")
            if del_target is not None:
                st.warning(f"「{current_favs[del_target]['name']}」を削除しますか？")
                y, n = st.columns(2)
                if y.button("削除", key="del_y", type="primary", use_container_width=True):
                    current_favs.pop(del_target)
                    st.session_state.user_locations = current_favs
                    st.session_state["pending_del_idx"] = None
                    if "save_settings_to_browser" in globals(): save_settings_to_browser()
                    st.rerun(scope="fragment")
                if n.button("中止", key="del_n", use_container_width=True):
                    st.session_state["pending_del_idx"] = None
                    st.rerun(scope="fragment")
    
        # --- 共通のフッター：地点の有無に関わらず表示 ---
        st.markdown("---")
        if st.button("編集を終了して閉じる", key="close_fav", type="secondary", use_container_width=True):
            st.rerun()
    
    internal_manager()

# ======================================================================================
# 93. 【main機能分離】②地図表示モジュール
# ======================================================================================
def render_map_module():
    if st.button("🗺️地図", use_container_width=True):
        show_location_map_dialog()
        
# ======================================================================================
# 94. 【main機能分離】④グラフ更新・設定モジュール
# ======================================================================================
def render_update_control_module(basho):
    """
    現在地ボタンと、グラフ更新・時刻情報表示ボタンを1行に並べて表示する。
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
    if st.button("🔄📍現在地　　　　　　　　　　", use_container_width=True):
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
    update_label = f"🔄📊更新 ({date_time_str})"
    
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
# 92. 【レイアウト修正版】操作コントロールパネル（機能・ロジック完全維持）
# ======================================================================================
def render_compact_control_panel(basho_name):
    """
    元のロジックを一切変更せず、スマホでの表示を「3行」に凝縮するレイアウト修正版。
    1行目：場所＋星、2行目：地図＋現在地、3行目：更新（日付時刻）
    """
    import streamlit as st
    from datetime import datetime, timedelta

    # --- レイアウト制御CSS (スマホ横並びと隙間削減のみに限定) ---
    st.markdown("""
        <style>
            [data-testid="column"] {
                flex-direction: row !important;
                flex-basis: auto !important;
                min-width: 0px !important;
                flex-grow: 1 !important;
            }
            [data-testid="stVerticalBlock"] > div {
                padding: 0px !important;
                margin-top: -2px !important;
            }
            [data-testid="stHorizontalBlock"] {
                gap: 5px !important;
            }
            .stButton > button {
                width: 100% !important;
                padding: 2px 5px !important;
                min-height: 35px !important;
            }
        </style>
    """, unsafe_allow_html=True)

    with st.container():
        # --- 1. 場所選択 ＋ お気に入り (元の92_2のロジックを完全維持) ---
        display_list, total_data = get_combined_location_list(
            CONFIG["LOCATION_MASTER"], 
            st.session_state.lat, 
            st.session_state.lon
        )
        favorites = st.session_state.get("user_locations", [])
        saved_data = next((f for f in favorites if abs(f['lat'] - st.session_state.lat) < 0.0001 and abs(f['lon'] - st.session_state.lon) < 0.0001), None)
        is_saved = saved_data is not None

        c1, c2 = st.columns([0.85, 0.15])
        with c1:
            selected_label = st.selectbox(
                "地点を選択してください", 
                options=display_list, 
                index=display_list.index(st.session_state.last_basho) if st.session_state.last_basho in display_list else 0,
                label_visibility="collapsed"
            )
        with c2:
            if is_saved:
                st.button("✅", key="fav_saved_icon", disabled=True, help="お気に入り登録済み")
            else:
                if st.button("⭐", key="fav_save_action", help="この場所をお気に入りに登録"):
                    pure_name = st.session_state.last_basho.split(" (")[0]
                    show_favorite_registration_dialog(pure_name, st.session_state.lat, st.session_state.lon)

        # --- 2. 地図 ＋ 現在地 (元の93と94_1のロジックを統合) ---
        c3, c4 = st.columns([0.5, 0.5])
        with c3:
            if st.button("🗺️地図", key="btn_map_open", use_container_width=True):
                show_location_map_dialog()
        with c4:
            # 🔄📍現在地 ボタン (元の94_1のボタン名称とロジックを維持)
            if st.button("🔄📍現在地", key="btn_get_gps", use_container_width=True):
                st.session_state.waiting_loc = True
                st.session_state.geo_key = f"geo_{datetime.now().timestamp()}"
                st.rerun()

        # --- 3. グラフ更新 (元の94_2のロジックを完全維持) ---
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
            now_local = now_jst.replace(tzinfo=None)

        date_time_str = now_local.strftime('%Y/%m/%d %H:%M:%S')
        update_label = f"🔄📊更新 ({date_time_str})"
        
        if st.button(update_label, key="btn_graph_refresh", use_container_width=True):
            st.cache_data.clear()
            st.session_state.needs_graph_update = True
            st.rerun()

    # --- 選択変更時のロジック処理 (元の92の後半部分) ---
    if selected_label == "地図で指定":
        show_location_map_dialog()
    elif selected_label != st.session_state.last_basho:
        new_lat, new_lon, new_name = total_data[selected_label]
        st.session_state.temp_lat, st.session_state.temp_lon, st.session_state.temp_basho = total_data[selected_label]
        update_state_and_save({
            "lat": new_lat, 
            "lon": new_lon, 
            "last_basho": selected_label,
            "needs_graph_update": True
        })

    # 現在地取得の待機処理 (元の94_1の後半部分)
    if st.session_state.get("waiting_loc"):
        handle_current_location_update_integrated()
        
# ======================================================================================
# 99. フッター情報表示 (凡例およびクレジット表記)
# ======================================================================================
def render_footer_info(danger_v):
    """
    グラフ下部に表示する凡例と、データソースのクレジット表記（Open-Meteo）を描画します。
    """
    st.markdown("---")
    
    # --- 1. 凡例の表示 ---
    # 以前のコードの意匠を継承し、ユーザーが設定した危険風速(danger_v)を動的に表示します
    st.markdown(
        f"""
        <div style="padding: 10px; border-radius: 5px; background-color: #f0f2f6; margin-bottom: 10px; line-height: 1.6;">
            <span style="font-weight: bold;">📊 凡例:</span><br>
            <span style="color: #1f77b4;">■</span> 3-5m/s (青) &nbsp;&nbsp; 
            <span style="color: #ff7f0e;">■</span> 5-10m/s (橙) &nbsp;&nbsp; 
            <span style="color: #d62728;">■</span> 10m/s以上 (赤) &nbsp;&nbsp; 
            <span style="color: #d62728; font-weight: bold;">---</span> <span style="font-size: 0.9em;">[赤点線: 危険風速ライン {danger_v}m/s]</span><br>
            <div style="margin-top: 4px; border-top: 1px solid #ddd; padding-top: 4px;">
                <small style="color: #666;">※青・橙は、詳細設定で選択した色付風向のみ表示</small>
            </div>
        </div>

        """,
        unsafe_allow_html=True
    )
    
    # --- 2. クレジット表記 (Open-Meteo) ---
    # 利用規約に基づき、リンクを含む適切な表記を行います
    st.caption("Weather data by [Open-Meteo.com](https://open-meteo.com/) (CC BY 4.0)")

# ======================================================================================
# 100. メイン処理 (再構築版・スクロール対応)
# ======================================================================================
def main():
    import os
    # --- 0. アプリ初期化 (最優先で実行) ---
    initialize_app()

    # --- 1. 状態の初期化 ---
    # 1. URLパラメータから開発者モードの状態を判定（SessionState内のみで保持）
    if "mode" in st.query_params and st.query_params["mode"] == "dev":
        st.session_state.is_dev_mode = True
    else:
        # パラメータがない場合は、LocalStorageの状態に関わらずFalseにする（永続化しない場合）
        st.session_state.is_dev_mode = False
    
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
    
    # --- タイトルエリアの修正 (画像ロゴのみを表示) ---
    import os
    icon_path = "pin_weather_01.png"
    if os.path.exists(icon_path):
        st.image(icon_path, HIGHT=100) 
    else:
        st.title("⛵Pin_Weather!")            
       
    # 時間設定
    now_jst = datetime.now(timezone(timedelta(hours=9)))

    # --- 2. 各モジュールの描画 ---
    # 以前の 92, 93, 94 をすべて1つに集約
    render_compact_control_panel(st.session_state.last_basho)

    # グラフエリア（ここでフラグを見て描画を行う）
    render_graph_area_module(danger_v, sel_dirs, design_params, now_jst)
    
    # 今回追加：凡例とクレジット表記
    render_footer_info(danger_v)
    
    if st.session_state.get("is_dev_mode"):
        st.divider()
        st.write("Debug: Session State", st.session_state)

if __name__ == "__main__":
    main()

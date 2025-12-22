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

# --- 定数設定：マジックナンバーを避け、一括でデザインを管理 ---
CONFIG = {
    "TITLE_SIZE": 22,
    "SUBTITLE_SIZE": 16,
    "GRAPH_FONT_SIZE": 12,
    "LABEL_SIZE": 12,
    "DPI": 300,
    "MAP_HEIGHT": 350
}

# 風向の定義（360度を16方位で割るための基準）
ALL_DIRECTIONS = ["北", "北北東", "北東", "東北東", "東", "東南東", "南東", "南南東", "南", "南南西", "南西", "西南西", "西", "西北西", "北西", "北北西"]

# ======================================================================================
# フォント設定：クラウド環境（Streamlit Cloud等）でも日本語を正しく表示させるための処理
# ======================================================================================
def setup_font():
    font_url = "https://github.com/google/fonts/raw/main/ofl/notosansjp/NotoSansJP%5Bwght%5D.ttf"
    font_path = "NotoSansJP.ttf"
    # サーバー内にフォントがなければダウンロード
    if not os.path.exists(font_path):
        urllib.request.urlretrieve(font_url, font_path)
    # Matplotlibのフォントマネージャーに登録し、デフォルトに設定
    fm.fontManager.addfont(font_path)
    plt.rc('font', family='Noto Sans JP', size=CONFIG["GRAPH_FONT_SIZE"])

# ======================================================================================
# 気象データの取得：Open-Meteo APIを利用して1時間ごとのデータを取得
# ======================================================================================
def fetch_weather_data(lat, lon, days):
    # 気温、風速(m/s)、風向、天気を取得するURLを構築
    url = f"https://api.open-meteo.com/v1/forecast?latitude={lat}&longitude={lon}&hourly=temperature_2m,wind_speed_10m,wind_direction_10m,weather_code&timezone=Asia%2FTokyo&wind_speed_unit=ms&forecast_days={days}"
    try:
        data = requests.get(url).json()
        df = pd.DataFrame(data["hourly"])
        df['time'] = pd.to_datetime(df['time'])
        
        # グラフの左端が切れないよう、直前3時間分の空行を追加（パディング処理）
        first_time = df['time'].iloc[0]
        padding = pd.DataFrame({
            'time': [first_time - timedelta(hours=i) for i in range(3, 0, -1)],
            'temperature_2m': [None]*3, 'wind_speed_10m': [None]*3, 'wind_direction_10m': [None]*3, 'weather_code': [None]*3
        })
        return pd.concat([padding, df], ignore_index=True)
    except Exception:
        return None

# ======================================================================================
# 潮汐データの推算：基準日からの時間経過に基づき余弦波で擬似的に計算
# ======================================================================================
def get_tide_level(times):
    base_full_tide = datetime(2025, 1, 1, 6, 0) # 基準となる満潮時刻
    cycle_hours = 12.42 # 大まかな潮汐周期（M2分潮）
    levels = []
    for t in times:
        if pd.isna(t): 
            levels.append(None)
            continue
        # 基準時刻からの経過時間を計算
        hours_from_base = (t - base_full_tide).total_seconds() / 3600
        # コサイン関数により-100〜100の範囲で潮位をシミュレート
        level = 100 * np.cos(2 * np.pi * hours_from_base / cycle_hours)
        levels.append(level)
    return levels

# ======================================================================================
# データ加工：数値データをテキスト（風向き名、矢印、色）に変換
# ======================================================================================
def get_weather_info(code):
    """WMO天候コードを日本語名と色に変換"""
    if code is None: return "", "black"
    if code <= 2: return "晴", "#FF8C00"
    if code <= 48: return "曇", "#696969"
    if code <= 99: return "雨", "#0000FF"
    return "？", "black"

def process_wind_data(df, target_dirs, danger_v):
    """風向角度(0-360)を16方位に変換し、条件に応じた色を割り当てる"""
    dirs = ALL_DIRECTIONS + ["北"]
    arrows = ["↓", "↙", "↙", "↙", "←", "↖", "↖", "↖", "↑", "↗", "↗", "↗", "→", "↘", "↘", "↘", "↓"]

    def get_info(deg):
        if pd.isna(deg): return "", ""
        # 角度を22.5度ずつの範囲に割り振る計算
        idx = int((deg + 11.25) / 22.5) % 16
        return dirs[idx], arrows[idx]

    # 風向き名と矢印アイコンの生成
    df['res'] = df['wind_direction_10m'].apply(get_info)
    df['dir_name'] = df['res'].apply(lambda x: x[0])
    df['arrow'] = df['res'].apply(lambda x: x[1])

    # 天気テキストと色の生成
    weather_res = df['weather_code'].apply(get_weather_info)
    df['w_text'] = [r[0] for r in weather_res]
    df['w_color'] = [r[1] for r in weather_res]

    def judge(row):
        """風速と風向から、グラフの棒の色を決定する重要ロジック"""
        speed = row['wind_speed_10m']
        if pd.isna(speed): return "none"
        if speed >= danger_v: return "crimson" # 危険域
        if row['dir_name'] in target_dirs:      # 指定した風向の場合
            if 6 <= speed < danger_v: return "orange"
            if 3 <= speed < 6: return "skyblue"
        return "#D3D3D3" # 条件外はグレー

    df['color'] = df.apply(judge, axis=1)
    df['tide_level'] = get_tide_level(df['time'])
    return df

# ======================================================================================
# グラフ生成：Matplotlibを用いて多段グラフを作成し、Base64形式で出力
# ======================================================================================
@st.cache_data(show_spinner=False) # データの再計算を避けるためのキャッシュ
def get_cached_graph(lat, lon, days, danger_v, selected_dirs_tuple):
    df = fetch_weather_data(lat, lon, days)
    if df is None: return None
    df = process_wind_data(df, list(selected_dirs_tuple), danger_v)

    # 日数に応じてラベルの表示間隔を調整（見やすさのため）
    wind_step = (1 if days <= 1 else (2 if days <= 3 else 3))
    time_step = (3 if days <= 2 else 6)
    
    # グラフの描画領域作成（3段：風速、気温、潮位）
    fig_w = max(10, days * 4.5)
    fig, (ax1, ax2, ax3) = plt.subplots(3, 1, figsize=(fig_w, 10), dpi=CONFIG["DPI"], gridspec_kw={'height_ratios': [4.2, 1.2, 1.0})
    plt.subplots_adjust(hspace=0.6)

    # 日本語の曜日フォーマッター
    jp_weeks = ["月", "火", "水", "木", "金", "土", "日"]
    def formatter(x, p):
        dt = mdates.num2date(x)
        if dt.hour == 0: # 0時の時だけ日付と曜日を表示
            return dt.strftime('%m/%d') + f'\n({jp_weeks[dt.weekday()]})\n' + dt.strftime('%H:%M')
        else:
            return dt.strftime('%H:%M')
    
    # --- 上段：風速棒グラフ ---
    bars = ax1.bar(df['time'], df['wind_speed_10m'], color=df['color'], alpha=0.9, width=0.03)
    ax1.axhline(y=danger_v, color='red', linestyle='--', alpha=0.6) # 危険線
    ax1.set_ylabel('風速 (m/s)')
    # y軸の表示範囲の「高さ」を取得して、テキスト間隔の基準にする
    y_max = max(df['wind_speed_10m'].max() if not df['wind_speed_10m'].empty else 0, danger_v) + 5
    ax1.set_ylim(0, y_max)
    offset = y_max * 0.12  # y軸全高の約12%を天気テキストの間隔にする
    
    # --- 共通設定（現在時刻の線、X軸のメモリ設定） ---
    jst = timezone(timedelta(hours=9))
    now_jst = datetime.now(jst).replace(tzinfo=None)
    for ax in [ax1, ax2, ax3]:
        ax.axvline(now_jst, color='blue', linestyle='-', alpha=0.6, linewidth=2.5) # 現在時刻線
        ax.xaxis.set_major_locator(mdates.HourLocator(byhour=range(0, 24, time_step)))
        ax.xaxis.set_major_formatter(plt.FuncFormatter(formatter))
        ax.set_xlim(df['time'].iloc[0], df['time'].iloc[-1])
        ax.grid(True, linestyle=':', alpha=0.4, color='#000000')

    # --- 中段：気温折れ線 ---
    ax2.plot(df['time'], df['temperature_2m'], color='black', linewidth=1.5)
    ax2.set_ylabel('気温(℃)')

    # --- 下段：潮位曲線 ---
    ax3.plot(df['time'], df['tide_level'], color='royalblue', linewidth=2)
    ax3.fill_between(df['time'], df['tide_level'], -120, color='royalblue', alpha=0.2) # 塗りつぶし
    ax3.set_ylabel('潮位'); ax3.set_yticks([]) # 潮位の数値自体は重要でないため消去

    # 棒グラフの上に風向・天気・風速のテキストを配置
    for i, bar in enumerate(bars):
        if not pd.isna(df['wind_speed_10m'].iloc[i]) and i % wind_step == 0:
            h = bar.get_height()
            # 天気（晴、曇、雨）
            ax1.text(bar.get_x() + bar.get_width()/2., h + offset, df['w_text'].iloc[i], ha='center', va='bottom', color=df['w_color'].iloc[i], fontweight='bold', fontsize=CONFIG["GRAPH_FONT_SIZE"])
            # 風向名、矢印、風速数値
            txt = f"{df['dir_name'].iloc[i]}\n{df['arrow'].iloc[i]}\n{round(df['wind_speed_10m'].iloc[i])}m"
            ax1.text(bar.get_x() + bar.get_width()/2., h + (y_max * 0.02) , txt, ha='center', va='bottom', fontweight='bold', color='black', fontsize=CONFIG["GRAPH_FONT_SIZE"])

    # メモリ上の画像として保存し、HTML表示用にBase64変換
    buf = io.BytesIO(); fig.savefig(buf, format="png", bbox_inches='tight', pad_inches=0.1)
    return base64.b64encode(buf.getvalue()).decode()

# ======================================================================================
# 地図UI：Foliumを使い、中心座標を取得するための複雑なレイアウトを構築
# ======================================================================================
def show_location_map():
    st.info("地図の中央地点のグラフを描画表示することができます。")
    # CSSで地図の周りに配置する矢印をデザイン
    st.markdown("""<style>...</style>""", unsafe_allow_html=True)

    # 現在選択されている座標にマーカーを置いた地図を作成
    m = folium.Map(location=[st.session_state.lat, st.session_state.lon], zoom_start=13)
    folium.Marker([st.session_state.lat, st.session_state.lon], icon=folium.Icon(color='red')).add_to(m)

    # 3x3のグリッドを作成し、中央[1,1]に地図、その上下左右にガイド矢印を配置
    col_l1, col_m1, col_r1 = st.columns([1, 18, 1])
    # （中略：矢印の配置処理）
    col_l2, col_m2, col_r2 = st.columns([1, 18, 1])
    with col_m2:
        # 地図の描画と、ユーザーが動かした後の「中心座標」の取得
        map_out = st_folium(m, width=None, height=CONFIG["MAP_HEIGHT"], key=f"map_{st.session_state.lat}", returned_objects=["center"])

    # 確定ボタンが押されたら、地図の中心座標をセッションに保存してリロード
    if map_out and map_out.get("center"):
        if st.button("グラフ描画地点確定", use_container_width=True):
            st.session_state.lat, st.session_state.lon = map_out["center"]["lat"], map_out["center"]["lng"]
            st.session_state.last_basho = "地図で指定"
            st.rerun()

# ======================================================================================
# メイン：アプリ全体の制御、状態管理
# ======================================================================================
def main():
    setup_font()
    st.markdown(f'<h1 ...>⛵ 高須風チェッカー</h1>', unsafe_allow_html=True)
    
    # --- 初期状態のセットアップ（クエリパラメータやセッションから値を復元） ---
    params = st.query_params
    init_lat, init_lon = float(params.get("lat", 31.337)), float(params.get("lon", 130.795))
    if 'lat' not in st.session_state: st.session_state.lat = init_lat
    if 'lon' not in st.session_state: st.session_state.lon = init_lon
    if 'last_basho' not in st.session_state: st.session_state.last_basho = "高須沖(鹿児島県)"

    # --- UI上部：地点選択 ---
    basho_list = ["高須沖(鹿児島県)", "柏原沖(鹿児島県)", ...]
    col_sel, col_map_check = st.columns([7, 3])
    with col_sel:
        basho = st.selectbox("地点を選択", basho_list, index=..., label_visibility="collapsed")
    with col_map_check:
        show_map = st.checkbox("地図表示", value=st.session_state.get('show_map_state', False))
        st.session_state.show_map_state = show_map

    # 地点（コンボボックス）が変更されたら座標を更新
    if st.session_state.last_basho != basho:
        coords = {"高須沖(鹿児島県)":(31.337, 130.795), ...}
        if basho in coords:
            st.session_state.lat, st.session_state.lon = coords[basho]
            st.session_state.last_basho = basho
            st.rerun()

    if show_map: show_location_map()
    
    # --- サイドバー：表示日数や風向きのフィルタリング設定 ---
    st.sidebar.header("表示設定")
    days = st.sidebar.slider("表示日数", 1, 8, int(params.get("days", 8)))
    danger_v = st.sidebar.number_input("危険風速(m/s)", value=float(params.get("danger", 10.0)))
    
    # 風向きチェックボックスの生成（2列に並べる）
    selected_target_dirs = []
    cols = st.sidebar.columns(2)
    for i, d in enumerate(ALL_DIRECTIONS):
        with cols[i % 2]:
            if st.checkbox(d, value=(d in init_dirs), key=f"chk_{d}"):
                selected_target_dirs.append(d)

    # 現在の設定をURLに反映（ブックマーク可能にするため）
    st.query_params.update({"lat": st.session_state.lat, ...})

    # グラフの生成と表示
    img_base64 = get_cached_graph(st.session_state.lat, st.session_state.lon, days, danger_v, tuple(selected_target_dirs))

    if img_base64:
        # 凡例表示（折り畳み式）
        with st.expander("📊 凡例・保存方法"):
            st.markdown(...)
        # グラフ本体（横スクロール可能にするためのdiv）
        st.markdown(f'<div style="overflow-x: auto; ..."><img src="data:image/png;base64,{img_base64}" ...></div>', unsafe_allow_html=True)

if __name__ == "__main__":
    main()

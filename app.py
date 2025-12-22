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

# --- デザイン管理辞書：数値を一箇所にまとめることで保守性を向上 ---
CONFIG = {
    "TITLE_SIZE": 22,
    "SUBTITLE_SIZE": 16,
    "GRAPH_FONT_SIZE": 12,
    "LABEL_SIZE": 12,
    "DPI": 300,        # 印刷品質の解像度。ボケ防止に重要
    "MAP_HEIGHT": 350  # 地図の表示高さ
}

# 16方位の定義。計算（(deg+11.25)/22.5）と配列の添字が一致するように設計
ALL_DIRECTIONS = ["北", "北北東", "北東", "東北東", "東", "東南東", "南東", "南南東", "南", "南南西", "南西", "西南西", "西", "西北西", "北西", "北北西"]

# ======================================================================================
# フォント設定：日本語文字化けを防ぐための標準的アプローチ
# ======================================================================================
def setup_font():
    font_url = "https://github.com/google/fonts/raw/main/ofl/notosansjp/NotoSansJP%5Bwght%5D.ttf"
    font_path = "NotoSansJP.ttf"
    if not os.path.exists(font_path):
        urllib.request.urlretrieve(font_url, font_path)
    fm.fontManager.addfont(font_path)
    # アプリ全体のグラフフォントを統一設定
    plt.rc('font', family='Noto Sans JP', size=CONFIG["GRAPH_FONT_SIZE"])

# ======================================================================================
# 気象データ取得：外部APIとの通信
# ======================================================================================
def fetch_weather_data(lat, lon, days):
    url = f"https://api.open-meteo.com/v1/forecast?latitude={lat}&longitude={lon}&hourly=temperature_2m,wind_speed_10m,wind_direction_10m,weather_code&timezone=Asia%2FTokyo&wind_speed_unit=ms&forecast_days={days}"
    try:
        data = requests.get(url).json()
        df = pd.DataFrame(data["hourly"])
        df['time'] = pd.to_datetime(df['time'])
        
        # 【重要】パディング処理。グラフの開始点に「現在時刻の線」が重なりすぎないよう左側に余白を作る
        first_time = df['time'].iloc[0]
        padding = pd.DataFrame({
            'time': [first_time - timedelta(hours=i) for i in range(3, 0, -1)],
            'temperature_2m': [None]*3, 'wind_speed_10m': [None]*3, 'wind_direction_10m': [None]*3, 'weather_code': [None]*3
        })
        return pd.concat([padding, df], ignore_index=True)
    except Exception:
        return None

# ======================================================================================
# 潮汐データ推算：天文学的な計算を簡易的な正弦波モデルで代用
# ======================================================================================
def get_tide_level(times):
    base_full_tide = datetime(2025, 1, 1, 6, 0)
    cycle_hours = 12.42 # 月の南中周期に基づく平均的な潮汐の間隔
    levels = []
    for t in times:
        if pd.isna(t): 
            levels.append(None)
            continue
        # 基準点からの経過時間を周期で割り、余弦関数で潮位の変化を生成
        hours_from_base = (t - base_full_tide).total_seconds() / 3600
        level = 100 * np.cos(2 * np.pi * hours_from_base / cycle_hours)
        levels.append(level)
    return levels

# ======================================================================================
# データ加工：人間が読みやすい形式にコンバート
# ======================================================================================
def get_weather_info(code):
    """天候コードを直感的な色と名前にマッピング"""
    if code is None: return "", "black"
    if code <= 2: return "晴", "#FF8C00"
    if code <= 48: return "曇", "#696969"
    if code <= 99: return "雨", "#0000FF"
    return "？", "black"

def process_wind_data(df, target_dirs, danger_v):
    """方位角を方位名に変換し、ユーザー設定に基づく強調色を決定"""
    dirs = ALL_DIRECTIONS + ["北"]
    arrows = ["↓", "↙", "↙", "↙", "←", "↖", "↖", "↖", "↑", "↗", "↗", "↗", "→", "↘", "↘", "↘", "↓"]

    def get_info(deg):
        if pd.isna(deg): return "", ""
        # 数学的に角度を16方位のINDEXに落とし込む処理
        idx = int((deg + 11.25) / 22.5) % 16
        return dirs[idx], arrows[idx]

    df['res'] = df['wind_direction_10m'].apply(get_info)
    df['dir_name'] = df['res'].apply(lambda x: x[0])
    df['arrow'] = df['res'].apply(lambda x: x[1])

    weather_res = df['weather_code'].apply(get_weather_info)
    df['w_text'] = [r[0] for r in weather_res]
    df['w_color'] = [r[1] for r in weather_res]

    def judge(row):
        """風速と向きに基づきグラフの色を判定（ビジネスロジックの中核）"""
        speed = row['wind_speed_10m']
        if pd.isna(speed): return "none"
        if speed >= danger_v: return "crimson"
        if row['dir_name'] in target_dirs:
            if 6 <= speed < danger_v: return "orange"
            if 3 <= speed < 6: return "skyblue"
        return "#D3D3D3"

    df['color'] = df.apply(judge, axis=1)
    df['tide_level'] = get_tide_level(df['time'])
    return df

# ======================================================================================
# グラフ生成：Matplotlibによる高度な可視化
# ======================================================================================
@st.cache_data(show_spinner=False) # 同じパラメータなら再計算せずキャッシュを返す（高速化）
def get_cached_graph(lat, lon, days, danger_v, selected_dirs_tuple):
    df = fetch_weather_data(lat, lon, days)
    if df is None: return None
    df = process_wind_data(df, list(selected_dirs_tuple), danger_v)

    # 情報密度に合わせて間引き率を決定（表示日数が長い時に文字が重なるのを防ぐ）
    wind_step = (1 if days <= 1 else (2 if days <= 3 else 3))
    time_step = (3 if days <= 2 else 6)
    
    fig_w = max(10, days * 4.5)
    # 三段グラフ。height_ratiosでそれぞれのグラフの高さの比重を指定
    fig, (ax1, ax2, ax3) = plt.subplots(3, 1, figsize=(fig_w, 10), dpi=CONFIG["DPI"], gridspec_kw={'height_ratios': [4.2, 1.2, 1.0]})
    plt.subplots_adjust(hspace=0.6) # グラフ間の垂直余白

    # X軸の時刻表記設定
    jp_weeks = ["月", "火", "水", "木", "金", "土", "日"]
    def formatter(x, p):
        dt = mdates.num2date(x)
        if dt.hour == 0:
            return dt.strftime('%m/%d') + f'\n({jp_weeks[dt.weekday()]})\n' + dt.strftime('%H:%M')
        else:
            return dt.strftime('%H:%M')
    
    # 風速バーチャート
    bars = ax1.bar(df['time'], df['wind_speed_10m'], color=df['color'], alpha=0.9, width=0.03)
    ax1.axhline(y=danger_v, color='red', linestyle='--', alpha=0.6)
    ax1.set_ylabel('風速 (m/s)')
    
    # 【最重要】y軸のスケールに応じたテキストの動的オフセット計算
    # PC/スマホでアスペクト比が変わっても、文字同士の間隔が一定に保たれる
    max_val = df['wind_speed_10m'].max() if not df['wind_speed_10m'].empty else 0
    y_limit = max(max_val, danger_v) + 5
    ax1.set_ylim(0, y_limit)
    text_offset_weather = y_limit * 0.12  # y軸の12%分上に天気を置く
    text_offset_wind = y_limit * 0.02     # y軸の2%分上に風向を置く

    # 日本標準時（JST）の取得と現在時刻線の描画
    jst = timezone(timedelta(hours=9))
    now_jst = datetime.now(jst).replace(tzinfo=None)
    for ax in [ax1, ax2, ax3]:
        ax.axvline(now_jst, color='blue', linestyle='-', alpha=0.6, linewidth=2.5)
        ax.xaxis.set_major_locator(mdates.HourLocator(byhour=range(0, 24, time_step)))
        ax.xaxis.set_major_formatter(plt.FuncFormatter(formatter))
        ax.set_xlim(df['time'].iloc[0], df['time'].iloc[-1])
        ax.grid(True, linestyle=':', alpha=0.4, color='#000000')

    # 気温グラフ
    ax2.plot(df['time'], df['temperature_2m'], color='black', linewidth=1.5)
    ax2.set_ylabel('気温(℃)')

    # 潮位グラフ（塗りつぶし付き）
    ax3.plot(df['time'], df['tide_level'], color='royalblue', linewidth=2)
    ax3.fill_between(df['time'], df['tide_level'], -120, color='royalblue', alpha=0.2)
    ax3.set_ylabel('潮位'); ax3.set_yticks([])

    # 棒グラフの上にメタ情報（天気・風向）を描画
    for i, bar in enumerate(bars):
        if not pd.isna(df['wind_speed_10m'].iloc[i]) and i % wind_step == 0:
            h = bar.get_height()
            # 天気（動的オフセット計算を適用）
            ax1.text(bar.get_x() + bar.get_width()/2., h + text_offset_weather, df['w_text'].iloc[i], ha='center', va='bottom', color=df['w_color'].iloc[i], fontweight='bold', fontsize=CONFIG["GRAPH_FONT_SIZE"])
            # 風向名・矢印（動的オフセット計算を適用）
            txt = f"{df['dir_name'].iloc[i]}\n{df['arrow'].iloc[i]}\n{round(df['wind_speed_10m'].iloc[i])}m"
            ax1.text(bar.get_x() + bar.get_width()/2., h + text_offset_wind, txt, ha='center', va='bottom', fontweight='bold', color='black', fontsize=CONFIG["GRAPH_FONT_SIZE"])

    # バイナリデータとして画像を保存しBase64化。HTML経由で表示するため
    buf = io.BytesIO(); fig.savefig(buf, format="png", bbox_inches='tight', pad_inches=0.1)
    return base64.b64encode(buf.getvalue()).decode()

# ======================================================================================
# 地図UI：ユーザー体験向上のためのこだわり
# ======================================================================================
def show_location_map():
    st.info("地図の中央地点のグラフを描画表示することができます。")
    # CSSで地図の中心を強調するための装飾
    st.markdown("""
        <style>
        div[data-testid="stHorizontalBlock"] { flex-wrap: nowrap !important; justify-content: center !important; }
        [data-testid="column"] { min-width: 0px !important; }
        .guide-arrow-main { color: crimson; font-size: 24px; font-weight: bold; text-align: center; }
        </style>
    """, unsafe_allow_html=True)

    # 現在のセッション状態の座標で地図を作成
    m = folium.Map(location=[st.session_state.lat, st.session_state.lon], zoom_start=13)
    folium.Marker([st.session_state.lat, st.session_state.lon], icon=folium.Icon(color='red')).add_to(m)

    # 地図を囲む「▼▶◀▲」ガイド表示
    col_l1, col_m1, col_r1 = st.columns([1, 18, 1])
    with col_m1: st.markdown("<div class='guide-arrow-main'>▼</div>", unsafe_allow_html=True)

    col_l2, col_m2, col_r2 = st.columns([1, 18, 1])
    with col_l2: st.markdown(f"<div style='line-height:{CONFIG['MAP_HEIGHT']}px; text-align:right;' class='guide-arrow-main'>▶</div>", unsafe_allow_html=True)
    # st_foliumにより地図の操作（移動）後の中心座標を取得可能にする
    with col_m2: map_out = st_folium(m, width=None, height=CONFIG["MAP_HEIGHT"], key=f"map_{st.session_state.lat}", returned_objects=["center"])
    with col_r2: st.markdown(f"<div style='line-height:{CONFIG['MAP_HEIGHT']}px; text-align:left;' class='guide-arrow-main'>◀</div>", unsafe_allow_html=True)
        
    col_l3, col_m3, col_r3 = st.columns([1, 18, 1])
    with col_m3: st.markdown("<div class='guide-arrow-main'>▲</div>", unsafe_allow_html=True)

    if map_out and map_out.get("center"):
        if st.button("グラフ描画地点確定", use_container_width=True):
            # 地図で選んだ新しい座標をセッションに上書き保存し、ページをリロード（再描画）
            st.session_state.lat, st.session_state.lon = map_out["center"]["lat"], map_out["center"]["lng"]
            st.session_state.last_basho = "地図で指定"
            st.rerun()

# ======================================================================================
# メインアプリケーション：全体のオーケストレーション
# ======================================================================================
def main():
    setup_font()
    st.markdown(f'<h1 style="font-size:{CONFIG["TITLE_SIZE"]}px; margin-bottom: 5px;">⛵ 高須風チェッカー</h1>', unsafe_allow_html=True)
    
    # URLパラメータの取得（初期表示用）
    params = st.query_params
    init_lat = float(params.get("lat", 31.337))
    init_lon = float(params.get("lon", 130.795))
    
    # 【設計】セッションステートの初期化（未定義の場合のみ実行）
    if 'lat' not in st.session_state: st.session_state.lat = init_lat
    if 'lon' not in st.session_state: st.session_state.lon = init_lon
    if 'last_basho' not in st.session_state: st.session_state.last_basho = "高須沖(鹿児島県)"

    basho_list = ["高須沖(鹿児島県)", "柏原沖(鹿児島県)", "垂水港(鹿児島県)", "海潟(鹿児島県)", "磯海岸沖(鹿児島県)", "江口浜沖(鹿児島県)", "錦江湾(鹿児島県)", "地図で指定"]
    
    # 【工夫】前回の選択をセレクトボックスに引き継ぐ
    try:
        current_idx = basho_list.index(st.session_state.last_basho)
    except ValueError:
        current_idx = 0

    col_sel, col_map_check = st.columns([7, 3])
    with col_sel:
        basho = st.selectbox("地点を選択", basho_list, index=current_idx, label_visibility="collapsed")
    with col_map_check:
        show_map = st.checkbox("地図表示", value=st.session_state.get('show_map_state', False))
        st.session_state.show_map_state = show_map

    st.markdown(f"<p style='font-size:12px; color:#666; margin-top:-10px;'>グラフ描画地点： 緯度 {st.session_state.lat:.4f} / 経度 {st.session_state.lon:.4f}</p>", unsafe_allow_html=True)

    # 地点が変更された瞬間に座標をセットし、rerun()で即座に反映させる
    if st.session_state.last_basho != basho:
        coords = {
            "高須沖(鹿児島県)":(31.337, 130.795), "柏原沖(鹿児島県)":(31.380, 131.020), 
            "垂水港(鹿児島県)":(31.478, 130.668), "海潟(鹿児島県)":(31.539, 130.706), 
            "磯海岸沖(鹿児島県)":(31.614, 130.577), "江口浜沖(鹿児島県)":(31.643, 130.322), 
            "錦江湾(鹿児島県)":(31.590, 130.600)
        }
        if basho in coords:
            st.session_state.lat, st.session_state.lon = coords[basho]
            st.session_state.last_basho = basho
            st.rerun()
        elif basho == "地図で指定":
            st.session_state.last_basho = basho

    if show_map: show_location_map()
    
    # サイドバー設定：インタラクティブなフィルタリング
    st.sidebar.header("表示設定")
    days = st.sidebar.slider("表示日数", 1, 8, int(params.get("days", 8)))
    danger_v = st.sidebar.number_input("危険風速(m/s)", value=float(params.get("danger", 10.0)))
    
    st.sidebar.markdown("---")
    st.sidebar.header("乗れる風向")
    
    # ターゲット風向のチェックボックスリスト（初期値はURLパラメータから復元）
    init_dirs = params.get("dirs", "南,南南西,南西,西南西,西,西北西,北西,北北西").split(",")
    selected_target_dirs = []
    cols = st.sidebar.columns(2)
    for i, d in enumerate(ALL_DIRECTIONS):
        with cols[i % 2]:
            if st.checkbox(d, value=(d in init_dirs), key=f"chk_{d}"):
                selected_target_dirs.append(d)

    # URLクエリパラメータを更新（現在のページURLをコピーして他人に共有可能にする）
    st.query_params.update({
        "lat": st.session_state.lat, "lon": st.session_state.lon, 
        "days": days, "danger": danger_v, "dirs": ",".join(selected_target_dirs)
    })

    # グラフ描画実行
    img_base64 = get_cached_graph(st.session_state.lat, st.session_state.lon, days, danger_v, tuple(selected_target_dirs))

    if img_base64:
        with st.expander("📊 凡例・保存方法"):
            st.markdown(f'<p style="font-size:14px;"><span style="color:skyblue;">■</span> 3-6m/s <span style="color:orange;">■</span> 6-10m/s <span style="color:crimson;">■</span> {danger_v}m/s以上</p>', unsafe_allow_html=True)
        # HTML/CSSを使用して、横スクロール可能なコンテナに高解像度画像を埋め込む
        st.markdown(f'<div style="overflow-x: auto; background: white; border-radius: 8px; border: 1px solid #eee; margin-top: 5px;"><img src="data:image/png;base64,{img_base64}" style="height: 780px; max-width: none;"></div>', unsafe_allow_html=True)

if __name__ == "__main__":
    main()

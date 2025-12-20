import streamlit as st
import requests
import pandas as pd
import matplotlib.pyplot as plt
import matplotlib.font_manager as fm
import urllib.request
import os
import io
import base64
import warnings
from datetime import datetime, timedelta, timezone
import matplotlib.dates as mdates
from streamlit_folium import st_folium
import folium

#=================================================================================================
# --- 設定 ---
#=================================================================================================
CONFIG = {
    "TITLE_SIZE": 20,
    "SUBTITLE_SIZE": 16,
    "GRAPH_FONT_SIZE": 9,
    "LABEL_SIZE": 11,
    "DPI": 300,
    "MAP_WIDTH": 700,
    "MAP_HEIGHT": 400
}

#=================================================================================================
def setup_font():
#=================================================================================================
    font_url = "https://github.com/google/fonts/raw/main/ofl/notosansjp/NotoSansJP%5Bwght%5D.ttf"
    font_path = "NotoSansJP.ttf"
    if not os.path.exists(font_path):
        urllib.request.urlretrieve(font_url, font_path)
    fm.fontManager.addfont(font_path)
    plt.rc('font', family='Noto Sans JP', size=CONFIG["GRAPH_FONT_SIZE"])

#=================================================================================================
def fetch_weather_data(lat, lon, days):
#=================================================================================================
    url = f"https://api.open-meteo.com/v1/forecast?latitude={lat}&longitude={lon}&hourly=temperature_2m,wind_speed_10m,wind_direction_10m&timezone=Asia%2FTokyo&wind_speed_unit=ms&forecast_days=8"
    try:
        data = requests.get(url).json()
        df = pd.DataFrame(data["hourly"])
        df['time'] = pd.to_datetime(df['time'])
        return df.head(24 * days).reset_index(drop=True)
    except Exception as e:
        st.error(f"データ取得エラー: {e}")
        return None

#=================================================================================================
def process_wind_data(df, lat, lon, danger_v):
#=================================================================================================
    dirs = ["北", "北北東", "北東", "東北東", "東", "東南東", "南東", "南南東", "南", "南南西", "南西", "西南西", "西", "西北西", "北西", "北北西", "北"]
    arrows = ["↓", "↙", "↙", "↙", "←", "↖", "↖", "↖", "↑", "↗", "↗", "↗", "→", "↘", "↘", "↘", "↓"]
    def get_info(deg):
        idx = int((deg + 11.25) / 22.5) % 16
        return dirs[idx], arrows[idx]
    df['res'] = df['wind_direction_10m'].apply(get_info)
    df['dir_name'] = df['res'].apply(lambda x: x[0])
    df['arrow'] = df['res'].apply(lambda x: x[1])
    def judge(row):
        speed, direction = row['wind_speed_10m'], row['dir_name']
        if speed > danger_v: return "crimson", "⚠️"
        is_takasu = (31.0 <= lat <= 31.5 and 130.5 <= lon <= 131.0)
        if is_takasu and 5 <= speed <= 10 and direction == "北西": return "gold", "★"
        if 5 <= speed <= 10 and direction in ["西", "南西"]: return "orange", "○"
        if 5 <= speed <= 10: return "skyblue", ""
        return "lightgray", ""
    res_all = df.apply(judge, axis=1)
    df['color'] = [r[0] for r in res_all]
    df['mark'] = [r[1] for r in res_all]
    return df

#=================================================================================================
def create_graph(df, days, danger_v, wind_step, time_step):
#=================================================================================================
    fig_w = max(10, days * 3.5)
    fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(fig_w, 8), dpi=CONFIG["DPI"], 
                                   gridspec_kw={'height_ratios': [4, 1]})
    plt.subplots_adjust(hspace=0.8)

    jp_weeks = ["月", "火", "水", "木", "金", "土", "日"]
    def formatter(x, p):
        dt = mdates.num2date(x)
        return dt.strftime('%m/%d') + f'\n({jp_weeks[dt.weekday()]})\n' + dt.strftime('%H:%M')

    bars = ax1.bar(df['time'], df['wind_speed_10m'], color=df['color'], alpha=0.8, width=0.03)
    ax1.axhline(y=danger_v, color='red', linestyle='--', alpha=0.4)
    ax1.set_ylabel('風速 (m/s)', fontsize=CONFIG["LABEL_SIZE"])
    ax1.set_ylim(0, max(df['wind_speed_10m'].max(), danger_v) + 7)
    
    jst = timezone(timedelta(hours=9))
    now_jst = datetime.now(jst).replace(tzinfo=None)
    ax1.axvline(now_jst, color='blue', linestyle='-', alpha=0.5, linewidth=2.5)

    for ax in [ax1, ax2]:
        ax.xaxis.set_major_locator(mdates.HourLocator(interval=time_step))
        ax.xaxis.set_major_formatter(plt.FuncFormatter(formatter))
        ax.set_xlim(df['time'].iloc[0], df['time'].iloc[-1])
        ax.grid(True, linestyle=':', alpha=0.5)
        plt.setp(ax.get_xticklabels(), ha='center')

    for i, bar in enumerate(bars):
        if i % wind_step == 0:
            h = bar.get_height()
            v = round(df['wind_speed_10m'].iloc[i])
            txt = f"{df['mark'].iloc[i]}\n{df['dir_name'].iloc[i]}\n{df['arrow'].iloc[i]}\n{v}m"
            ax1.text(bar.get_x() + bar.get_width()/2., h + 0.3, txt, ha='center', va='bottom', fontweight='bold')

    ax2.plot(df['time'], df['temperature_2m'], color='#666666', linewidth=1.5)
    ax2.set_ylabel('気温 (℃)', fontsize=CONFIG["LABEL_SIZE"])

    buf = io.BytesIO()
    fig.savefig(buf, format="png", bbox_inches='tight', pad_inches=0.1)
    return base64.b64encode(buf.getvalue()).decode()

#=================================================================================================
def main():
#=================================================================================================
    setup_font()
    st.markdown(f'<h1 style="font-size:{CONFIG["TITLE_SIZE"]}px;">⛵ 風況チェッカー</h1>', unsafe_allow_html=True)

    # 初期座標の設定
    if 'lat' not in st.session_state:
        st.session_state.lat, st.session_state.lon = 31.340, 130.790

    st.sidebar.header("設定")
    basho = st.sidebar.selectbox("場所", ["高須沖(鹿児島県)", "錦江湾(鹿児島県)", "地図から指定"])
    
    current_place_name = basho
    if basho == "高須沖(鹿児島県)":
        st.session_state.lat, st.session_state.lon = 31.340, 130.790
    elif basho == "錦江湾(鹿児島県)":
        st.session_state.lat, st.session_state.lon = 31.590, 130.600
    
    use_map = st.sidebar.checkbox("地図で微調整する", value=False)
#=================================================================================================
        # --- 地図表示条件：微調整チェックが入っているか、場所が「地図から指定」の場合 ---
    if use_map or basho == "地図から指定":
        
        # 名称表示のロジック：プリセット場所の微調整中か、新規地点かを判定
        if basho != "地図から指定":
            current_place_name = f"{basho}(微調整中)"  # 「高須沖(微調整中)」などの表示
        else:
            current_place_name = "地図指定地点"       # 完全にフリーな地点の場合
    
        # --- CSS定義：地図を囲む枠(map-container)と、その四辺の中央にあるガイド線(guide)のスタイル ---
        st.markdown(f"""
            <style>
            .map-wrapper {{ 
                position: relative;             /* 子要素（ガイド線）の配置基準にする */
                width: {CONFIG["MAP_WIDTH"]}px; /* 設定された幅に固定 */
                border: 2px solid #ddd;         # 枠線を表示
                line-height: 0;                # 中の要素（地図）との隙間を詰める
            }}
            /* 共通設定：ガイド線を最前面(z-index: 1001)に配置し、マウス操作を透過させる(pointer-events: none) */
            .guide {{ position: absolute; background: red; z-index: 1001; pointer-events: none; }}
            
            /* 垂直ガイド線：左右中央(50%)に配置 */
            .guide-v {{ left: 50%; width: 2px; height: 15px; transform: translateX(-50%); }}
            .guide-t {{ top: 0; }}              /* 上端に配置 */
            .guide-b {{ bottom: 0; }}           /* 下端に配置 */
            
            /* 水平ガイド線：上下中央(50%)に配置 */
            .guide-h {{ top: 50%; height: 2px; width: 15px; transform: translateY(-50%); }}
            .guide-l {{ left: 0; }}             /* 左端に配置 */
            .guide-r {{ right: 0; }}            /* 右端に配置 */
            </style>
        """, unsafe_allow_html=True)
    
        st.info("地図の中心に合わせて予報地点を決定します。")
    
        # --- ガイド線を描画するためのHTML要素 (地図の「上に」重なるパーツ) ---
        # 注：Streamlitの仕様上、<div>の中にst_foliumを入れることは難しいため、
        # 枠とガイド線だけの「重なり」をCSSで制御します。
        st.markdown('''
            <div class="map-wrapper">
                <div class="guide guide-v guide-t"></div>
                <div class="guide guide-v guide-b"></div>
                <div class="guide guide-h guide-l"></div>
                <div class="guide guide-h guide-r"></div>
            </div>''', unsafe_allow_html=True)
        
        # --- 地図オブジェクトの作成 ---
        # location: 現在のセッション状態(緯度経度)を初期表示位置にする
        m = folium.Map(location=[st.session_state.lat, st.session_state.lon], zoom_start=12)
        
        # 地図の「中心そのもの」に赤い「╋」マーカーを設置
        # DivIconを使うことで、標準のピンではなく任意の文字(╋)を表示
        folium.Marker(
            [st.session_state.lat, st.session_state.lon],
            icon=folium.DivIcon(html=f'<div style="font-size: 24pt; color: red; font-weight: bold; text-align: center; width: 50px; margin-left: -25px; margin-top: -25px;">╋</div>')
        ).add_to(m)
    
        # --- 地図を画面に表示 (st_folium) ---
        # 上記のガイド線の下（物理的には地図の描画エリア）に表示される
        map_out = st_folium(m, width=CONFIG["MAP_WIDTH"]-4, height=CONFIG["MAP_HEIGHT"]-4, key="map")
    
        # --- 地図が動かされた（ドラッグ終了）時の処理 ---
        if map_out and map_out.get("center"):
            c = map_out["center"] # 地図の新しい中心座標を取得
            # 0.001度以上の変化があれば、セッション状態を更新してアプリを再起動(rerun)
            if abs(st.session_state.lat - c["lat"]) > 0.001 or abs(st.session_state.lon - c["lng"]) > 0.001:
                st.session_state.lat, st.session_state.lon = c["lat"], c["lng"]
                st.rerun()
#=================================================================================================

    days = st.sidebar.slider("表示日数", 1, 7, 7)
    danger_v = st.sidebar.number_input("危険風速(m/s)", value=10)
    
    w_step = 1 if days == 1 else (2 if days == 2 else 3)
    t_step = 3 if days == 1 else 6

    df = fetch_weather_data(st.session_state.lat, st.session_state.lon, days)
    if df is not None:
        df = process_wind_data(df, st.session_state.lat, st.session_state.lon, danger_v)
        img_base64 = create_graph(df, days, danger_v, w_step, t_step)

        st.markdown(f'<p style="font-size:14px;"><span style="color:gold;">■</span>最高 <span style="color:orange;">■</span>良好 <span style="color:skyblue;">■</span>ジャスト <span style="color:crimson;">■</span>危険 <span style="color:blue; font-weight:bold;">―</span>現在時刻</p>', unsafe_allow_html=True)
        # 指定の形式「地点: 名称 (緯度, 経度)」で表示
        st.markdown(f'<p style="font-weight:bold; font-size:16px;">地点: {current_place_name} ({st.session_state.lat:.3f}, {st.session_state.lon:.3f})</p>', unsafe_allow_html=True)
        
        st.markdown(f"""
            <div style="overflow-x: auto; white-space: nowrap; background: white; border-radius: 8px; border: 1px solid #eee;">
                <img src="data:image/png;base64,{img_base64}" style="height: 550px; max-width: none;">
            </div>
        """, unsafe_allow_html=True)

if __name__ == "__main__":
    main()

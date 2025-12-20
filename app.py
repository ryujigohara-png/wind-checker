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

# --- 設定 ---
CONFIG = {
    "TITLE_SIZE": 20,
    "SUBTITLE_SIZE": 16,
    "GRAPH_FONT_SIZE": 9,
    "LABEL_SIZE": 11,
    "DPI": 300,
    "MAP_WIDTH": 700,
    "MAP_HEIGHT": 400
}

def setup_font():
    font_url = "https://github.com/google/fonts/raw/main/ofl/notosansjp/NotoSansJP%5Bwght%5D.ttf"
    font_path = "NotoSansJP.ttf"
    if not os.path.exists(font_path):
        urllib.request.urlretrieve(font_url, font_path)
    fm.fontManager.addfont(font_path)
    plt.rc('font', family='Noto Sans JP', size=CONFIG["GRAPH_FONT_SIZE"])

def fetch_weather_data(lat, lon, days):
    url = f"https://api.open-meteo.com/v1/forecast?latitude={lat}&longitude={lon}&hourly=temperature_2m,wind_speed_10m,wind_direction_10m&timezone=Asia%2FTokyo&wind_speed_unit=ms&forecast_days=8"
    try:
        data = requests.get(url).json()
        df = pd.DataFrame(data["hourly"])
        df['time'] = pd.to_datetime(df['time'])
        return df.head(24 * days).reset_index(drop=True)
    except Exception as e:
        st.error(f"データ取得エラー: {e}")
        return None

def process_wind_data(df, lat, lon, danger_v):
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

def create_graph(df, days, danger_v, wind_step, time_step):
    fig_w = max(10, days * 4)
    # sharex=Trueを解除し、個別に軸を制御
    fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(fig_w, 8), dpi=CONFIG["DPI"])
    plt.subplots_adjust(hspace=0.7)

    # 共通の時間軸設定関数
    jp_weeks = ["月", "火", "水", "木", "金", "土", "日"]
    def formatter(x, p):
        dt = mdates.num2date(x)
        return dt.strftime('%m/%d') + f'\n({jp_weeks[dt.weekday()]})\n' + dt.strftime('%H:%M')

    # --- 上段：風速グラフ ---
    bars = ax1.bar(df['time'], df['wind_speed_10m'], color=df['color'], alpha=0.8, width=0.03)
    ax1.axhline(y=danger_v, color='red', linestyle='--', alpha=0.4)
    ax1.set_ylabel('風速 (m/s)', fontsize=CONFIG["LABEL_SIZE"])
    ax1.set_ylim(0, max(df['wind_speed_10m'].max(), danger_v) + 7)
    
    # 現在時刻
    jst = timezone(timedelta(hours=9))
    now_jst = datetime.now(jst).replace(tzinfo=None)
    ax1.axvline(now_jst, color='blue', linestyle='-', alpha=0.5, linewidth=2.5)

    # 風グラフの時刻軸表示
    ax1.xaxis.set_major_locator(mdates.HourLocator(interval=time_step))
    ax1.xaxis.set_major_formatter(plt.FuncFormatter(formatter))
    ax1.set_xlim(df['time'].iloc[0], df['time'].iloc[-1]) # 左端空白なし
    plt.setp(ax1.get_xticklabels(), ha='center')

    for i, bar in enumerate(bars):
        if i % wind_step == 0:
            h = bar.get_height()
            v = round(df['wind_speed_10m'].iloc[i])
            txt = f"{df['mark'].iloc[i]}\n{df['dir_name'].iloc[i]}\n{df['arrow'].iloc[i]}\n{v}m"
            ax1.text(bar.get_x() + bar.get_width()/2., h + 0.3, txt, ha='center', va='bottom', fontweight='bold')

    # --- 下段：気温グラフ ---
    ax2.plot(df['time'], df['temperature_2m'], color='#666666', linewidth=1.5)
    ax2.set_ylabel('気温 (℃)', fontsize=CONFIG["LABEL_SIZE"])
    ax2.xaxis.set_major_locator(mdates.HourLocator(interval=time_step))
    ax2.xaxis.set_major_formatter(plt.FuncFormatter(formatter))
    ax2.set_xlim(df['time'].iloc[0], df['time'].iloc[-1]) # 左端空白なし
    plt.setp(ax2.get_xticklabels(), ha='center')

    # グリッド
    ax1.grid(True, linestyle=':', alpha=0.5); ax2.grid(True, linestyle=':', alpha=0.5)

    buf = io.BytesIO()
    fig.savefig(buf, format="png", bbox_inches='tight', pad_inches=0.1)
    return base64.b64encode(buf.getvalue()).decode()

def main():
    setup_font()
    st.markdown(f'<h1 style="font-size:{CONFIG["TITLE_SIZE"]}px;">⛵ 風況チェッカー</h1>', unsafe_allow_html=True)

    if 'lat' not in st.session_state:
        st.session_state.lat, st.session_state.lon = 31.3420, 130.7870

    st.sidebar.header("設定")
    use_map = st.sidebar.checkbox("地図から場所を選択", value=False)

    if use_map:
        st.info("地図を動かすと、中心に合わせてポインターが移動し予報が更新されます。")
        m = folium.Map(location=[st.session_state.lat, st.session_state.lon], zoom_start=12)
        # 地図内にポインターを表示
        folium.Marker(
            [st.session_state.lat, st.session_state.lon],
            popup="現在の予報地点",
            icon=folium.Icon(color='blue', icon='info-sign')
        ).add_to(m)

        map_out = st_folium(m, width=CONFIG["MAP_WIDTH"], height=CONFIG["MAP_HEIGHT"], key="map")

        if map_out and map_out.get("center"):
            c = map_out["center"]
            if abs(st.session_state.lat - c["lat"]) > 0.0001 or abs(st.session_state.lon - c["lng"]) > 0.0001:
                st.session_state.lat, st.session_state.lon = c["lat"], c["lng"]
                st.rerun()

    days = st.sidebar.slider("表示日数", 1, 7, 7)
    danger_v = st.sidebar.number_input("危険風速(m/s)", value=10)
    
    w_step = 1 if days == 1 else (2 if days == 2 else 3)
    t_step = 3 if days == 1 else 6

    df = fetch_weather_data(st.session_state.lat, st.session_state.lon, days)
    if df is not None:
        df = process_wind_data(df, st.session_state.lat, st.session_state.lon, danger_v)
        img_base64 = create_graph(df, days, danger_v, w_step, t_step)

        st.markdown(f'<p style="font-size:14px;"><span style="color:gold;">■</span>最高 <span style="color:orange;">■</span>良好 <span style="color:skyblue;">■</span>ジャスト <span style="color:crimson;">■</span>危険 <span style="color:blue; font-weight:bold;">―</span>現在時刻</p>', unsafe_allow_html=True)
        st.markdown(f'<p style="font-weight:bold;">地点: ({st.session_state.lat:.3f}, {st.session_state.lon:.3f})</p>', unsafe_allow_html=True)
        st.markdown(f'<div style="overflow-x:auto; background:white; border-radius:8px;"><img src="data:image/png;base64,{img_base64}" style="height:550px;"></div>', unsafe_allow_html=True)

if __name__ == "__main__":
    main()

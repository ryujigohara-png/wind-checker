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

# --- 設定 ---
CONFIG = {
    "TITLE_SIZE": 22,
    "SUBTITLE_SIZE": 16,
    "GRAPH_FONT_SIZE": 14,
    "LABEL_SIZE": 14,
    "DPI": 300,
    "MAP_HEIGHT": 350
}

ALL_DIRECTIONS = ["北", "北北東", "北東", "東北東", "東", "東南東", "南東", "南南東", "南", "南南西", "南西", "西南西", "西", "西北西", "北西", "北北西"]

#========================================================================================================================
# フォント設定
#========================================================================================================================
def setup_font():
    font_url = "https://github.com/google/fonts/raw/main/ofl/notosansjp/NotoSansJP%5Bwght%5D.ttf"
    font_path = "NotoSansJP.ttf"
    if not os.path.exists(font_path):
        urllib.request.urlretrieve(font_url, font_path)
    fm.fontManager.addfont(font_path)
    plt.rc('font', family='Noto Sans JP', size=CONFIG["GRAPH_FONT_SIZE"])

#========================================================================================================================
# グラフ生成のキャッシュ処理
#========================================================================================================================
@st.cache_data(show_spinner=False)
def get_cached_graph(lat, lon, days, danger_v, selected_dirs_tuple):
    df = fetch_weather_data(lat, lon, days)
    if df is None: return None
    df = process_wind_data(df, list(selected_dirs_tuple), danger_v)
    wind_step = (1 if days <= 1 else (2 if days <= 3 else 3))
    time_step = (3 if days <= 2 else 6)
    return create_graph(df, days, danger_v, wind_step, time_step)

#========================================================================================================================
# 気象データの取得（Open-Meteo API）
#========================================================================================================================
def fetch_weather_data(lat, lon, days):
    url = f"https://api.open-meteo.com/v1/forecast?latitude={lat}&longitude={lon}&hourly=temperature_2m,wind_speed_10m,wind_direction_10m,weather_code&timezone=Asia%2FTokyo&wind_speed_unit=ms&forecast_days={days}"
    try:
        data = requests.get(url).json()
        df = pd.DataFrame(data["hourly"])
        df['time'] = pd.to_datetime(df['time'])
        df = df.head(24 * days).reset_index(drop=True)
        # 3時間の空白（余白）を設ける処理
        first_time = df['time'].iloc[0]
        padding = pd.DataFrame({
            'time': [first_time - timedelta(hours=i) for i in range(3, 0, -1)],
            'temperature_2m': [None]*3, 'wind_speed_10m': [None]*3, 'wind_direction_10m': [None]*3, 'weather_code': [None]*3
        })
        return pd.concat([padding, df], ignore_index=True)
    except Exception:
        return None

#========================================================================================================================
# 潮汐データの計算（擬似計算）
#========================================================================================================================
def get_tide_level(times):
    base_full_tide = datetime(2025, 1, 1, 6, 0) 
    cycle_hours = 12.42
    levels = []
    for t in times:
        if pd.isna(t): levels.append(None); continue
        hours_from_base = (t - base_full_tide).total_seconds() / 3600
        level = 100 * np.cos(2 * np.pi * hours_from_base / cycle_hours)
        levels.append(level)
    return levels

#========================================================================================================================
# 天気コードの変換
#========================================================================================================================
def get_weather_info(code):
    if code is None: return "", "black"
    if code <= 2: return "晴", "#FF8C00"
    if code <= 48: return "曇", "#696969"
    if code <= 99: return "雨", "#0000FF"
    return "？", "black"

#========================================================================================================================
# 風向・風速データの加工と判定
#========================================================================================================================
def process_wind_data(df, target_dirs, danger_v):
    dirs = ALL_DIRECTIONS + ["北"]
    arrows = ["↓", "↙", "↙", "↙", "←", "↖", "↖", "↖", "↑", "↗", "↗", "↗", "→", "↘", "↘", "↘", "↓"]
    def get_info(deg):
        if pd.isna(deg): return "", ""
        idx = int((deg + 11.25) / 22.5) % 16
        return dirs[idx], arrows[idx]
    df['res'] = df['wind_direction_10m'].apply(get_info)
    df['dir_name'] = df['res'].apply(lambda x: x[0]); df['arrow'] = df['res'].apply(lambda x: x[1])
    weather_res = df['weather_code'].apply(get_weather_info)
    df['w_text'] = [r[0] for r in weather_res]; df['w_color'] = [r[1] for r in weather_res]
    def judge(row):
        speed = row['wind_speed_10m']
        if pd.isna(speed): return "none"
        if speed >= danger_v: return "crimson"
        if row['dir_name'] in target_dirs:
            if 6 <= speed < danger_v: return "orange"
            if 3 <= speed < 6: return "skyblue"
        return "#D3D3D3"
    df['color'] = df.apply(judge, axis=1); df['tide_level'] = get_tide_level(df['time'])
    return df

#========================================================================================================================
# Matplotlibによるグラフ作成
#========================================================================================================================
def create_graph(df, days, danger_v, wind_step, time_step):
    fig_w = max(10, days * 4.5)
    fig, (ax1, ax2, ax3) = plt.subplots(3, 1, figsize=(fig_w, 10), dpi=CONFIG["DPI"], gridspec_kw={'height_ratios': [4, 1.2, 1.2]})
    plt.subplots_adjust(hspace=0.6)
    jp_weeks = ["月", "火", "水", "木", "金", "土", "日"]
    def formatter(x, p):
        dt = mdates.num2date(x)
        if dt.hour == 0: return dt.strftime('%m/%d') + f'\n({jp_weeks[dt.weekday()]})\n' + dt.strftime('%H:%M')
        else: return dt.strftime('%H:%M')
    bars = ax1.bar(df['time'], df['wind_speed_10m'], color=df['color'], alpha=0.9, width=0.03)
    ax1.axhline(y=danger_v, color='red', linestyle='--', alpha=0.6)
    ax1.set_ylabel('風速 (m/s)', fontsize=CONFIG["LABEL_SIZE"])
    max_speed = df['wind_speed_10m'].dropna().max() if not df['wind_speed_10m'].dropna().empty else 0
    ax1.set_ylim(0, max(max_speed, danger_v) + 5) 
    jst = timezone(timedelta(hours=9)); now_jst = datetime.now(jst).replace(tzinfo=None)
    for ax in [ax1, ax2, ax3]:
        ax.axvline(now_jst, color='blue', linestyle='-', alpha=0.6, linewidth=2.5)
        ax.xaxis.set_major_locator(mdates.HourLocator(byhour=range(0, 24, time_step)))
        ax.xaxis.set_major_formatter(plt.FuncFormatter(formatter))
        ax.set_xlim(df['time'].iloc[0], df['time'].iloc[-1])
        ax.grid(True, linestyle=':', alpha=0.4, color='#000000')
    ax2.plot(df['time'], df['temperature_2m'], color='black', linewidth=1.5)
    ax2.set_ylabel('気温(℃)', fontsize=CONFIG["LABEL_SIZE"])
    ax3.plot(df['time'], df['tide_level'], color='royalblue', linewidth=2)
    ax3.fill_between(df['time'], df['tide_level'], -120, color='royalblue', alpha=0.2)
    ax3.set_ylabel('潮位', fontsize=CONFIG["LABEL_SIZE"]); ax3.set_yticks([])
    for i, bar in enumerate(bars):
        if not pd.isna(df['wind_speed_10m'].iloc[i]) and i % wind_step == 0:
            h = bar.get_height()
            ax1.text(bar.get_x() + bar.get_width()/2., h + 3.0, df['w_text'].iloc[i], ha='center', va='bottom', color=df['w_color'].iloc[i], fontweight='bold', fontsize=12)
            txt = f"{df['dir_name'].iloc[i]}\n{df['arrow'].iloc[i]}\n{round(df['wind_speed_10m'].iloc[i])}m"
            ax1.text(bar.get_x() + bar.get_width()/2., h + 0.3, txt, ha='center', va='bottom', fontweight='bold', color='black', fontsize=10)
    buf = io.BytesIO(); fig.savefig(buf, format="png", bbox_inches='tight', pad_inches=0.1)
    return base64.b64encode(buf.getvalue()).decode()

#========================================================================================================================
# メインアプリケーション
#========================================================================================================================
def main():
    setup_font()
    st.markdown(f'<h1 style="font-size:{CONFIG["TITLE_SIZE"]}px; margin-bottom: 5px;">⛵ 高須風チェッカー</h1>', unsafe_allow_html=True)
    
    params = st.query_params
    init_lat = float(params.get("lat", 31.337))
    init_lon = float(params.get("lon", 130.795))
    init_days = int(params.get("days", 8))
    init_danger = float(params.get("danger", 10.0))
    init_dirs = params.get("dirs", "南,南南西,南西,西南西,西,西北西,北西,北北西").split(",")

    if 'lat' not in st.session_state: st.session_state.lat = init_lat
    if 'lon' not in st.session_state: st.session_state.lon = init_lon
    if 'last_basho' not in st.session_state: st.session_state.last_basho = "高須沖(鹿児島県)"

    # 地点選択セクション
    col_sel, col_map_check = st.columns([7, 3])
    basho_list = ["高須沖(鹿児島県)", "柏原沖(鹿児島県)", "垂水港(鹿児島県)", "海潟(鹿児島県)", "磯海岸沖(鹿児島県)", "江口浜沖(鹿児島県)", "錦江湾(鹿児島県)", "地図で指定"]
    
    with col_sel:
        current_idx = basho_list.index(st.session_state.last_basho) if st.session_state.last_basho in basho_list else 7
        basho = st.selectbox("地点を選択", basho_list, index=current_idx, label_visibility="collapsed")
    
    with col_map_check:
        show_map = st.checkbox("地図表示", value=st.session_state.get('show_map_state', False))
        st.session_state.show_map_state = show_map

    st.markdown(f"<p style='font-size:12px; color:#666; margin-top:-10px;'>グラフ描画地点： 緯度 {st.session_state.lat:.4f} / 経度 {st.session_state.lon:.4f}</p>", unsafe_allow_html=True)

    if st.session_state.last_basho != basho:
        coords = {"高須沖(鹿児島県)":(31.337, 130.795), "柏原沖(鹿児島県)":(31.380, 131.020), "垂水港(鹿児島県)":(31.478, 130.668), "海潟(鹿児島県)":(31.539, 130.706), "磯海岸沖(鹿児島県)":(31.614, 130.577), "江口浜沖(鹿児島県)":(31.643, 130.322), "錦江湾(鹿児島県)":(31.590, 130.600)}
        if basho in coords:
            st.session_state.lat, st.session_state.lon = coords[basho]
            st.session_state.last_basho = basho
            st.rerun()
        elif basho == "地図で指定":
            st.session_state.last_basho = basho

    # 地図表示セクション（外枠ガイド方式：比率1:16:1）
    if show_map:
        st.info("テスト中：地図のみ表示")
        # 矢印なし・カラムなしで地図を100%幅で表示
        map_out = st_folium(m, width=None, use_container_width=True, height=CONFIG["MAP_HEIGHT"])
# --- 地図表示（外枠ガイド方式：HTMLテーブルで横並びを強制） ---
    if show_map:
        st.info("地図の中央地点のグラフを描画表示することができます。")
        
        # 上の矢印
        st.markdown("<div style='text-align:center; color:crimson; font-size:24px; font-weight:bold; margin-bottom:-10px;'>▼</div>", unsafe_allow_html=True)
        
        # HTMLテーブルを使用して、スマホでも強制的に横並びにする
        map_html = f"""
        <table style="width:100%; border:none; border-collapse:collapse; table-layout:fixed;">
            <tr>
                <td style="width:5%; text-align:right; vertical-align:middle; color:crimson; font-size:24px; font-weight:bold; padding:0;">▶</td>
                <td style="width:90%; padding:0; vertical-align:middle;" id="map_container">
                    </td>
                <td style="width:5%; text-align:left; vertical-align:middle; color:crimson; font-size:24px; font-weight:bold; padding:0;">◀</td>
            </tr>
        </table>
        """
        # 矢印ガイドのみ先に表示（地図を挟む枠組み）
        # ※Streamlitの制約上、st_foliumをテーブルの中に直接入れることはできないため、
        #   「矢印を独立させたカラム」のスタックをCSSで防止する方法を適用します。

        st.markdown("""
            <style>
            [data-testid="column"] {
                min-width: 0px !important;
                flex-basis: content !important;
            }
            div[data-testid="stHorizontalBlock"] {
                flex-wrap: nowrap !important;
            }
            </style>
            """, unsafe_allow_html=True)

        col_l, col_m, col_r = st.columns([1, 18, 1])
        with col_l:
            st.markdown(f"<div style='line-height:{CONFIG['MAP_HEIGHT']}px; text-align:right; color:crimson; font-size:24px; font-weight:bold;'>▶</div>", unsafe_allow_html=True)
        with col_m:
            map_key = f"map_view_{st.session_state.lat}_{st.session_state.lon}"
            m = folium.Map(location=[st.session_state.lat, st.session_state.lon], zoom_start=13)
            folium.Marker([st.session_state.lat, st.session_state.lon], tooltip="現在の描画地点", icon=folium.Icon(color='red')).add_to(m)
            map_out = st_folium(m, width=None, height=CONFIG["MAP_HEIGHT"], key=map_key, returned_objects=["center"])
        with col_r:
            st.markdown(f"<div style='line-height:{CONFIG['MAP_HEIGHT']}px; text-align:left; color:crimson; font-size:24px; font-weight:bold;'>◀</div>", unsafe_allow_html=True)
            
        st.markdown("<div style='text-align:center; color:crimson; font-size:24px; font-weight:bold; margin-top:-10px;'>▲</div>", unsafe_allow_html=True)
        
        if map_out and map_out.get("center"):
            if st.button("グラフ描画地点確定", use_container_width=True):
                st.session_state.lat, st.session_state.lon = map_out["center"]["lat"], map_out["center"]["lng"]
                st.session_state.last_basho = "地図で指定"
                st.rerun()

    # サイドバー設定
    st.sidebar.header("表示設定")
    days = st.sidebar.slider("表示日数", 1, 8, init_days)
    danger_v = st.sidebar.number_input("危険風速(m/s)", value=init_danger)
    st.sidebar.markdown("---")
    st.sidebar.header("乗れる風向")
    cols = st.sidebar.columns(2); selected_target_dirs = []
    for i, d in enumerate(ALL_DIRECTIONS):
        with cols[i % 2]:
            if st.checkbox(d, value=(d in init_dirs), key=f"chk_{d}"):
                selected_target_dirs.append(d)

    st.query_params.update({"lat": st.session_state.lat, "lon": st.session_state.lon, "days": days, "danger": danger_v, "dirs": ",".join(selected_target_dirs)})

    # グラフ表示
    img_base64 = get_cached_graph(st.session_state.lat, st.session_state.lon, days, danger_v, tuple(selected_target_dirs))

    if img_base64:
        with st.expander("📊 凡例・自分専用設定の保存方法"):
            st.markdown(f'''<p style="font-size:14px;"><span style="color:skyblue;">■</span> 3-6m/s &nbsp; <span style="color:orange;">■</span> 6-10m/s &nbsp; <span style="color:crimson;">■</span> {danger_v}m/s以上<br><span style="color:crimson;">---</span> 危険風速{danger_v}m/s</p><hr><p style="font-size:12px; color:#333;"><b>自分専用設定の保存</b><br>iPhone: Safari下の「共有」→「ホーム画面に追加」<br>Android: Chrome右上の「︙」→「ホーム画面に追加」</p>''', unsafe_allow_html=True)
        st.markdown(f'<div style="overflow-x: auto; background: white; border-radius: 8px; border: 1px solid #eee; margin-top: 5px;"><img src="data:image/png;base64,{img_base64}" style="height: 520px; max-width: none;"></div>', unsafe_allow_html=True)

if __name__ == "__main__": main()

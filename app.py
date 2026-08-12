import streamlit as st
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import re
import os

# --- 1. Configuration & Theming ---
st.set_page_config(page_title="PESU Market Intelligence '27", layout="wide", page_icon="⚡")

st.markdown("""
    <style>
    .stApp { background-color: #0E1117; color: #FAFAFA; }
    .glass-card {
        background: rgba(255, 255, 255, 0.03);
        backdrop-filter: blur(16px);
        -webkit-backdrop-filter: blur(16px);
        border-radius: 15px;
        padding: 25px;
        border: 1px solid rgba(255, 255, 255, 0.08);
        box-shadow: 0 4px 30px rgba(0, 0, 0, 0.1);
        margin-bottom: 20px;
    }
    .metric-value { font-size: 2.2rem; font-weight: 800; color: #00FF9D; line-height: 1.2; }
    .metric-sub { font-size: 1.2rem; color: #636EFA; font-weight: 600; margin-top: 5px; }
    .metric-label { font-size: 0.85rem; color: #8892B0; text-transform: uppercase; letter-spacing: 1.5px; margin-bottom: 5px; }
    .highlight-text { color: #636EFA; font-weight: 600; }
    </style>
""", unsafe_allow_html=True)

# --- 2. Core Data Processing ---
@st.cache_data
def clean_headers(df):
    header_idx = next((i for i, row in df.iterrows() if 'Company' in str(row.values)), None)
    if header_idx is None: return df
    
    main_cols = pd.Series(df.iloc[header_idx].values).ffill()
    sub_cols = pd.Series(df.iloc[header_idx+1].values).fillna('')
    
    final_cols = [f"{m} - {s}".strip(" -") if s and s != 'nan' else str(m).strip() for m, s in zip(main_cols, sub_cols)]
    df = df.iloc[header_idx+2:].reset_index(drop=True)
    df.columns = final_cols
    df['Company'] = df['Company'].ffill()
    return df

def normalize_text(text): return re.sub(r'\(.*?\)', '', str(text).lower().strip()).strip()

def extract_numeric(val):
    try:
        matches = re.findall(r'(\d+\.?\d*)', str(val))
        return float(matches[0]) if matches else None
    except:
        return None

@st.cache_data
def load_historical_data():
    df_26 = pd.DataFrame()
    if os.path.exists("Placement Scene '26.xlsx"):
        xls_26 = pd.ExcelFile("Placement Scene '26.xlsx")
        dfs = []
        for sheet in ['Tier 1', 'Tier 2', 'Tier 3', 'Internship Only', 'Summer Internship PPOs']:
            if sheet in xls_26.sheet_names:
                df = clean_headers(pd.read_excel(xls_26, sheet_name=sheet, header=None))
                df['Source_Tier'] = sheet
                dfs.append(df)
        
        if dfs:
            df_26 = pd.concat(dfs, ignore_index=True)
            df_26['Norm_Company'] = df_26['Company'].apply(normalize_text)
            
            base_col = next((c for c in df_26.columns if 'Base' in c), None)
            ctc_col = next((c for c in df_26.columns if 'CTC' in c), None)
            
            df_26['Parsed_Base'] = df_26[base_col].apply(extract_numeric) if base_col else None
            df_26['Parsed_CTC'] = df_26[ctc_col].apply(extract_numeric) if ctc_col else None
            if 'Role' not in df_26.columns: df_26['Role'] = 'N/A'
                
            if 'OA Date' in df_26.columns:
                extracted = df_26['OA Date'].astype(str).str.extract(r'(\d{2}/\d{2}/\d{2,4})')[0]
                df_26['OA_Date_Parsed'] = pd.to_datetime(extracted, format='mixed', dayfirst=True, errors='coerce')
    return df_26

df_26 = load_historical_data()

# --- Advanced Academic Timeline Parser ---
def get_timeline_grouping(df):
    if df.empty or 'OA_Date_Parsed' not in df.columns: return pd.DataFrame(), df
    valid_df = df.dropna(subset=['OA_Date_Parsed']).copy()
    
    def parse_academic_time(d):
        acad_month = d.month - 7 if d.month >= 8 else d.month + 5
        week_of_month = (d.day - 1) // 7 + 1
        sort_key = acad_month * 10 + week_of_month
        label = f"{d.strftime('%b')} - W{week_of_month}"
        return pd.Series([sort_key, label])
        
    valid_df[['SortKey', 'Time_Label']] = valid_df['OA_Date_Parsed'].apply(parse_academic_time)
    
    grouped = valid_df.groupby(['SortKey', 'Time_Label']).agg(
        Count=('Company', 'count'),
        Company_List=('Company', lambda x: '<br> • '.join(list(x)[:10]) + ('<br>   <i>...and more</i>' if len(x)>10 else ''))
    ).reset_index()
    
    return grouped.sort_values('SortKey'), valid_df

# --- Heatmap Generator with Hover Targeting ---
def build_heatmap(df, val_col, title, colorscale):
    if df.empty or val_col not in df.columns or 'Time_Label' not in df.columns: return go.Figure()
    
    valid_df = df.dropna(subset=[val_col, 'SortKey', 'Time_Label']).copy()
    if valid_df.empty: return go.Figure()
    
    # Financial Buckets
    bins = [0, 8, 12, 16, 25, 40, 100]
    labels = ['< 8 LPA', '8 - 12 LPA', '12 - 16 LPA', '16 - 25 LPA', '25 - 40 LPA', '40+ LPA']
    valid_df['Bucket'] = pd.cut(valid_df[val_col], bins=bins, labels=labels, right=False)
    
    # Group to map both the quantitative count and the qualitative company names
    grouped = valid_df.groupby(['Bucket', 'Time_Label'], observed=True).agg(
        Count=('Company', 'count'),
        Company_List=('Company', lambda x: '<br> • '.join(list(x)[:10]) + ('<br>   <i>...and more</i>' if len(x)>10 else ''))
    ).reset_index()
    
    count_matrix = grouped.pivot(index='Bucket', columns='Time_Label', values='Count').fillna(0)
    comps_matrix = grouped.pivot(index='Bucket', columns='Time_Label', values='Company_List').fillna('No Companies Scheduled')
    
    time_sort = valid_df[['Time_Label', 'SortKey']].drop_duplicates().sort_values('SortKey')
    count_matrix = count_matrix.reindex(columns=time_sort['Time_Label'], fill_value=0)
    comps_matrix = comps_matrix.reindex(columns=time_sort['Time_Label'], fill_value='No Companies Scheduled')
    
    count_matrix = count_matrix.reindex(labels[::-1]) 
    comps_matrix = comps_matrix.reindex(labels[::-1])
    
    fig = go.Figure(data=go.Heatmap(
        z=count_matrix.values,
        x=count_matrix.columns,
        y=count_matrix.index,
        colorscale=colorscale,
        text=count_matrix.values,
        texttemplate="%{text}",
        customdata=comps_matrix.values,
        showscale=False,
        hovertemplate="<b>%{x}</b><br>Range: %{y}<br>OAs Conducted: %{z} Companies<br><br><b>Companies:</b><br>%{customdata}<extra></extra>"
    ))
    
    fig.update_layout(
        title=title,
        plot_bgcolor='rgba(0,0,0,0)', paper_bgcolor='rgba(0,0,0,0)', font=dict(color='white'),
        xaxis=dict(showgrid=False), yaxis=dict(showgrid=False),
        margin=dict(t=50, b=20, l=10, r=10)
    )
    return fig

# --- 3. UI Structure & Ingestion ---
st.sidebar.image("https://upload.wikimedia.org/wikipedia/en/e/e4/PES_University_logo.png", width=120)
st.sidebar.markdown("### 📥 Data Injection")
uploaded_file = st.sidebar.file_uploader("Drop 'Placements 27 .xlsx'", type=['xlsx'])

st.title("⚡ PESU Market Intelligence: Class of '27")

if uploaded_file and not df_26.empty:
    df_27_raw = pd.read_excel(uploaded_file, header=None)
    df_27 = clean_headers(df_27_raw)
    df_27['Norm_Company'] = df_27['Company'].apply(normalize_text)
    
    ctc_col_27 = next((c for c in df_27.columns if 'CTC' in c.upper() or 'COMPENSATION' in c.upper()), None)
    base_col_27 = next((c for c in df_27.columns if 'BASE' in c.upper()), None)
    gpa_col_27 = next((c for c in df_27.columns if 'GPA' in c.upper()), None)
    oa_col_27 = next((c for c in df_27.columns if 'OA' in c.upper()), None)
    
    df_27['Parsed_CTC'] = df_27[ctc_col_27].apply(extract_numeric) if ctc_col_27 else None
    df_27['Parsed_Base'] = df_27[base_col_27].apply(extract_numeric) if base_col_27 else None
    if 'Role' not in df_27.columns: df_27['Role'] = 'N/A'
        
    if gpa_col_27: df_27['Parsed_GPA'] = df_27[gpa_col_27].apply(extract_numeric)
    if oa_col_27: df_27['OA_Date_Parsed'] = pd.to_datetime(df_27[oa_col_27], errors='coerce')

    tab1, tab2, tab3, tab4 = st.tabs(["🚀 Target Intel", "⏱️ Timeline Radar", "👻 Ghost List", "🔥 Financial Heatmaps"])

    # --- TAB 1: Core Target Intel ---
    with tab1:
        st.subheader("Market X-Ray: Compare Target Offerings")
        common_cos = set(df_26['Norm_Company']).intersection(set(df_27['Norm_Company']))
        
        col_xray, col_delta = st.columns([1.2, 2])
        
        with col_xray:
            st.markdown("##### 🔍 Deep Target Intel")
            target_options = sorted(list(common_cos))
            default_target = next((c for c in ["lam research", "inmobi groups"] if c in target_options), target_options[0] if target_options else None)
            selected_target = st.selectbox("Select Overlapping Company", target_options, index=target_options.index(default_target) if default_target else 0)
            
            if selected_target:
                t26 = df_26[df_26['Norm_Company'] == selected_target].iloc[0]
                t27 = df_27[df_27['Norm_Company'] == selected_target].iloc[0]
                
                st.markdown(f"""
                <div class="glass-card">
                    <div style="display:flex; justify-content:space-between; margin-bottom:15px;">
                        <div>
                            <div class="metric-label">2026 Historical</div>
                            <div class="metric-value">₹ {t26.get('Parsed_CTC', 'N/A')} <span style="font-size:1rem; color:#8892B0;">CTC</span></div>
                            <div class="metric-sub">₹ {t26.get('Parsed_Base', 'N/A')} <span style="font-size:0.9rem; color:#8892B0;">BASE</span></div>
                        </div>
                        <div style="text-align:right;">
                            <div class="metric-label">2027 Live</div>
                            <div class="metric-value" style="color:#636EFA;">₹ {t27.get('Parsed_CTC', 'N/A')} <span style="font-size:1rem; color:#8892B0;">CTC</span></div>
                            <div class="metric-sub">₹ {t27.get('Parsed_Base', 'N/A') if 'Parsed_Base' in t27 else 'N/A'} <span style="font-size:0.9rem; color:#8892B0;">BASE</span></div>
                        </div>
                    </div>
                    <hr style="border-color: rgba(255,255,255,0.1);">
                    <div style="font-size:0.95rem; color:#E2E8F0;">
                        <p><b>🏢 Role Shift:</b> {t26.get('Role', 'N/A')} ➔ <span class="highlight-text">{t27.get('Role', 'N/A')}</span></p>
                        <p><b>🎓 GPA Cutoff:</b> {t26.get('GPA Cutoff', 'N/A')} ➔ <span class="highlight-text">{t27.get('GPA Cutoff', 'N/A')}</span></p>
                    </div>
                </div>
                """, unsafe_allow_html=True)
                
        with col_delta:
            st.markdown("##### 💸 YoY Total CTC Deltas")
            df_common_26 = df_26[df_26['Norm_Company'].isin(common_cos)].groupby('Norm_Company').first().reset_index()
            df_common_27 = df_27[df_27['Norm_Company'].isin(common_cos)].groupby('Norm_Company').first().reset_index()
            
            merged = pd.merge(df_common_26, df_common_27, on='Norm_Company', suffixes=('_26', '_27')).dropna(subset=['Parsed_CTC_26', 'Parsed_CTC_27'])
            merged['Delta'] = merged['Parsed_CTC_27'] - merged['Parsed_CTC_26']
            merged = merged.sort_values('Delta', ascending=False)
            merged['Display_Name'] = merged['Norm_Company'].str.title()
            
            for col in ['Parsed_Base_26', 'Parsed_CTC_26', 'Role_26', 'Parsed_Base_27', 'Parsed_CTC_27', 'Role_27']:
                merged[col] = merged[col].fillna("N/A")
            
            colors = ['#00FF9D' if val > 0 else '#FF4B4B' if val < 0 else '#8892B0' for val in merged['Delta']]
            fig_delta = go.Figure(data=[go.Bar(
                x=merged['Display_Name'], y=merged['Delta'], marker_color=colors, text=merged['Delta'], textposition='outside',
                customdata=merged[['Parsed_Base_26', 'Parsed_CTC_26', 'Role_26', 'Parsed_Base_27', 'Parsed_CTC_27', 'Role_27']],
                hovertemplate="<b>%{x}</b><br><br><b>Market Delta:</b> %{y} LPA<br><hr><b>2026:</b><br>Role: %{customdata[2]}<br>Base: %{customdata[0]} | CTC: %{customdata[1]}<br><br><b>2027:</b><br>Role: %{customdata[5]}<br>Base: %{customdata[3]} | CTC: %{customdata[4]}<extra></extra>"
            )])
            fig_delta.update_layout(plot_bgcolor='rgba(0,0,0,0)', paper_bgcolor='rgba(0,0,0,0)', font=dict(color='white'), margin=dict(l=0, r=0, t=30, b=0), height=400)
            st.plotly_chart(fig_delta, use_container_width=True)

    # --- TAB 2: Timeline Radar ---
    with tab2:
        st.subheader("Placement Velocity: 2026 vs 2027 (Overlay)")
        grouped_26, valid_26 = get_timeline_grouping(df_26)
        grouped_27, valid_27 = get_timeline_grouping(df_27)
        
        all_cats = pd.concat([
            grouped_26[['SortKey', 'Time_Label']], 
            grouped_27[['SortKey', 'Time_Label']] if not grouped_27.empty else pd.DataFrame()
        ]).drop_duplicates().sort_values('SortKey')
        
        fig_timeline = go.Figure()
        if not grouped_26.empty:
            fig_timeline.add_trace(go.Scatter(x=grouped_26['Time_Label'], y=grouped_26['Count'], mode='lines+markers', name="2026 Historical", line=dict(color='#8892B0', width=2, dash='dot'), customdata=grouped_26[['Company_List']], hovertemplate="<b>%{x} (2026)</b><br>Volume: %{y} Companies<br><br><b>Companies:</b><br>%{customdata[0]}<extra></extra>"))
        if not grouped_27.empty:
            fig_timeline.add_trace(go.Scatter(x=grouped_27['Time_Label'], y=grouped_27['Count'], mode='lines+markers', name="2027 Live (Starts Aug '27)", line=dict(color='#00FF9D', width=4), marker=dict(size=10, symbol='diamond'), customdata=grouped_27[['Company_List']], hovertemplate="<b>%{x} (2027)</b><br>Volume: %{y} Companies<br><br><b>Companies:</b><br>%{customdata[0]}<extra></extra>"))
            
        fig_timeline.update_xaxes(categoryorder='array', categoryarray=all_cats['Time_Label'].tolist())
        fig_timeline.update_layout(xaxis_title="Placement Calendar", yaxis_title="Number of Companies", plot_bgcolor='rgba(0,0,0,0)', paper_bgcolor='rgba(0,0,0,0)', font=dict(color='white'))
        st.plotly_chart(fig_timeline, use_container_width=True)
        
        st.markdown("##### 🗂️ Deep Dive: Inspect Specific Calendar Week")
        if not all_cats.empty:
            selected_week_label = st.selectbox("Select a week to view exact metadata for companies that held OAs during that timeframe:", all_cats['Time_Label'].tolist())
            
            col_26, col_27 = st.columns(2)
            with col_26:
                st.markdown(f"**2026 Companies ({selected_week_label})**")
                week_df_26 = valid_26[valid_26['Time_Label'] == selected_week_label]
                st.dataframe(week_df_26[['Company', 'Role', 'Parsed_CTC', 'GPA Cutoff', 'Note']] if not week_df_26.empty else pd.DataFrame(), use_container_width=True)
            with col_27:
                st.markdown(f"**2027 Companies ({selected_week_label})**")
                week_df_27 = valid_27[valid_27['Time_Label'] == selected_week_label] if not valid_27.empty else pd.DataFrame()
                st.dataframe(week_df_27[['Company', 'Role', 'Parsed_CTC', 'GPA Cutoff', 'Note']] if not week_df_27.empty else pd.DataFrame(), use_container_width=True)

    # --- TAB 3: Ghost List ---
    with tab3:
        st.subheader("👻 The Pending Market")
        comps_26 = set(df_26['Norm_Company'].dropna().unique())
        comps_27 = set(df_27['Norm_Company'].dropna().unique())
        pending = list(comps_26 - comps_27)
        
        if pending:
            ghosts_df = df_26[df_26['Norm_Company'].isin(pending)].copy()
            ghost_grouped, valid_ghost_dates = get_timeline_grouping(ghosts_df)
            
            ghost_tab1, ghost_tab2 = st.tabs(["📅 Expected Drop Radar", "📋 Complete Pending Database"])
            
            with ghost_tab1:
                fig_ghost_radar = go.Figure()
                if not ghost_grouped.empty:
                    fig_ghost_radar.add_trace(go.Scatter(x=ghost_grouped['Time_Label'], y=ghost_grouped['Count'], mode='lines+markers', fill='tozeroy', line=dict(color='#FF4B4B', width=3), marker=dict(size=8), customdata=ghost_grouped[['Company_List']], hovertemplate="<b>%{x}</b><br>Expected Drop: %{y} Companies<br><br><b>Pending Targets:</b><br>%{customdata[0]}<extra></extra>"))
                    fig_ghost_radar.update_xaxes(categoryorder='array', categoryarray=ghost_grouped.sort_values('SortKey')['Time_Label'].tolist())
                fig_ghost_radar.update_layout(title="When Did They Test Last Year?", plot_bgcolor='rgba(0,0,0,0)', paper_bgcolor='rgba(0,0,0,0)', font=dict(color='white'))
                st.plotly_chart(fig_ghost_radar, use_container_width=True)
                
                st.markdown("##### 🗂️ Deep Dive: Inspect Pending Week")
                if not ghost_grouped.empty:
                    selected_ghost_week = st.selectbox("Select a week to view exact metadata for the pending companies expected to drop:", ghost_grouped.sort_values('SortKey')['Time_Label'].tolist())
                    week_ghost_df = valid_ghost_dates[valid_ghost_dates['Time_Label'] == selected_ghost_week]
                    st.dataframe(week_ghost_df[['Company', 'Role', 'Parsed_Base', 'Parsed_CTC', 'Source_Tier', 'GPA Cutoff']], use_container_width=True)

            with ghost_tab2:
                cols_to_display = ['Company', 'Role', 'Parsed_Base', 'Parsed_CTC', 'Source_Tier', 'GPA Cutoff', 'OA Date']
                valid_cols = [c for c in cols_to_display if c in ghosts_df.columns]
                st.dataframe(ghosts_df[valid_cols].sort_values('Parsed_CTC', ascending=False), use_container_width=True)

    # --- TAB 4: Financial Density Heatmaps ---
    with tab4:
        st.subheader("🔥 Financial Density (Time vs. Compensation)")
        st.markdown("Hover over any cell block to reveal exactly which companies fall into that financial bracket during that week.")
        
        _, valid_heatmap_26 = get_timeline_grouping(df_26)
        
        col_heat1, col_heat2 = st.columns(2)
        
        with col_heat1:
            st.markdown("<div class='glass-card'>", unsafe_allow_html=True)
            fig_ctc = build_heatmap(valid_heatmap_26, 'Parsed_CTC', "Total CTC Distribution by Week", "Teal")
            st.plotly_chart(fig_ctc, use_container_width=True)
            st.markdown("</div>", unsafe_allow_html=True)
            
        with col_heat2:
            st.markdown("<div class='glass-card'>", unsafe_allow_html=True)
            fig_base = build_heatmap(valid_heatmap_26, 'Parsed_Base', "Base Salary Distribution by Week", "Purpor")
            st.plotly_chart(fig_base, use_container_width=True)
            st.markdown("</div>", unsafe_allow_html=True)

else:
    st.info("👈 Upload your 2027 Placements data in the sidebar to initialize the Intelligence Engine.")
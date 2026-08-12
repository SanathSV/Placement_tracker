import streamlit as st
import pandas as pd
import numpy as np
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

# --- 2. Helper Functions ---
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

def normalize_text(text): 
    name = str(text).lower().strip()
    name = re.sub(r'\(.*?\)', '', name) 
    name = re.sub(r'[^a-z0-9]', '', name)
    suffixes = ['groups', 'group', 'technologies', 'technology', 'tech', 'apps', 'app', 'solutions', 'labs', 'inc', 'pvt', 'ltd']
    for s in suffixes:
        if name.endswith(s) and len(name) > len(s):
            name = name[:-len(s)]
    return name.strip()

def extract_numeric(val):
    try:
        matches = re.findall(r'(\d+\.?\d*)', str(val))
        return float(matches[0]) if matches else None
    except:
        return None

def sanitize_for_arrow(df):
    if df.empty: return df
    clean_df = df.copy()
    for col in clean_df.columns:
        if clean_df[col].dtype == 'object':
            clean_df[col] = clean_df[col].astype(str).replace({'nan': '', 'None': ''})
    return clean_df

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

# --- Multi-Line Density Chart Generator ---
def build_density_line_chart(df, val_col, title):
    if df.empty or val_col not in df.columns or 'Time_Label' not in df.columns: return go.Figure()
    
    valid_df = df.dropna(subset=[val_col, 'SortKey', 'Time_Label']).copy()
    if valid_df.empty: return go.Figure()
    
    bins = [0, 8, 12, 16, 25, 40, 100]
    labels = ['< 8 LPA', '8 - 12 LPA', '12 - 16 LPA', '16 - 25 LPA', '25 - 40 LPA', '40+ LPA']
    valid_df['Bucket'] = pd.cut(valid_df[val_col], bins=bins, labels=labels, right=False)
    
    grouped = valid_df.groupby(['Bucket', 'SortKey', 'Time_Label'], observed=True).agg(
        Count=('Company', 'count'),
        Company_List=('Company', lambda x: '<br> • '.join(list(x)[:10]) + ('<br>   <i>...and more</i>' if len(x)>10 else ''))
    ).reset_index()
    
    color_map = {
        '< 8 LPA': '#8892B0',       # Muted Slate
        '8 - 12 LPA': '#3A86FF',    # Bright Blue
        '12 - 16 LPA': '#A020F0',   # Purple
        '16 - 25 LPA': '#F15BB5',   # Pink
        '25 - 40 LPA': '#FB5607',   # Orange
        '40+ LPA': '#00FF9D'        # Neon Green
    }
    
    fig = go.Figure()
    time_sort = valid_df[['Time_Label', 'SortKey']].drop_duplicates().sort_values('SortKey')
    full_time_labels = time_sort['Time_Label'].tolist()
    
    for bucket in labels:
        bucket_data = grouped[grouped['Bucket'] == bucket].copy()
        if not bucket_data.empty and bucket_data['Count'].sum() > 0:
            merged_time = pd.merge(time_sort, bucket_data, on=['Time_Label', 'SortKey'], how='left').fillna({'Count': 0, 'Company_List': 'No Companies'})
            
            fig.add_trace(go.Scatter(
                x=merged_time['Time_Label'],
                y=merged_time['Count'],
                mode='lines+markers',
                name=bucket,
                line=dict(color=color_map[bucket], width=3, shape='spline', smoothing=0.3),
                marker=dict(size=6),
                customdata=merged_time[['Company_List']],
                hovertemplate="<b>%{y} Companies</b><br>%{customdata[0]}<extra></extra>"
            ))
            
    fig.update_layout(
        title=title,
        xaxis_title="Placement Calendar",
        yaxis_title="Volume of OAs",
        plot_bgcolor='rgba(0,0,0,0)', paper_bgcolor='rgba(0,0,0,0)', font=dict(color='white'),
        xaxis=dict(categoryorder='array', categoryarray=full_time_labels, showgrid=False),
        yaxis=dict(showgrid=True, gridcolor='rgba(255,255,255,0.1)'),
        hovermode='x unified', # This is the magic line that slices through all buckets at once
        legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1),
        margin=dict(t=50, b=20, l=10, r=10)
    )
    return fig

# --- Statistical Bell Curve Generator ---
def build_bell_curve(df26, df27, val_col, title, color_26, color_27):
    fig = go.Figure()
    bin_size = 2
    
    valid_26 = df26[val_col].dropna() if not df26.empty and val_col in df26.columns else pd.Series()
    if not valid_26.empty:
        fig.add_trace(go.Histogram(
            x=valid_26, name="2026 Historical",
            marker_color=color_26, opacity=0.4,
            xbins=dict(start=0, end=max(valid_26)+5, size=bin_size),
            hovertemplate="Compensation: %{x} LPA<br>Companies: %{y}<extra></extra>"
        ))
        
        mu, sigma = valid_26.mean(), valid_26.std()
        if pd.notna(sigma) and sigma > 0:
            x_val = np.linspace(0, max(valid_26)+10, 100)
            y_val = (1 / (sigma * np.sqrt(2 * np.pi))) * np.exp(-0.5 * ((x_val - mu) / sigma)**2)
            y_scaled = y_val * len(valid_26) * bin_size
            fig.add_trace(go.Scatter(
                x=x_val, y=y_scaled, mode='lines', name="2026 Bell Curve",
                line=dict(color=color_26, width=3, dash='dot'), hoverinfo='skip'
            ))

    valid_27 = df27[val_col].dropna() if not df27.empty and val_col in df27.columns else pd.Series()
    if not valid_27.empty:
        fig.add_trace(go.Histogram(
            x=valid_27, name="2027 Live",
            marker_color=color_27, opacity=0.7,
            xbins=dict(start=0, end=max(valid_27)+5, size=bin_size),
            hovertemplate="Compensation: %{x} LPA<br>Companies: %{y}<extra></extra>"
        ))
        
        mu, sigma = valid_27.mean(), valid_27.std()
        if pd.notna(sigma) and sigma > 0:
            x_val = np.linspace(0, max(valid_27)+10, 100)
            y_val = (1 / (sigma * np.sqrt(2 * np.pi))) * np.exp(-0.5 * ((x_val - mu) / sigma)**2)
            y_scaled = y_val * len(valid_27) * bin_size
            fig.add_trace(go.Scatter(
                x=x_val, y=y_scaled, mode='lines', name="2027 Bell Curve",
                line=dict(color=color_27, width=4), hoverinfo='skip'
            ))

    fig.update_layout(
        title=title, barmode='overlay',
        xaxis_title=f"{val_col.replace('Parsed_', '')} (LPA)", yaxis_title="Frequency (Number of Companies)",
        plot_bgcolor='rgba(0,0,0,0)', paper_bgcolor='rgba(0,0,0,0)', font=dict(color='white'),
        legend=dict(yanchor="top", y=0.99, xanchor="right", x=0.99)
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

    tab1, tab2, tab3, tab4 = st.tabs(["🚀 Target Intel", "⏱️ Timeline Radar", "👻 Ghost List", "📈 Financial Trends & Bell Curves"])

    # --- TAB 1: Core Target Intel ---
    with tab1:
        st.subheader("Market X-Ray: Compare Target Offerings")
        
        df_27_unique = df_27.groupby('Norm_Company').first().reset_index()
        df_26_unique = df_26.groupby('Norm_Company').first().reset_index() if not df_26.empty else pd.DataFrame()
        merged_all = pd.merge(df_27_unique, df_26_unique, on='Norm_Company', how='left', suffixes=('_27', '_26'))
        
        merged_all['Parsed_CTC_26_Clean'] = merged_all['Parsed_CTC_26'].fillna(0)
        merged_all['Parsed_CTC_27_Clean'] = merged_all['Parsed_CTC_27'].fillna(0)
        merged_all['Delta'] = merged_all['Parsed_CTC_27_Clean'] - merged_all['Parsed_CTC_26_Clean']
        
        merged_all['Display_Name'] = merged_all['Company_27'].str.replace(r'\(.*?\)', '', regex=True).str.strip()
        merged_all = merged_all.sort_values('Delta', ascending=False)
        
        col_xray, col_delta = st.columns([1.2, 2])
        
        with col_xray:
            st.markdown("##### 🔍 Deep Target Intel")
            target_options = sorted(merged_all['Display_Name'].unique().tolist())
            
            default_target = next((c for c in ["Lam Research", "InMobi Groups", "InMobi"] if c in target_options), target_options[0] if target_options else None)
            selected_target_name = st.selectbox("Select Applied Company (2027)", target_options, index=target_options.index(default_target) if default_target else 0)
            
            if selected_target_name:
                row_selected = merged_all[merged_all['Display_Name'] == selected_target_name].iloc[0]
                
                ctc_26_disp = f"₹ {row_selected['Parsed_CTC_26']} LPA" if pd.notnull(row_selected['Parsed_CTC_26']) else "New Entry ('27)"
                base_26_disp = f"₹ {row_selected['Parsed_Base_26']} LPA" if pd.notnull(row_selected['Parsed_Base_26']) else "N/A"
                
                ctc_27_disp = f"₹ {row_selected['Parsed_CTC_27']} LPA" if pd.notnull(row_selected['Parsed_CTC_27']) else "N/A"
                base_27_disp = f"₹ {row_selected['Parsed_Base_27']} LPA" if pd.notnull(row_selected['Parsed_Base_27']) else "N/A"
                
                role_26_disp = row_selected.get('Role_26', 'N/A') if pd.notnull(row_selected.get('Role_26')) else "Did not visit"
                role_27_disp = row_selected.get('Role_27', 'N/A')
                
                gpa_26_disp = row_selected.get('GPA Cutoff_26', 'N/A') if pd.notnull(row_selected.get('GPA Cutoff_26')) else "N/A"
                gpa_27_disp = row_selected.get('GPA Cutoff_27', 'N/A') if pd.notnull(row_selected.get('GPA Cutoff_27')) else "N/A"
                
                note_26_disp = row_selected.get('Note_26', 'None') if pd.notnull(row_selected.get('Note_26')) else "None"
                note_27_disp = row_selected.get('Note_27', 'None') if pd.notnull(row_selected.get('Note_27')) else "None"

                st.markdown(f"""
                <div class="glass-card">
                    <div style="display:flex; justify-content:space-between; margin-bottom:15px;">
                        <div>
                            <div class="metric-label">2026 Historical</div>
                            <div class="metric-value" style="font-size:1.8rem; color:#8892B0;">{ctc_26_disp}</div>
                            <div class="metric-sub" style="font-size:1rem; color:#8892B0;">Base: {base_26_disp}</div>
                        </div>
                        <div style="text-align:right;">
                            <div class="metric-label">2027 Live</div>
                            <div class="metric-value" style="font-size:1.8rem; color:#636EFA;">{ctc_27_disp}</div>
                            <div class="metric-sub" style="font-size:1rem; color:#636EFA;">Base: {base_27_disp}</div>
                        </div>
                    </div>
                    <hr style="border-color: rgba(255,255,255,0.1);">
                    <div style="font-size:0.95rem; color:#E2E8F0;">
                        <p><b>🏢 Role Shift:</b> {role_26_disp} ➔ <span class="highlight-text">{role_27_disp}</span></p>
                        <p><b>🎓 GPA Cutoff:</b> {gpa_26_disp} ➔ <span class="highlight-text">{gpa_27_disp}</span></p>
                        <p><b>⚠️ 2026 Notes:</b> <i>{note_26_disp}</i></p>
                        <p><b>⚠️ 2027 Notes:</b> <i>{note_27_disp}</i></p>
                    </div>
                </div>
                """, unsafe_allow_html=True)
                
        with col_delta:
            st.markdown("##### 💸 YoY Total CTC Deltas (All 2027 Applied Companies)")
            
            for col in ['Parsed_Base_26', 'Parsed_CTC_26', 'Role_26', 'Parsed_Base_27', 'Parsed_CTC_27', 'Role_27']:
                merged_all[col] = merged_all[col].fillna("N/A")
            
            colors = []
            for idx, row in merged_all.iterrows():
                if row['Parsed_CTC_26'] == "N/A": colors.append('#00D2FF')
                elif row['Delta'] > 0: colors.append('#00FF9D')
                elif row['Delta'] < 0: colors.append('#FF4B4B')
                else: colors.append('#8892B0')
            
            fig_delta = go.Figure(data=[go.Bar(
                x=merged_all['Display_Name'], y=merged_all['Delta'], marker_color=colors, text=merged_all['Delta'], textposition='outside',
                customdata=merged_all[['Parsed_Base_26', 'Parsed_CTC_26', 'Role_26', 'Parsed_Base_27', 'Parsed_CTC_27', 'Role_27']],
                hovertemplate="<b>%{x}</b><br><br><b>Market Delta:</b> %{y} LPA<br><hr><b>2026 Baseline:</b><br>Role: %{customdata[2]}<br>Base: %{customdata[0]} LPA | CTC: %{customdata[1]} LPA<br><br><b>2027 Current:</b><br>Role: %{customdata[5]}<br>Base: %{customdata[3]} LPA | CTC: %{customdata[4]} LPA<extra></extra>"
            )])
            fig_delta.update_layout(plot_bgcolor='rgba(0,0,0,0)', paper_bgcolor='rgba(0,0,0,0)', font=dict(color='white'), margin=dict(l=0, r=0, t=30, b=0), height=420)
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
                st.dataframe(sanitize_for_arrow(week_df_26[['Company', 'Role', 'Parsed_CTC', 'GPA Cutoff', 'Note']] if not week_df_26.empty else pd.DataFrame()), use_container_width=True)
            with col_27:
                st.markdown(f"**2027 Companies ({selected_week_label})**")
                week_df_27 = valid_27[valid_27['Time_Label'] == selected_week_label] if not valid_27.empty else pd.DataFrame()
                st.dataframe(sanitize_for_arrow(week_df_27[['Company', 'Role', 'Parsed_CTC', 'GPA Cutoff', 'Note']] if not week_df_27.empty else pd.DataFrame()), use_container_width=True)

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
                    st.dataframe(sanitize_for_arrow(week_ghost_df[['Company', 'Role', 'Parsed_Base', 'Parsed_CTC', 'Source_Tier', 'GPA Cutoff']]), use_container_width=True)

            with ghost_tab2:
                cols_to_display = ['Company', 'Role', 'Parsed_Base', 'Parsed_CTC', 'Source_Tier', 'GPA Cutoff', 'OA Date']
                valid_cols = [c for c in cols_to_display if c in ghosts_df.columns]
                st.dataframe(sanitize_for_arrow(ghosts_df[valid_cols].sort_values('Parsed_CTC', ascending=False)), use_container_width=True)

    # --- TAB 4: Density Trend Lines & Bell Curves ---
    with tab4:
        st.subheader("📈 Salary Density Trends (Time vs. Compensation Volume)")
        st.markdown("This multi-line radar tracks precisely when different financial brackets test. Hover anywhere on the chart to instantly slice through all brackets for that specific week.")
        
        _, valid_heatmap_26 = get_timeline_grouping(df_26)
        
        col_line1, col_line2 = st.columns(2)
        
        with col_line1:
            st.markdown("<div class='glass-card'>", unsafe_allow_html=True)
            fig_ctc_line = build_density_line_chart(valid_heatmap_26, 'Parsed_CTC', "Total CTC Bracket Volumes by Week")
            st.plotly_chart(fig_ctc_line, use_container_width=True)
            st.markdown("</div>", unsafe_allow_html=True)
            
        with col_line2:
            st.markdown("<div class='glass-card'>", unsafe_allow_html=True)
            fig_base_line = build_density_line_chart(valid_heatmap_26, 'Parsed_Base', "Base Salary Bracket Volumes by Week")
            st.plotly_chart(fig_base_line, use_container_width=True)
            st.markdown("</div>", unsafe_allow_html=True)
            
        st.divider()
        
        st.subheader("🔔 The Market Bell Curve (Financial Spread)")
        st.markdown("This overlays a mathematical Gaussian distribution onto the raw histogram of compensation packages. It proves if the 'average' package is genuine or just skewed by a few massive outliers.")
        
        col_bell1, col_bell2 = st.columns(2)
        
        with col_bell1:
            st.markdown("<div class='glass-card'>", unsafe_allow_html=True)
            fig_ctc_bell = build_bell_curve(df_26, df_27, 'Parsed_CTC', "Total CTC Spread", '#8892B0', '#00FF9D')
            st.plotly_chart(fig_ctc_bell, use_container_width=True)
            st.markdown("</div>", unsafe_allow_html=True)
            
        with col_bell2:
            st.markdown("<div class='glass-card'>", unsafe_allow_html=True)
            fig_base_bell = build_bell_curve(df_26, df_27, 'Parsed_Base', "Base Salary Spread", '#8892B0', '#00FF9D')
            st.plotly_chart(fig_base_bell, use_container_width=True)
            st.markdown("</div>", unsafe_allow_html=True)

else:
    st.info("👈 Upload your 2027 Placements data in the sidebar to initialize the Intelligence Engine.")
"""INNEVA.E — 90-day energy overview using canonical historical columns."""
import pandas as pd
import plotly.express as px
import streamlit as st


def render_energy_overview(df):
    st.header('Energy Overview — Historical Dataset')
    st.caption('Canonical 37-column energy dataset. Default: latest 90 complete UTC days; no September-only SQLite energy source.')
    dates = df['hour_start_utc'].dt.date
    start, end = dates.min(), dates.max()
    selected = st.date_input('Select historical date range (UTC)', value=(start, end), min_value=start, max_value=end)
    if not isinstance(selected, (list, tuple)) or len(selected) != 2:
        st.info('Select both start and end dates.'); return
    a, b = selected
    if a > b:
        st.error('Start date must not be after end date.'); return
    view = df.loc[(df['hour_start_utc'] >= pd.Timestamp(a, tz='UTC')) & (df['hour_start_utc'] < pd.Timestamp(b, tz='UTC') + pd.Timedelta(days=1))].copy()
    if view.empty:
        st.warning('No observations in selected range.'); return
    renewables = view[['solar_mw','wind_onshore_mw','wind_offshore_mw']].sum(axis=1, min_count=3)
    cols = st.columns(5)
    cols[0].metric('Average demand', f"{view['actual_load_mw'].mean():,.0f} MW")
    cols[1].metric('Average solar', f"{view['solar_mw'].mean():,.0f} MW")
    cols[2].metric('Average wind', f"{(view['wind_onshore_mw'] + view['wind_offshore_mw']).mean():,.0f} MW")
    cols[3].metric('Average wholesale price', f"€{view['wholesale_price_eur_mwh'].mean():,.2f}/MWh")
    cols[4].metric('Hourly observations', f'{len(view):,}')
    st.caption(f"Missing offshore wind: {view['wind_offshore_mw'].isna().sum()} hours · Missing prices: {view['wholesale_price_eur_mwh'].isna().sum()} hours. Missing measurements are not treated as observed zero.")
    st.subheader('Electricity Demand')
    st.plotly_chart(px.line(view, x='hour_start_utc', y='actual_load_mw', labels={'hour_start_utc':'Hour (UTC)','actual_load_mw':'Demand (MW)'}), use_container_width=True)
    st.subheader('Renewable Generation')
    renew_long = view[['hour_start_utc','solar_mw','wind_onshore_mw','wind_offshore_mw']].melt('hour_start_utc', var_name='Source', value_name='Generation (MW)')
    st.plotly_chart(px.line(renew_long, x='hour_start_utc', y='Generation (MW)', color='Source'), use_container_width=True)
    st.subheader('Wholesale Price')
    st.plotly_chart(px.line(view, x='hour_start_utc', y='wholesale_price_eur_mwh', labels={'hour_start_utc':'Hour (UTC)','wholesale_price_eur_mwh':'EUR/MWh'}), use_container_width=True)
    st.subheader('Weather Conditions')
    weather = st.selectbox('Weather variable', ['temperature_c','wind_speed_ms','solar_radiation_wm2','cloud_cover_oktas','relative_humidity_pct','precipitation_mm','sunshine_hours','pressure_hpa'])
    st.plotly_chart(px.line(view, x='hour_start_utc', y=weather), use_container_width=True)
    with st.expander('Data quality and missing values'):
        st.dataframe(view.isna().sum().rename('missing_hours').to_frame(), use_container_width=True)
        st.write('Missingness flags in the canonical source:')
        st.dataframe(view[['actual_load_missing','solar_missing','wind_onshore_missing','wind_offshore_missing','price_missing']].sum().rename('flagged_hours').to_frame(), use_container_width=True)
    with st.expander('Canonical historical dataset (all 37 variables)'):
        st.dataframe(view, use_container_width=True, hide_index=True)
    st.download_button('Download selected 37-column dataset (CSV)', data=view.to_csv(index=False).encode('utf-8'), file_name=f'innevae_energy_{a}_{b}.csv', mime='text/csv')

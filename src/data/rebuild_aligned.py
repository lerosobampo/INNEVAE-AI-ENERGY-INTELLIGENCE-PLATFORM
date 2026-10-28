#!/usr/bin/env python3
"""Correct KNMI hour-end convention and rebuild hourly INNEVA.E outputs.
Requires original KNMI station archives and prior standardized energy/price CSVs.
No SQLite writes. Run from anywhere; paths are arguments.
"""
import argparse, json
from pathlib import Path
import pandas as pd

STATIONS=(215,240,260,280,290,310,370,380)
FEATURES=('temperature_c','wind_speed_ms','solar_radiation_wm2','cloud_cover_oktas','relative_humidity_pct','precipitation_mm','sunshine_hours','pressure_hpa')
START=pd.Timestamp('2024-01-01',tz='UTC')
END=pd.Timestamp('2026-10-01',tz='UTC')
HOURS=pd.date_range(START,END-pd.Timedelta(hours=1),freq='h',tz='UTC')

def read_knmi(path,station):
    with path.open(encoding='utf-8-sig') as fh:
        line_no,header=next((i,line) for i,line in enumerate(fh) if line.lstrip().startswith('# STN,'))
    names=[v.strip() for v in header.lstrip('# ').split(',')]
    d=pd.read_csv(path,skiprows=line_no+1,header=None,names=names,skipinitialspace=True,na_values=['',' '],low_memory=False)
    if not d.STN.eq(station).all(): raise ValueError(f'Station mismatch: {path}')
    if not d.HH.between(1,24).all(): raise ValueError(f'Bad KNMI HH: {path}')
    # KNMI HH=1 is 00:00-01:00 UTC: convert to interval START.
    d['hour_start_utc']=pd.to_datetime(d.YYYYMMDD.astype(str),format='%Y%m%d',utc=True)+pd.to_timedelta(d.HH-1,unit='h')
    d=d[(d.hour_start_utc>=START)&(d.hour_start_utc<END)].copy()
    d['station_id']=station
    d=d.rename(columns={'T':'temperature_c','FH':'wind_speed_ms','Q':'solar_radiation_wm2','N':'cloud_cover_oktas','U':'relative_humidity_pct','RH':'precipitation_mm','SQ':'sunshine_hours','P':'pressure_hpa'})
    for c in ('temperature_c','wind_speed_ms','precipitation_mm','sunshine_hours','pressure_hpa'):
        d[c]=pd.to_numeric(d[c],errors='coerce')/10
    d['solar_radiation_wm2']=pd.to_numeric(d.solar_radiation_wm2,errors='coerce')*10000/3600
    d['cloud_cover_oktas']=pd.to_numeric(d.cloud_cover_oktas,errors='coerce').replace(9,float('nan'))
    d['precipitation_mm']=d.precipitation_mm.clip(lower=0)
    d['sunshine_hours']=d.sunshine_hours.clip(lower=0)
    d=d[['hour_start_utc','station_id',*FEATURES]]
    if d.hour_start_utc.duplicated().any():raise ValueError(f'Duplicate KNMI hours: {station}')
    if len(d)!=len(HOURS) or not d.hour_start_utc.sort_values().reset_index(drop=True).equals(pd.Series(HOURS)):
        raise ValueError(f'KNMI coverage invalid for station {station}: {len(d)}')
    return d

def main():
    p=argparse.ArgumentParser()
    p.add_argument('--knmi-dir',type=Path,required=True)
    p.add_argument('--standardized-dir',type=Path,required=True)
    p.add_argument('--output-dir',type=Path,required=True)
    a=p.parse_args();a.output_dir.mkdir(parents=True,exist_ok=True)
    stations=pd.concat([read_knmi(a.knmi_dir/f'uurgeg_{s}_2021-2030.txt',s) for s in STATIONS],ignore_index=True).sort_values(['hour_start_utc','station_id'])
    stations['hour_end_utc']=stations.hour_start_utc+pd.Timedelta(hours=1)
    stations=stations[['hour_start_utc','hour_end_utc','station_id',*FEATURES]]
    stations.to_csv(a.output_dir/'weather_stations_hourly.csv',index=False)
    stations[stations.hour_start_utc>=END-pd.Timedelta(days=90)].to_csv(a.output_dir/'weather_stations_dev_90d.csv',index=False)
    national=stations.groupby('hour_start_utc')[list(FEATURES)].mean().reset_index()
    counts=stations.groupby('hour_start_utc')[list(FEATURES)].count()
    counts.columns=[f'{c}_station_count' for c in counts.columns]
    national=national.merge(counts.reset_index(),on='hour_start_utc',validate='one_to_one')
    national.insert(1,'station_count',len(STATIONS))
    national.insert(1,'hour_end_utc',national.hour_start_utc+pd.Timedelta(hours=1))
    national.to_csv(a.output_dir/'weather_hourly.csv',index=False)
    national.tail(2160).to_csv(a.output_dir/'weather_dev_90d.csv',index=False)
    master=pd.DataFrame({'hour_start_utc':HOURS,'hour_end_utc':HOURS+pd.Timedelta(hours=1)})
    report={'timestamp_conventions':{'KNMI':'YYYYMMDD + (HH-1) hours is hour start','energy':'validfrom (UTC) is hour start; no shift','prices':'Datetime (UTC) retained as source hour'},'expected_hours':len(HOURS),'weather_station_rows':len(stations)}
    for name in ('demand','solar','wind_onshore','wind_offshore','prices'):
        d=pd.read_csv(a.standardized_dir/f'{name}_hourly.csv')
        d.hour_start_utc=pd.to_datetime(d.hour_start_utc,utc=True)
        d.hour_end_utc=pd.to_datetime(d.hour_end_utc,utc=True)
        if len(d)!=len(HOURS) or d.hour_start_utc.duplicated().any():raise ValueError(f'Invalid rows {name}')
        if not (d.hour_end_utc-d.hour_start_utc).eq(pd.Timedelta(hours=1)).all():raise ValueError(f'Invalid intervals {name}')
        master=master.merge(d.drop(columns='hour_end_utc'),on='hour_start_utc',how='left',validate='one_to_one')
        d.to_csv(a.output_dir/f'{name}_hourly.csv',index=False)
        d.tail(2160).to_csv(a.output_dir/f'{name}_dev_90d.csv',index=False)
        report[f'{name}_missing']={c:int(d[c].sum()) for c in d if c.endswith('_missing')}
    master=master.merge(national.drop(columns='hour_end_utc'),on='hour_start_utc',how='left',validate='one_to_one')
    master['hour_of_day']=master.hour_start_utc.dt.hour
    master['day_of_week']=master.hour_start_utc.dt.dayofweek
    master['month']=master.hour_start_utc.dt.month
    master['is_weekend']=master.day_of_week>=5
    if len(master)!=24096 or master.hour_start_utc.duplicated().any() or not master.hour_start_utc.equals(pd.Series(HOURS)):
        raise ValueError('Master timeline failed')
    if master[list(FEATURES)].isna().any().any():raise ValueError('Missing national weather')
    # Verify first hour against original KNMI station 260 raw HH=1, 20240101: T=78 => 7.8C.
    check=stations[(stations.station_id==260)&(stations.hour_start_utc==START)].iloc[0]
    if abs(check.temperature_c-7.8)>1e-8:raise ValueError('KNMI source boundary check failed')
    master.to_csv(a.output_dir/'energy_intelligence_hourly.csv',index=False)
    master.tail(2160).to_csv(a.output_dir/'energy_intelligence_dev_90d.csv',index=False)
    report.update({'master_rows':len(master),'dev_rows':2160,'first_hour':str(master.hour_start_utc.min()),'last_hour':str(master.hour_start_utc.max()),'last_interval_end':str(master.hour_end_utc.max()),'national_weather_nulls':int(master[list(FEATURES)].isna().sum().sum()),'boundary_check_station_260_2024_01_01_00_temp_c':float(check.temperature_c),'status':'timestamp alignment verified against source interval conventions; remaining missing measurements retained'})
    (a.output_dir/'alignment_quality_report.json').write_text(json.dumps(report,indent=2))
    print(json.dumps(report,indent=2))
if __name__=='__main__':main()

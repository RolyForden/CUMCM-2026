"""Read-only paper audit. Run from repository root; no model execution."""
import io
import json
import zipfile
import urllib.request
from pathlib import Path

import numpy as np
import openpyxl
import pandas as pd


def rows(source, sheet=0):
    wb = openpyxl.load_workbook(source, read_only=True, data_only=True)
    ws = wb.worksheets[sheet] if isinstance(sheet, int) else wb[sheet]
    result = list(ws.values)
    wb.close()
    return result


def main():
    out = {}
    archive = Path('tmp/paper_review/official_problems.zip')
    archive.parent.mkdir(parents=True, exist_ok=True)
    if not archive.exists():
        urllib.request.urlretrieve('https://www.mcm.edu.cn/upload_cn/CUMCM2026Problems.zip', archive)
    with zipfile.ZipFile('tmp/paper_review/official_problems.zip') as z:
        files = [n for n in z.namelist() if n.startswith('C') and n.endswith('.xlsx')]
        comparisons = []
        for i in range(1, 5):
            name = next(n for n in files if n.endswith(f'{i}.xlsx') and 'result' not in n)
            official = rows(io.BytesIO(z.read(name)))
            local = rows(f'data/raw/official/附件{i}.xlsm', 2)
            same = sum(a == b for a, b in zip(official, local))
            comparisons.append({'attachment': i, 'official_rows': len(official),
                                'local_rows': len(local), 'equal_rows': same})
        n = next(n for n in files if n.endswith('2.xlsx') and 'result' not in n)
        a = np.array([r[1:145] for r in rows(io.BytesIO(z.read(n)), 1)[1:]], float)
        b = np.array([r[1:145] for r in rows('data/raw/substitute/附件2.xlsx', '光伏发电实际功率')[1:]], float)
        out['official_pv_comparison'] = {'cells': int(a.size), 'max_abs_error': float(np.max(abs(a-b)))}
        out['official_local_comparison'] = comparisons
        out['official_attachment2_sheets'] = openpyxl.load_workbook(io.BytesIO(z.read(n)), read_only=True).sheetnames
    checks = {}
    raw_load = {str(r[0])[:10]: np.array(r[1:145], float)/6 for r in rows('data/raw/official/附件2.xlsm', 2)[1:]}
    raw_pv = {str(r[0])[:10]: np.array(r[1:145], float)/6 for r in rows('data/raw/substitute/附件2.xlsx', '光伏发电实际功率')[1:]}
    raw_price = {str(r[0])[:10]: np.array(r[1:145], float) for r in rows('data/raw/official/附件4.xlsm', 2)[1:]}
    fixed_price = np.array([r[1] for r in rows('data/raw/official/附件1.xlsm', 2)[1:]], float)
    for key, folder in [('q2','q2'), ('q3','q3'), ('q4_2','q4'), ('q4_3','q4')]:
        d = pd.read_csv(f'outputs/{folder}/{key}_dispatch.csv')
        c = 'charge_actual' if 'charge_actual' in d else 'charge'
        r = 'discharge_actual' if 'discharge_actual' in d else 'discharge'
        checks[key] = {'rows': len(d), 'days': int(d.date.nunique()),
            'max_soc_adjacent_gap': float(np.max(abs(d.soc_start.to_numpy()[1:]-d.soc_end.to_numpy()[:-1]))),
            'max_soc_equation_error': float(np.max(abs(d.soc_end-d.soc_start-.9*d[c]+d[r]/.9))),
            'soc_min': float(min(d.soc_start.min(),d.soc_end.min())),
            'soc_max': float(max(d.soc_start.max(),d.soc_end.max())),
            'simultaneous_charge_discharge_rows': int(((d[c]>1e-6)&(d[r]>1e-6)).sum())}
        midnight = d[d.slot == 143]
        shift = abs(midnight.soc_end-midnight.soc_start)
        worst = midnight.loc[shift.idxmax()]
        checks[key]['midnight_export'] = {
            'max_24h_vs_24h10_difference_kwh': float(shift.max()),
            'affected_days': int((shift>1e-6).sum()),
            'worst_date': str(worst.date),
            'wall_clock_24h_soc': float(worst.soc_start),
            'exported_24h10_soc': float(worst.soc_end)}
        load = np.array([raw_load[x.date][x.slot] for x in d.itertuples()])
        pv = np.array([raw_pv[x.date][x.slot] for x in d.itertuples()])
        price = np.array([raw_price[x.date][x.slot] if key.startswith('q4') else fixed_price[x.slot] for x in d.itertuples()])
        contract = d['final_contract' if 'final_contract' in d else 'grid_contract'].to_numpy()
        expected_emergency = np.maximum(load+d[c].to_numpy()-d[r].to_numpy()-pv-contract, 0)
        checks[key]['max_emergency_reconstruction_error'] = float(np.max(abs(expected_emergency-d.grid_emergency)))
        if 'load_actual' in d:
            checks[key]['max_raw_load_error'] = float(np.max(abs(load-d.load_actual)))
            checks[key]['max_raw_pv_error'] = float(np.max(abs(pv-d.pv_available)))
        if key in ('q2', 'q4_2'):
            cost = float(np.sum(price*(contract+5*d.grid_emergency)))
            daily = pd.read_csv(f'outputs/{folder}/{key}_daily_summary.csv')
            checks[key]['independent_total_cost'] = cost
            checks[key]['cost_difference_vs_daily'] = cost-float(daily.cost_total.sum())
    out['soc_checks'] = checks
    d = pd.read_csv('outputs/q2/q2_daily_summary.csv')
    out['q2_stats'] = {c: float(d[c].sum()) for c in ['cost_total','cost_normal','cost_emergency','grid_emergency_kwh','charge_shortfall_kwh','discharge_shortfall_kwh']}
    out['q2_stats'].update({f'soc_end_{stat}': float(getattr(d.actual_soc_end,stat)()) for stat in ['min','max','median']})
    out['support_missing_pv_dependency'] = not Path('支撑材料/data/raw/substitute/附件2.xlsx').exists() and not list(Path('支撑材料').rglob('附件2.xlsx'))
    target = Path('research/C_paper_review_evidence.json')
    target.write_text(json.dumps(out, ensure_ascii=False, indent=2), encoding='utf-8')
    print(target.read_text(encoding='utf-8'))


if __name__ == '__main__':
    main()

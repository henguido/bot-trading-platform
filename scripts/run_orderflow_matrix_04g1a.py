from __future__ import annotations
import json,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path: sys.path.insert(0,str(ROOT))
from backend.economia.auditoria_orderflow_matrix_04g1a import auditar_matrix_04g1a
OUT=ROOT/'artifacts'/'orderflow-fixed-matrix-04g1a.json'
def main():
    print('[04G-1a] start fixed OF matrix audit; ML=False FUTURE=False PNL=False 2026_OPEN=False')
    r=auditar_matrix_04g1a(); OUT.parent.mkdir(parents=True,exist_ok=True); OUT.write_text(json.dumps(r,indent=2,sort_keys=True),encoding='utf-8')
    print(f"[04G-1a] status={r['status']} listings={r['pair_listings_complete']}/{r['pair_listings_expected']} files={r['downloaded_files']} rows={r['downloaded_rows']} errors={r['content_error_files']}")
    print(f"[04G-1a] days={r['usable_days']}/{r['feature_days']} fraction={r['usable_days_fraction']} complete_min={r['complete_bases_min']} complete_max={r['complete_bases_max']} years={r['usable_fraction_by_year']}")
    print(f"[04G-1a] reasons={','.join(r['reasons']) if r['reasons'] else 'NONE'} artifact={OUT}")
if __name__=='__main__': main()

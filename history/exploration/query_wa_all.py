"""Fetch all WA NVCL boreholes and save them as CSV"""
import csv, sys, io
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

from nvcl_kit.reader import NVCLReader
from nvcl_kit.param_builder import param_builder

param = param_builder('wa', max_boreholes=0)  # 0 = all
reader = NVCLReader(param)
if not reader.wfs:
    raise SystemExit('NVCLReader initialization failed')

bh_list = reader.get_feature_list()
print(f"Total WA boreholes:  {len(bh_list)}")

with open('wa_boreholes.csv', 'w', newline='', encoding='utf-8-sig') as f:
    w = csv.writer(f)
    w.writerow(['name', 'nvcl_id', 'lon', 'lat', 'boreholeLength_m',
                'drillStartDate', 'operator', 'tenement', 'identifier'])
    for bh in bh_list:
        w.writerow([getattr(bh, 'name', ''), getattr(bh, 'nvcl_id', ''),
                    getattr(bh, 'x', ''), getattr(bh, 'y', ''),
                    getattr(bh, 'boreholeLength_m', ''),
                    getattr(bh, 'drillStartDate', ''),
                    getattr(bh, 'operator', ''), getattr(bh, 'tenement', ''),
                    getattr(bh, 'identifier', '')])
print('Saved wa_boreholes.csv')

for bh in bh_list[:10]:
    print(f"{bh.name:18s} lon={bh.x} lat={bh.y} len={bh.boreholeLength_m}m")

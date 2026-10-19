"""Query the Western Australian NVCL borehole catalog"""
from nvcl_kit.reader import NVCLReader
from nvcl_kit.param_builder import param_builder

MAX_BH = 50  # Start with 50 boreholes; 0 selects all.

param = param_builder('wa', max_boreholes=MAX_BH)
if not param:
    raise SystemExit('param_builder failed')

reader = NVCLReader(param)
if not reader.wfs:
    raise SystemExit('NVCLReader initialization failed: WFS connection failed')

bh_list = reader.get_feature_list()
print(f"Fetched  {len(bh_list)}  boreholes\n")

# Print field names from the first borehole.
if bh_list:
    print('Available fields:', ", ".join(vars(bh_list[0]).keys()), "\n")

for i, bh in enumerate(bh_list):
    name = getattr(bh, 'name', '?')
    # Common GeoSciML BoreholeView fields
    lat = getattr(bh, 'latitude', None) or getattr(bh, 'lat', '?')
    lon = getattr(bh, 'longitude', None) or getattr(bh, 'lon', '?')
    nvcl = getattr(bh, 'nvcl_collection', '?')
    print(f"{i+1:3d}. {name:20s} lat={lat} lon={lon} nvcl={nvcl}")

# NVCL ID list
ids = reader.get_nvcl_id_list()
print(f"\nBoreholes with NVCL data:  {len(ids)}")
print('First 10 NVCL IDs:', ids[:10])

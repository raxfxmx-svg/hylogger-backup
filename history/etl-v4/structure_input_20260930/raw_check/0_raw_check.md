# Raw input precheck

Source: `D:\100demo\data\raw`

Checks manifests, file existence, and sizes only; payload hashes, business content, and database import are outside this precheck

101 boreholes and 106 datasets; elapsed: 4.027 seconds.

- Single dataset: steps 1–10, then steps 20–29 as needed: 95 boreholes (`single_holes.txt`)
- Multiple datasets: run steps 31–35 separately after checking source evidence and the source release: 3 boreholes (`multi_holes.txt`)
- Resolve alerts or empty categories before selecting subsequent steps: 3 boreholes (`attention_holes.txt`)

The precheck only classifies inputs; it does not move files or start later stages. In this snapshot, steps 1–6 and 31–35 still read raw packages under etl4. Prepare the selected source directories before running them.

Boreholes with an entirely missing category are listed as pending. This does not imply source corruption or support for empty categories in subsequent steps.

## Boreholes with multiple datasets

| Borehole ID | Dataset count | Dataset names and IDs | Status |
|---|---:|---|---|
| 12CADD001 | 2 | 12CADD001 (0bf137d9-7fd7-4bf4-aa33-8130465ae4e); 12CADD001_wedge (43057f8c-4268-40ef-aa3d-90aa56f13d1) | passed |
| 14KDD001 | 2 | 14KDD001_wedge (c10744cc-2e42-478a-8bc3-7cea1059044); 14KDD001 (eb0c6c07-1957-421a-b974-47d8a30aa7a) | passed |
| 15EIS001 | 4 | 15EIS001 (443bd630-f6df-4f32-8e5c-0a756c9a56f); 15EIS001_wedge3 (56d5fe91-626f-48ad-8786-acf91fe83a5); 15EIS001_wedge2 (c83afeab-5697-4476-b24a-e210af12137); 15EIS001_wedge (ea2aad6e-6b09-4086-ab88-2d49b09459d) | passed |

## Missing data and alerts

### 05GJD001 (1 datasets)

- Notice: Profilometer data unavailable: Marked unavailable by the source; handle separately before using the current complete-data workflow

### 19AFRD2003 (1 datasets)

- Alert: missing  package_manifest.json
- Alert: missing  profilometer_manifest.json
- Alert: missing  image_logs_by_dataset.json
- Alert: missing  images_manifest.json
- Alert: missing  tray_depths.json
- Alert: Found an incomplete .part download: D:\100demo\data\raw\19AFRD2003\profilometer\853d3273-5402-487d-b9e4-da617608123_Profile_log.jsonl.part
- Notice: Image data unavailable: Category directory is empty or missing; handle separately before using the current complete-data workflow

### 19AFRD2004 (1 datasets)

- Alert: missing  package_manifest.json
- Alert: missing  spectral_manifest.json
- Alert: missing  profilometer_manifest.json
- Alert: missing  image_logs_by_dataset.json
- Alert: missing  images_manifest.json
- Alert: missing  tray_depths.json
- Alert: The file is not listed as a provided payload: D:\100demo\data\raw\19AFRD2004\spectral\02a14176-725d-4787-bbad-ac0423ede5c_Reflectance.f32
- Alert: Found an incomplete .part download: D:\100demo\data\raw\19AFRD2004\spectral\9217e6e2-77e2-457d-b360-ef977abb5ad_Base_Refl.f32.part
- Notice: Profilometer data unavailable: Category directory is empty or missing; handle separately before using the current complete-data workflow
- Notice: Image data unavailable: Category directory is empty or missing; handle separately before using the current complete-data workflow

## Classification of all boreholes

| Borehole ID | Dataset count | Scalar files | Spectral files | Profilometer files | Image files | Next steps |
|---|---:|---:|---:|---:|---:|---|
| 05GJD001 | 1 | 125 | 2 | 0 | 33 | Resolve alerts or empty categories before selecting subsequent steps |
| 05KCD001 | 1 | 127 | 2 | 1 | 30 | Single dataset: steps 1–10, then steps 20–29 as needed |
| 07THD002 | 1 | 107 | 2 | 1 | 77 | Single dataset: steps 1–10, then steps 20–29 as needed |
| 07THD003 | 1 | 107 | 2 | 1 | 36 | Single dataset: steps 1–10, then steps 20–29 as needed |
| 09ATD015 | 1 | 78 | 1 | 1 | 72 | Single dataset: steps 1–10, then steps 20–29 as needed |
| 09ATD019 | 1 | 78 | 1 | 1 | 34 | Single dataset: steps 1–10, then steps 20–29 as needed |
| 09ATRCD025 | 1 | 82 | 1 | 1 | 34 | Single dataset: steps 1–10, then steps 20–29 as needed |
| 09DKRCD001A | 1 | 129 | 2 | 1 | 64 | Single dataset: steps 1–10, then steps 20–29 as needed |
| 09DKRCD002 | 1 | 105 | 2 | 1 | 68 | Single dataset: steps 1–10, then steps 20–29 as needed |
| 09FKRCD001 | 1 | 128 | 2 | 1 | 42 | Single dataset: steps 1–10, then steps 20–29 as needed |
| 09HBRCD001 | 1 | 133 | 2 | 1 | 76 | Single dataset: steps 1–10, then steps 20–29 as needed |
| 09RTD001 | 1 | 75 | 1 | 1 | 57 | Single dataset: steps 1–10, then steps 20–29 as needed |
| 09THD028 | 1 | 110 | 2 | 1 | 80 | Single dataset: steps 1–10, then steps 20–29 as needed |
| 09THD029 | 1 | 110 | 2 | 1 | 86 | Single dataset: steps 1–10, then steps 20–29 as needed |
| 09THD030 | 1 | 109 | 2 | 1 | 55 | Single dataset: steps 1–10, then steps 20–29 as needed |
| 09THD031 | 1 | 109 | 2 | 1 | 70 | Single dataset: steps 1–10, then steps 20–29 as needed |
| 09THD032 | 1 | 109 | 2 | 1 | 100 | Single dataset: steps 1–10, then steps 20–29 as needed |
| 09THD033 | 1 | 110 | 2 | 1 | 130 | Single dataset: steps 1–10, then steps 20–29 as needed |
| 10CHD006 | 1 | 128 | 2 | 1 | 37 | Single dataset: steps 1–10, then steps 20–29 as needed |
| 10CHRCD005 | 1 | 116 | 2 | 1 | 31 | Single dataset: steps 1–10, then steps 20–29 as needed |
| 10KRD04 | 1 | 124 | 2 | 1 | 42 | Single dataset: steps 1–10, then steps 20–29 as needed |
| 10KRD06 | 1 | 124 | 2 | 1 | 54 | Single dataset: steps 1–10, then steps 20–29 as needed |
| 10LAD009 | 1 | 131 | 2 | 1 | 46 | Single dataset: steps 1–10, then steps 20–29 as needed |
| 10TJD001 | 1 | 105 | 2 | 1 | 66 | Single dataset: steps 1–10, then steps 20–29 as needed |
| 11SAVD003 | 1 | 133 | 2 | 1 | 154 | Single dataset: steps 1–10, then steps 20–29 as needed |
| 12AMD0015 | 1 | 124 | 2 | 1 | 111 | Single dataset: steps 1–10, then steps 20–29 as needed |
| 12BRDDH001 | 1 | 107 | 2 | 1 | 24 | Single dataset: steps 1–10, then steps 20–29 as needed |
| 12BRDDH002 | 1 | 108 | 2 | 1 | 33 | Single dataset: steps 1–10, then steps 20–29 as needed |
| 12BRDDH003 | 1 | 108 | 2 | 1 | 19 | Single dataset: steps 1–10, then steps 20–29 as needed |
| 12BRDDH004 | 1 | 107 | 2 | 1 | 34 | Single dataset: steps 1–10, then steps 20–29 as needed |
| 12CADD001 | 2 | 262 | 4 | 2 | 151 | Multiple datasets: run steps 31–35 separately after checking source evidence and the source release |
| 12CADD002 | 1 | 137 | 2 | 1 | 45 | Single dataset: steps 1–10, then steps 20–29 as needed |
| 12DHDD0001 | 1 | 135 | 2 | 1 | 79 | Single dataset: steps 1–10, then steps 20–29 as needed |
| 12DHDD0002 | 1 | 136 | 2 | 1 | 84 | Single dataset: steps 1–10, then steps 20–29 as needed |
| 12GMSD001 | 1 | 107 | 2 | 1 | 258 | Single dataset: steps 1–10, then steps 20–29 as needed |
| 13AHDD005 | 1 | 107 | 2 | 1 | 42 | Single dataset: steps 1–10, then steps 20–29 as needed |
| 13CGDD001 | 1 | 107 | 2 | 1 | 80 | Single dataset: steps 1–10, then steps 20–29 as needed |
| 13TRDD012 | 1 | 108 | 2 | 1 | 194 | Single dataset: steps 1–10, then steps 20–29 as needed |
| 13TRDD013 | 1 | 110 | 2 | 1 | 75 | Single dataset: steps 1–10, then steps 20–29 as needed |
| 13TRDD014 | 1 | 109 | 2 | 1 | 177 | Single dataset: steps 1–10, then steps 20–29 as needed |
| 14AMD0043 | 1 | 129 | 2 | 1 | 48 | Single dataset: steps 1–10, then steps 20–29 as needed |
| 14CADD001 | 1 | 137 | 2 | 1 | 62 | Single dataset: steps 1–10, then steps 20–29 as needed |
| 14CADD002 | 1 | 132 | 2 | 1 | 52 | Single dataset: steps 1–10, then steps 20–29 as needed |
| 14CADD003 | 1 | 124 | 2 | 1 | 3 | Single dataset: steps 1–10, then steps 20–29 as needed |
| 14KDD001 | 2 | 214 | 4 | 2 | 29 | Multiple datasets: run steps 31–35 separately after checking source evidence and the source release |
| 15BRDD001 | 1 | 122 | 2 | 1 | 105 | Single dataset: steps 1–10, then steps 20–29 as needed |
| 15BRDD002 | 1 | 107 | 2 | 1 | 85 | Single dataset: steps 1–10, then steps 20–29 as needed |
| 15BRDD003 | 1 | 107 | 2 | 1 | 113 | Single dataset: steps 1–10, then steps 20–29 as needed |
| 15EIS001 | 4 | 493 | 8 | 4 | 516 | Multiple datasets: run steps 31–35 separately after checking source evidence and the source release |
| 15RCDVZ001 | 1 | 186 | 2 | 1 | 97 | Single dataset: steps 1–10, then steps 20–29 as needed |
| 15SYDD0003B | 1 | 128 | 2 | 1 | 105 | Single dataset: steps 1–10, then steps 20–29 as needed |
| 15SYDD0004 | 1 | 126 | 2 | 1 | 162 | Single dataset: steps 1–10, then steps 20–29 as needed |
| 16CADD001 | 1 | 179 | 2 | 1 | 161 | Single dataset: steps 1–10, then steps 20–29 as needed |
| 16CADD002 | 1 | 170 | 2 | 1 | 209 | Single dataset: steps 1–10, then steps 20–29 as needed |
| 16MYD0047 | 1 | 166 | 2 | 1 | 126 | Single dataset: steps 1–10, then steps 20–29 as needed |
| 16MYD0052 | 1 | 167 | 2 | 1 | 89 | Single dataset: steps 1–10, then steps 20–29 as needed |
| 16MYD0058 | 1 | 167 | 2 | 1 | 74 | Single dataset: steps 1–10, then steps 20–29 as needed |
| 16SHDD10 | 1 | 113 | 2 | 1 | 143 | Single dataset: steps 1–10, then steps 20–29 as needed |
| 17BBDD002 | 1 | 110 | 2 | 1 | 134 | Single dataset: steps 1–10, then steps 20–29 as needed |
| 17BBDD004 | 1 | 81 | 2 | 1 | 150 | Single dataset: steps 1–10, then steps 20–29 as needed |
| 17DD003 | 1 | 197 | 2 | 1 | 73 | Single dataset: steps 1–10, then steps 20–29 as needed |
| 17DHDD0016 | 1 | 177 | 2 | 1 | 83 | Single dataset: steps 1–10, then steps 20–29 as needed |
| 17DTDD0001 | 1 | 110 | 2 | 1 | 61 | Single dataset: steps 1–10, then steps 20–29 as needed |
| 17FCHRCD001 | 1 | 110 | 2 | 1 | 118 | Single dataset: steps 1–10, then steps 20–29 as needed |
| 17FCHRCD002 | 1 | 110 | 2 | 1 | 168 | Single dataset: steps 1–10, then steps 20–29 as needed |
| 17MNDD0001 | 1 | 120 | 2 | 1 | 49 | Single dataset: steps 1–10, then steps 20–29 as needed |
| 17MVDD001 | 1 | 110 | 2 | 1 | 40 | Single dataset: steps 1–10, then steps 20–29 as needed |
| 17MVDD002 | 1 | 110 | 2 | 1 | 17 | Single dataset: steps 1–10, then steps 20–29 as needed |
| 17MVDD003 | 1 | 110 | 2 | 1 | 38 | Single dataset: steps 1–10, then steps 20–29 as needed |
| 17MVDD004 | 1 | 109 | 2 | 1 | 57 | Single dataset: steps 1–10, then steps 20–29 as needed |
| 17MVRCD008 | 1 | 109 | 2 | 1 | 16 | Single dataset: steps 1–10, then steps 20–29 as needed |
| 17MVRCD018 | 1 | 109 | 2 | 1 | 14 | Single dataset: steps 1–10, then steps 20–29 as needed |
| 17NNMD001 | 1 | 186 | 2 | 1 | 114 | Single dataset: steps 1–10, then steps 20–29 as needed |
| 17SRDD0004 | 1 | 161 | 2 | 1 | 52 | Single dataset: steps 1–10, then steps 20–29 as needed |
| 17SRDD0010 | 1 | 109 | 2 | 1 | 49 | Single dataset: steps 1–10, then steps 20–29 as needed |
| 17SRDD0011 | 1 | 110 | 2 | 1 | 49 | Single dataset: steps 1–10, then steps 20–29 as needed |
| 18ABAD01 | 1 | 126 | 2 | 1 | 427 | Single dataset: steps 1–10, then steps 20–29 as needed |
| 18ABAD02 | 1 | 110 | 2 | 1 | 274 | Single dataset: steps 1–10, then steps 20–29 as needed |
| 18AFRD002 | 1 | 136 | 2 | 1 | 147 | Single dataset: steps 1–10, then steps 20–29 as needed |
| 18EISD001 | 1 | 80 | 2 | 1 | 316 | Single dataset: steps 1–10, then steps 20–29 as needed |
| 18EMRCD001 | 1 | 110 | 2 | 1 | 118 | Single dataset: steps 1–10, then steps 20–29 as needed |
| 18GSCRCD0001 | 1 | 79 | 2 | 1 | 53 | Single dataset: steps 1–10, then steps 20–29 as needed |
| 18GSCRCD0002 | 1 | 80 | 2 | 1 | 56 | Single dataset: steps 1–10, then steps 20–29 as needed |
| 18GSLARCD0003 | 1 | 79 | 2 | 1 | 9 | Single dataset: steps 1–10, then steps 20–29 as needed |
| 18JBDD001 | 1 | 192 | 2 | 1 | 67 | Single dataset: steps 1–10, then steps 20–29 as needed |
| 18JBDD002 | 1 | 191 | 2 | 1 | 91 | Single dataset: steps 1–10, then steps 20–29 as needed |
| 18KLDD007 | 1 | 109 | 2 | 1 | 103 | Single dataset: steps 1–10, then steps 20–29 as needed |
| 18KLDD008 | 1 | 109 | 2 | 1 | 87 | Single dataset: steps 1–10, then steps 20–29 as needed |
| 18KLDD010 | 1 | 110 | 2 | 1 | 66 | Single dataset: steps 1–10, then steps 20–29 as needed |
| 18LCDD0001 | 1 | 130 | 2 | 1 | 226 | Single dataset: steps 1–10, then steps 20–29 as needed |
| 18MBDD001 | 1 | 79 | 2 | 1 | 80 | Single dataset: steps 1–10, then steps 20–29 as needed |
| 18MMDD0434 | 1 | 285 | 2 | 1 | 450 | Single dataset: steps 1–10, then steps 20–29 as needed |
| 18QMDD001 | 1 | 79 | 2 | 1 | 107 | Single dataset: steps 1–10, then steps 20–29 as needed |
| 18QMDD002 | 1 | 79 | 2 | 1 | 142 | Single dataset: steps 1–10, then steps 20–29 as needed |
| 18SFDD001 | 1 | 79 | 2 | 1 | 75 | Single dataset: steps 1–10, then steps 20–29 as needed |
| 19AFDD1009 | 1 | 79 | 2 | 1 | 87 | Single dataset: steps 1–10, then steps 20–29 as needed |
| 19AFRD2003 | 1 | 110 | 2 | 1 | 0 | Resolve alerts or empty categories before selecting subsequent steps |
| 19AFRD2004 | 1 | 110 | 2 | 0 | 0 | Resolve alerts or empty categories before selecting subsequent steps |
| 19EISD002 | 1 | 79 | 2 | 1 | 111 | Single dataset: steps 1–10, then steps 20–29 as needed |
| 19EISD003 | 1 | 79 | 2 | 1 | 111 | Single dataset: steps 1–10, then steps 20–29 as needed |
| 19EISD004 | 1 | 79 | 2 | 1 | 121 | Single dataset: steps 1–10, then steps 20–29 as needed |

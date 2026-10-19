from pathlib import Path
import csv, json
p=Path(r"C:\path\to\project\29\SM_05KCD001.csv")
rows=list(csv.reader(p.open(encoding="utf-8-sig",newline="")))
h=rows[16]; data=rows[17:]
out=[]
for start in range(60,201,10):
    chunk=[r for r in data if r and start <= float(r[0]) < min(start+10,202)]
    rec={"a":start,"b":min(start+10,202)}
    for tag, suffix in [("swir","System_SWIR)"),("tir","System_TIR)")]:
        cols=[(i,n.split("_(")[0]) for i,n in enumerate(h) if n.endswith(suffix) and not n.lower().startswith("invalid")]
        scores=[]
        for i,n in cols:
            vals=[]
            for r in chunk:
                try: vals.append(float(r[i]))
                except: vals.append(0)
            scores.append((sum(vals)/max(len(chunk),1),n))
        rec[tag]=max(scores)[1]
    out.append(rec)
print(json.dumps(out,ensure_ascii=False))

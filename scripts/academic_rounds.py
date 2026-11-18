"""Academic evidence: three RSS collection rounds. No fake claims of new live news."""
import argparse
import json
import time
from radar import store
from radar.pipeline import collect

p=argparse.ArgumentParser()
p.add_argument('--interval',type=int,default=600,help='Seconds between rounds. Use 2 only for an accelerated classroom demo.')
a=p.parse_args()
store.init()
results=[]
for i in range(3):
    result=collect(enable_ai=True)
    print(f'Ronda {i+1}/3: '+json.dumps(result,ensure_ascii=False))
    results.append(result)
    if i<2:time.sleep(max(0,a.interval))
with open('docs/rondas_academicas.json','w',encoding='utf-8') as f:json.dump(results,f,ensure_ascii=False,indent=2)
print('Guardado docs/rondas_academicas.json')

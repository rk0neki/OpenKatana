"""Check graffiti timing/state independently of the full pixel comparison."""
import argparse
import json
from pathlib import Path
from PIL import Image,ImageChops
from openkatana.render import write_json


def main():
    p=argparse.ArgumentParser();p.add_argument('--project',type=Path,required=True)
    p.add_argument('--result-name',default='openkatana');p.add_argument('--out',type=Path,required=True);args=p.parse_args()
    cases={c['name']:c for c in json.loads((args.project/'cases.json').read_text(encoding='utf-8'))}
    def image(folder,case,offset):
        return Image.open(args.project/folder/'frames'/f"{cases[case]['f0']+offset:05d}.png").convert('RGB')
    def same(folder,case,a,b):return ImageChops.difference(image(folder,case,a),image(folder,case,b)).getbbox() is None
    observations=[]
    for folder in ('comp',args.result_name):
        checks={'hold_stable':same(folder,'hold',0,47),
                'write_changes':not same(folder,'write',0,24),
                'slam_changes':not same(folder,'slam',0,3),
                'keys_wait_before_start':same(folder,'letter-keys',0,2),
                'keys_start_on_schedule':not same(folder,'letter-keys',2,3),
                'colors_change_output':ImageChops.difference(image(folder,'hold',24),image(folder,'colors',24)).getbbox() is not None,
                'all_glyphs_render':all(ImageChops.difference(image(folder,name,24),Image.open(args.project/'plates/A/00000.png').convert('RGB')).getbbox() is not None for name in ('alphabet','digits'))}
        observations.append({'renderer':folder,'checks':checks})
    result={'passed':all(all(r['checks'].values()) for r in observations),'pixel_parity':None,
            'scope':'Timing/state smoke checks only; review rendered artwork separately', 'observations':observations}
    args.out.mkdir(parents=True,exist_ok=False);write_json(args.out/'result.json',result);print(json.dumps(result,indent=2))
    if not result['passed']:raise SystemExit(1)


if __name__=='__main__':main()

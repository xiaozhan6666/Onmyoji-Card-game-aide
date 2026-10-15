"""Offline OCR calibration for the observed 1920x1080 MuMu board/profile layout."""
import argparse
import json
import os
from pathlib import Path


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('image', type=Path)
    parser.add_argument('--kind', choices=['board','profile','nickname'], required=True)
    parser.add_argument('--center-y',type=int,default=412)
    args=parser.parse_args()
    root=Path(__file__).resolve().parents[1]
    os.environ['PADDLE_PDX_DISABLE_MODEL_SOURCE_CHECK']='True'
    os.environ['PADDLE_PDX_CACHE_HOME']=str(root/'.cache/paddlex')
    for key in ('OMP_NUM_THREADS','MKL_NUM_THREADS','OPENBLAS_NUM_THREADS'): os.environ[key]='2'
    from paddleocr import PaddleOCR
    from bwp_collector.ocr import normalize_result
    from bwp_collector.imaging import read_image,crop,preprocess
    from bwp_collector.live_profile import profile_anchor
    models=root/'.cache/paddlex/official_models'
    engine=PaddleOCR(device='cpu',cpu_threads=2,text_detection_model_name='PP-OCRv5_mobile_det',
        text_recognition_model_name='PP-OCRv5_mobile_rec',text_detection_model_dir=str(models/'PP-OCRv5_mobile_det'),
        text_recognition_model_dir=str(models/'PP-OCRv5_mobile_rec'),use_doc_orientation_classify=False,
        use_doc_unwarping=False,use_textline_orientation=False,text_rec_score_thresh=0.0)
    image=read_image(args.image)
    if image.shape[:2] != (1080,1920): raise ValueError('Unexpected dimensions')
    boxes={'id':[1280,270,1444,309],'grade':[990,348,1295,400], 'name':[980,308,1400,351], 'buttons':[780,493,1395,577]} if args.kind=='profile' else {
        'title':[110,599,256,652], 'headings':[1050,165,1670,222], 'ranks':[368,245,474,817],
        'points':[1098,247,1240,817], 'wins':[1510,247,1660,817], 'names':[686,241,1040,815]}
    if args.kind=='nickname': boxes={'nickname':[685,args.center_y-36,1045,args.center_y+12]}
    if args.kind=='profile':
        band=normalize_result(list(engine.predict(preprocess(crop(image,[1280,250,1444,950]),'color',2)))[0])
        _,top=profile_anchor(band)
        boxes={'id_band':[1280,250,1444,950], 'grade':[990,top+71,1295,top+123],
               'grade_tight':[990,top+71,1295,top+115], 'buttons':[780,top+216,1395,top+300]}
    result={key:normalize_result(list(engine.predict(preprocess(crop(image,box),'color',2)))[0]) for key,box in boxes.items()}
    out=args.image.with_suffix('.ocr.json');out.write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps(result,ensure_ascii=False,indent=2))


if __name__=='__main__': main()

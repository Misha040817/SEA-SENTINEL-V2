"""SEA SENTINEL V2: free CPU-friendly CLIP image-based maritime visual screening.

Requires: torch, transformers<5, pillow. The CLIP model is downloaded on first run.
Visual risk categories are provisional, not validated maritime safety decisions.
"""
import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

MODEL_ID = 'openai/clip-vit-base-patch32'
DB_PATH = Path(__file__).resolve().parent / 'sea_sentinel_results.sqlite3'

# Each hazard has a positive and a negative natural-language image description.
# The two-way CLIP score is a relative similarity, NOT a probability of an incident.
INDICATORS = {
    'fire_or_smoke': ('a photograph of a ship with obvious flames or thick smoke coming from the vessel',
                      'a photograph of a ship with no visible flames or smoke', 'HIGH', 'Visible smoke or flames near the vessel'),
    'visible_structural_damage': ('a photograph of a ship with clearly visible severe damage to its hull or superstructure',
                                  'a photograph of an intact ship with no visible structural damage', 'HIGH', 'Possible visible structural damage'),
    'possible_flooding_or_listing': ('a photograph of a ship capsizing or severely tilted to one side in the water',
                                     'a photograph of a ship floating upright in a normal orientation', 'HIGH', 'Possible severe listing or capsize'),
    'poor_visibility': ('a photograph of a ship in thick fog or very poor visibility',
                        'a photograph of a ship in clear weather with good visibility', 'MODERATE', 'Poor visibility around vessel'),
    'rough_seas': ('a photograph of a ship in dangerous rough seas with very large waves',
                   'a photograph of a ship in calm water with small waves', 'MODERATE', 'Rough sea conditions'),
    'close_vessel_proximity': ('a photograph of two ships appearing extremely close to each other',
                               'a photograph of a ship alone or ships clearly separated by open water', 'MODERATE', 'Apparent close vessel proximity'),
}


def load_model():
    """Load CLIP ViT-B/32 locally on CPU; cache via Streamlit st.cache_resource."""
    import torch
    from transformers import CLIPModel, CLIPProcessor
    torch.set_num_threads(min(4, max(1, torch.get_num_threads())))
    processor = CLIPProcessor.from_pretrained(MODEL_ID)
    model = CLIPModel.from_pretrained(MODEL_ID, low_cpu_mem_usage=True).to('cpu').eval()
    return processor, model


def _regions(image):
    img = image.convert('RGB')
    img.thumbnail((768, 768))
    w, h = img.size
    regions = [('Full image', img)]
    if w >= 320:
        regions += [('Left region', img.crop((0, 0, int(w * .7), h))),
                    ('Right region', img.crop((int(w * .3), 0, w, h)))]
    return regions


def _compare(processor, model, image, positive, negative):
    import torch
    inputs = processor(text=[positive, negative], images=image, return_tensors='pt', padding=True)
    with torch.inference_mode():
        logits = model(**inputs).logits_per_image[0]
        values = logits.softmax(dim=0).tolist()
    return float(values[0]), float(values[1])


def analyse_image(image, processor, model):
    """Compare actual image regions to contrasting hazard prompts. No generated JSON."""
    regions = _regions(image)
    hazards = []
    indicators = []
    negative_evidence = 0
    for key, (positive, negative, priority, description) in INDICATORS.items():
        comparisons = []
        for region_name, region in regions:
            pos, neg = _compare(processor, model, region, positive, negative)
            comparisons.append((pos, neg, region_name))
        best_pos, best_neg, best_region = max(comparisons, key=lambda x: x[0])
        # Conservative thresholds. These are heuristic and need validation on labelled photos.
        # A crop alone cannot establish physical distance, actual vessel movement or hostile intent.
        if best_pos >= .80 and best_pos - best_neg >= .60:
            status = 'Possible visual indicator'
            hazards.append({'type': key, 'evidence': description + ' (' + best_region + ')',
                            'certainty': 'possible', 'priority': priority,
                            'similarity': round(best_pos, 3)})
        elif all(neg >= .75 for _, neg, _ in comparisons):
            status = 'Not indicated'
            negative_evidence += 1
        else:
            status = 'Unconfirmed'
        indicators.append({'Indicator': description, 'Status': status,
                           'CLIP relative match': round(best_pos, 3), 'Region': best_region})
    if hazards:
        summary = 'Visual screening flagged: ' + '; '.join(h['evidence'] for h in hazards) + '.'
    elif negative_evidence == len(INDICATORS):
        summary = 'No screened hazard indicators were supported by the model in this image.'
    else:
        summary = 'No clear hazard indicators established; some visual conditions remain uncertain.'
    return {'summary': summary, 'hazards': hazards, 'indicators': indicators,
            'assessment_status': 'clip_image_comparison',
            'limitations': [
                'CLIP relative similarity scores are not calibrated hazard probabilities.',
                'Single photographs cannot establish speed, navigation behaviour, trajectory or intent.',
                'LOW is not proof of safety; all classifications require human verification.'
            ]}


def score_assessment(observations):
    hazards = observations.get('hazards', [])
    indicators = observations.get('indicators', [])
    if any(h.get('priority') == 'HIGH' for h in hazards):
        level = 'HIGH'
    elif hazards:
        level = 'MODERATE'
    elif indicators and all(i.get('Status') == 'Not indicated' for i in indicators):
        level = 'LOW'
    else:
        level = 'Unable to Assess'
    behavior = ('Possible abnormal vessel orientation or proximity; review image evidence.'
                if any(h.get('type') in ('possible_flooding_or_listing','close_vessel_proximity') for h in hazards)
                else 'No abnormal vessel orientation or proximity established from this photograph.')
    action = ('Urgent human review of the visual evidence and corroboration with AIS/video.' if level == 'HIGH'
              else 'Review flagged indicators and corroborate with AIS/video.' if level == 'MODERATE'
              else 'Continue routine monitoring; a photo cannot establish safety.' if level == 'LOW'
              else 'Image evidence insufficient; request clearer imagery or video and review manually.')
    return {'level': level, 'score': 0, 'hazards': hazards, 'indicators': indicators,
            'behavior': behavior, 'recommended_action': action,
            'summary': observations.get('summary', ''),
            'assessment_status': observations.get('assessment_status', ''),
            'limitations': observations.get('limitations', []),
            'disclaimer': 'Provisional CLIP-based visual screening. Not a validated maritime risk or behavioural detection system. Human verification required.'}


def save_result(filename, assessment, predictions):
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(DB_PATH) as conn:
        conn.execute('''CREATE TABLE IF NOT EXISTS visual_risk_results (
            id INTEGER PRIMARY KEY AUTOINCREMENT, timestamp TEXT NOT NULL,
            filename TEXT NOT NULL, risk_level TEXT NOT NULL, score INTEGER NOT NULL,
            assessment_json TEXT NOT NULL, detections_json TEXT NOT NULL)''')
        conn.execute('''INSERT INTO visual_risk_results
            (timestamp,filename,risk_level,score,assessment_json,detections_json)
            VALUES (?,?,?,?,?,?)''',
            (datetime.now(timezone.utc).isoformat(), filename, assessment['level'],
             assessment['score'], json.dumps(assessment), json.dumps(predictions, default=str)))
        conn.commit()


def read_results():
    if not DB_PATH.exists():
        return []
    with sqlite3.connect(DB_PATH) as conn:
        try:
            rows = conn.execute('''SELECT id,timestamp,filename,risk_level,score,assessment_json
                FROM visual_risk_results ORDER BY id DESC''').fetchall()
        except sqlite3.OperationalError:
            return []
    return [{'ID': r[0], 'Timestamp': r[1], 'Image': r[2], 'Risk Level': r[3],
             'Score': r[4], 'Assessment': json.loads(r[5])} for r in rows]

"""Conservative parsing and consistency checks for observed Android profile cards."""
import re
import numpy as np
from bwp_collector.validation import parse_field


def one_text(tokens, minimum=.95):
    if len(tokens) != 1 or tokens[0]['confidence'] < minimum:
        raise ValueError('empty, ambiguous or low-confidence OCR')
    return tokens[0]['text']


def profile_values(id_tokens, grade_tokens):
    # Never let the visible ID label become part of the persistent player identity.
    text=one_text(id_tokens)
    match=re.fullmatch(r'ID[:：]\s*([0-9]{1,64})', text)
    if not match:
        raise ValueError('profile ID is not an exact ID:digits label')
    # The grade crop can include tiny fragments from the decorative title below.
    # Ignore only short fragments at the bottom edge of this calibrated 2x crop;
    # never discard a full-sized competing grade or relax its confidence.
    grade_tokens=[t for t in grade_tokens if not (
        'box' in t and t['box'][1]>=70 and t['box'][3]-t['box'][1]<=32)]
    return {'player_id':match[1], 'grade':parse_field('grade',one_text(grade_tokens))}


def profile_anchor(tokens):
    """Find an explicit ID label in the vertical card band (crop top=250, scale=2)."""
    labels=[t for t in tokens if re.fullmatch(r'ID[:：]\s*[0-9]{1,64}',t['text'])]
    one_text(labels)
    top=round(250+labels[0]['box'][1]/2)
    if not 260<=top<=730:
        raise ValueError('Profile anchor outside calibrated area')
    return labels,top


def nickname_text(tokens):
    # Auxiliary consistency only. Discard tiny ornament detections (<15 source pixels
    # at scale 2); never use this filtering for player IDs or numeric game fields.
    text=[t for t in tokens if t['text'].strip() and t['box'][2]-t['box'][0]>=30]
    return one_text(text,minimum=.85)


def nickname_image_agrees(before,after,center_y,before_tokens,after_tokens,*,allow_unreadable=False):
    """Corroborate auxiliary nickname OCR with its tightly bounded source pixels.

    This never changes a persisted player ID. Reject moved text, tiny regions,
    constant regions and visibly different glyphs even when board numbers agree.
    """
    def box(tokens):
        candidates=[t for t in tokens if t['text'].strip() and t['box'][2]-t['box'][0]>=30]
        if not candidates: raise ValueError('No nickname image region')
        if not allow_unreadable: one_text(candidates,minimum=.85)
        return [min(t['box'][0] for t in candidates),min(t['box'][1] for t in candidates),
                max(t['box'][2] for t in candidates),max(t['box'][3] for t in candidates)]
    a,b=box(before_tokens),box(after_tokens)
    if any(abs(x-y)>4 for x,y in zip(a,b)): return False
    if any(not (0<=c[0]<c[2]<=720 and 0<=c[1]<c[3]<=122) for c in (a,b)): return False
    # Padding may touch the crop edge; keep it inside the calibrated region.
    left=max(685,685+min(a[0],b[0])//2-2)
    right=min(1045,685+(max(a[2],b[2])+1)//2+2)
    top=max(center_y-38,center_y-36+min(a[1],b[1])//2-2)
    bottom=min(center_y+27,center_y-36+(max(a[3],b[3])+1)//2+2)
    if not (685<=left<right<=1045 and center_y-38<=top<bottom<=center_y+27): return False
    first=before[top:bottom,left:right].astype(float)
    second=after[top:bottom,left:right].astype(float)
    if first.size<300 or min(first.std(),second.std())<5: return False
    difference=float(np.mean(np.abs(first-second)))
    correlation=float(np.corrcoef(first.reshape(-1),second.reshape(-1))[0,1])
    return difference<=2.5 and correlation>=.99


def rank_rows(tokens):
    """Full visible rows from rank strip [368,245,474,817], at scale 2.

    Edge fragments cannot be targets. Interior ranks must be consecutive and
    spaced like the calibrated 127px rows; never infer a missing rank.
    """
    rows=[]
    for token in tokens:
        y=round(245+(token['box'][1]+token['box'][3])/4)
        if not 264<=y<=793:
            continue
        text=one_text([token])
        if not re.fullmatch(r'[1-9][0-9]{0,2}',text):
            raise ValueError('Unknown visible rank')
        rows.append((int(text),y))
    rows.sort(key=lambda row:row[1])
    if len(rows)<3 or any(b[0]!=a[0]+1 or not 119<=b[1]-a[1]<=135
                          for a,b in zip(rows,rows[1:])):
        raise ValueError('Ranks are missing, duplicated or not stably aligned')
    return dict(rows)


def require_overlap(previous,current,target):
    if target not in current or not (set(previous)&set(current)):
        raise ValueError('Scroll skipped the target or has no overlapping ranks')
    if max(current)<=max(previous):
        raise ValueError('Scroll made no forward progress')


def return_difference(before, after, center_y):
    """Check static row content, excluding animated portraits and decorative badges."""
    if before.shape != after.shape or before.shape[:2] != (1080,1920):
        raise ValueError('layout size changed')
    # Clan ornaments at x=690..748 animate. The caller separately compares the full OCR nickname.
    boxes=[(755,center_y-25,1040,center_y+10), (1100,center_y-25,1235,center_y+25),
           (1510,center_y-25,1665,center_y+25), (112,604,255,650)]
    return max(float(np.mean(np.abs(before[t:b,l:r].astype(float)-after[t:b,l:r].astype(float))))
               for l,t,r,b in boxes)

import pytest
import numpy as np
from bwp_collector.live_profile import profile_values, profile_anchor, nickname_text, return_difference
from bwp_collector.validation import parse_field


@pytest.mark.parametrize('text,grade', [('名士五段 198席',9), ('大名士 22席',10),
                                      ('大名士9席',10), ('七段三阶',7), ('五段一阶',5),
                                      ('八段初阶',8), ('五段初阶',5),
                                      ('八段五阶5席',8), ('八段五阶 5席',8)])
def test_profile_grade_suffixes(text, grade):
    assert parse_field('grade', text) == grade


@pytest.mark.parametrize('text', ['历史最高大名士', '名士五段未知', '七段3', '名士19', '五段 大名士', '名土五段', '八段五阶S席', '八段五阶5席大名士'])
def test_uncertain_grade_labels_are_not_guessed(text):
    with pytest.raises(ValueError):
        parse_field('grade', text)


def token(text,confidence=.99): return [{'text':text,'confidence':confidence}]


def test_profile_id_keeps_leading_zeros_and_removes_only_exact_label():
    assert profile_values(token('ID:000123'),token('名士五段198席'))=={'player_id':'000123','grade':9}
    for text in ['ID:12O3','ID:123 456','id:123','123','ID:']:
        with pytest.raises(ValueError): profile_values(token(text),token('五段'))


def test_profile_ambiguity_and_low_confidence_are_rejected():
    with pytest.raises(ValueError): profile_values(token('ID:123',.94),token('五段'))
    with pytest.raises(ValueError): profile_values(token('ID:123')+token('ID:456'),token('五段'))


def test_return_checks_static_row_and_shikigami_but_ignores_avatar_animation():
    before=np.zeros((1080,1920,3),dtype=np.uint8);after=before.copy()
    after[230:330,570:675]=255
    after[260:295,690:748]=255
    assert return_difference(before,after,285)==0
    after[260:310,1100:1235]=255
    assert return_difference(before,after,285)>5
    with pytest.raises(ValueError): return_difference(before,after[:500],285)


def test_profile_anchor_tracks_vertical_position_without_using_player_name():
    label={'text':'ID:000123','confidence':.99,'box':[0,266,250,310]}
    labels,top=profile_anchor([{'text':'a nickname','confidence':.99,'box':[0,340,250,400]},label])
    assert labels==[label] and top==383
    with pytest.raises(ValueError): profile_anchor([label,label])
    with pytest.raises(ValueError): profile_anchor([{**label,'confidence':.8}])


def test_auxiliary_nickname_ignores_tiny_ornaments_but_rejects_two_real_labels():
    name={'text':'樱花入夜细无声','confidence':.93,'box':[139,16,619,90]}
    noise={'text':'2','confidence':.13,'box':[4,69,13,78]}
    assert nickname_text([name,noise])==name['text']
    with pytest.raises(ValueError): nickname_text([name,{**name,'text':'another name'}])
    with pytest.raises(ValueError): nickname_text([noise])

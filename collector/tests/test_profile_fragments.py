import pytest
import numpy as np
from bwp_collector.live_profile import profile_values
from bwp_collector.live_profile import nickname_image_agrees


def test_bottom_decoration_fragment_does_not_replace_actual_grade():
    identity=[{'text':'ID:14084871','confidence':.996}]
    grade={'text':'名士四段','confidence':.999,'box':[24,19,297,89]}
    fragments=[{'text':'','confidence':0,'box':[5,83,41,104]},
               {'text':'产','confidence':.13,'box':[440,83,460,104]},
               {'text':'-','confidence':.07,'box':[435,74,463,104]}]
    assert profile_values(identity,[grade,*fragments])['grade']==9
    with pytest.raises(ValueError): profile_values(identity,fragments)
    with pytest.raises(ValueError): profile_values(identity,[{**grade,'confidence':.94},*fragments])


def test_full_sized_conflicting_grade_still_rejected():
    identity=[{'text':'ID:123','confidence':.99}]
    grades=[{'text':'名士四段','confidence':.99,'box':[24,19,297,89]},
            {'text':'五段','confidence':.99,'box':[300,18,430,90]}]
    with pytest.raises(ValueError): profile_values(identity,grades)


def test_nickname_visual_confirmation_requires_same_pixels_and_position():
    before=np.zeros((1080,1920,3),dtype=np.uint8)
    before[512:550,748:805]=np.random.default_rng(7).integers(0,256,(38,57,3),dtype=np.uint8)
    first=[{'text':'lnc','confidence':.86,'box':[132,22,233,86]}]
    second=[{'text':'Inc','confidence':.91,'box':[133,22,233,86]}]
    assert nickname_image_agrees(before,before.copy(),539,first,second)
    unreadable=[{**first[0],'text':'火し口阝可','confidence':.79}]
    with pytest.raises(ValueError): nickname_image_agrees(before,before,539,unreadable,unreadable)
    assert nickname_image_agrees(before,before,539,unreadable,unreadable,allow_unreadable=True)
    changed=before.copy();changed[520:540,755:765]=255
    assert not nickname_image_agrees(before,changed,539,first,second)
    assert not nickname_image_agrees(before,before,539,first,[{**second[0],'box':[143,22,243,86]}])


def test_nickname_at_left_crop_edge_keeps_pixel_verification():
    before=np.zeros((1080,1920,3),dtype=np.uint8)
    before[760:807,685:765]=np.random.default_rng(8).integers(0,256,(47,80,3),dtype=np.uint8)
    tokens=[{'text':'黃初','confidence':.799,'box':[3,9,153,96]}]
    assert nickname_image_agrees(before,before.copy(),793,tokens,tokens,allow_unreadable=True)
    changed=before.copy();changed[770:790,690:710]=255
    assert not nickname_image_agrees(before,changed,793,tokens,tokens,allow_unreadable=True)
    outside=[{**tokens[0],'box':[-3,9,153,96]}]
    assert not nickname_image_agrees(before,before,793,outside,outside,allow_unreadable=True)

from aegis.nexus.neurobus import NeuroState

def test_neurostate_vec_length():
    assert len(NeuroState().vec()) == 6

def test_neurostate_clamp_bounds():
    s = NeuroState(reward=9.0, threat=-9.0)
    s.clamp()
    assert s.reward == 1.0
    assert s.threat == -1.0

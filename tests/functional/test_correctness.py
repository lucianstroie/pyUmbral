"""
Copyright (C) 2018 NuCypher

This file is part of pyUmbral.

pyUmbral is free software: you can redistribute it and/or modify
it under the terms of the GNU General Public License as published by
the Free Software Foundation, either version 3 of the License, or
(at your option) any later version.

pyUmbral is distributed in the hope that it will be useful,
but WITHOUT ANY WARRANTY; without even the implied warranty of
MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
GNU General Public License for more details.

You should have received a copy of the GNU General Public License
along with pyUmbral. If not, see <https://www.gnu.org/licenses/>.
"""

import pytest

from umbral import pre
from umbral.point import Point

def test_cheating_ursula_replays_old_reencryption(alices_keys, bobs_keys, 
                                                  kfrags, prepared_capsule):

    delegating_privkey, signing_privkey = alices_keys
    delegating_pubkey = delegating_privkey.get_pubkey()

    receiving_privkey, receiving_pubkey = bobs_keys
    
    capsule_alice1 = prepared_capsule

    _unused_key2, capsule_alice2 = pre._encapsulate(delegating_pubkey)

    capsule_alice2.set_correctness_keys(delegating=delegating_pubkey,
                                        receiving=receiving_pubkey,
                                        verifying=signing_privkey.get_pubkey())

    cfrags = []
    for i, kfrag in enumerate(kfrags):

        # Example of potential metadata to describe the re-encryption request
        metadata_i = "This is an example of metadata for re-encryption request #{}"
        metadata_i = metadata_i.format(i).encode()

        if i == 0:
            # Let's put the re-encryption of a different Alice ciphertext
            cfrag = pre.reencrypt(kfrag, capsule_alice2, metadata=metadata_i)
        else:
            cfrag = pre.reencrypt(kfrag, capsule_alice1, metadata=metadata_i)

        cfrags.append(cfrag)


    # CFrag 0 is not valid ...
    assert not cfrags[0].verify_correctness(capsule_alice1)

    # ... and trying to attach it raises an error.
    with pytest.raises(pre.UmbralCorrectnessError) as exception_info:
        capsule_alice1.attach_cfrag(cfrags[0])

    correctness_error = exception_info.value
    assert cfrags[0] in correctness_error.offending_cfrags
    assert len(correctness_error.offending_cfrags) == 1

    # The rest of CFrags should be correct:
    correct_cases = 0
    for cfrag_i in cfrags[1:]:
        assert cfrag_i.verify_correctness(capsule_alice1)
        capsule_alice1.attach_cfrag(cfrag_i)
        correct_cases += 1
        
    assert correct_cases == len(cfrags[1:])

def test_cheating_ursula_sends_garbage(kfrags, prepared_capsule):
    
    capsule_alice = prepared_capsule

    cfrags = []
    for i, kfrag in enumerate(kfrags):
        # Example of potential metadata to describe the re-encryption request
        metadata_i = "This is an example of metadata for re-encryption request #{}"
        metadata_i = metadata_i.format(i).encode()

        cfrag = pre.reencrypt(kfrag, capsule_alice, metadata=metadata_i)
        cfrags.append(cfrag)

    # Let's put random garbage in one of the cfrags
    cfrags[0]._point_e1 = Point.gen_rand()
    cfrags[0]._point_v1 = Point.gen_rand()

    # Of course, this CFrag is not valid ...
    assert not cfrags[0].verify_correctness(capsule_alice)

    # ... and trying to attach it raises an error.
    with pytest.raises(pre.UmbralCorrectnessError) as exception_info:
        capsule_alice.attach_cfrag(cfrags[0])

    correctness_error = exception_info.value
    assert cfrags[0] in correctness_error.offending_cfrags
    assert len(correctness_error.offending_cfrags) == 1

    # The response of cheating Ursula is in cfrags[0],
    # so the rest of CFrags chould be correct: 
    for cfrag_i in cfrags[1:]:
        assert cfrag_i.verify_correctness(capsule_alice)
        capsule_alice.attach_cfrag(cfrag_i)


def test_cfrag_with_missing_proof_cannot_be_attached(kfrags, prepared_capsule):

    capsule = prepared_capsule

    cfrags = []
    for kfrag in kfrags:
        cfrag = pre.reencrypt(kfrag, capsule)
        cfrags.append(cfrag)

    # If the proof is lost (e.g., it is chopped off a serialized CFrag or similar), 
    # then the CFrag cannot be attached.
    cfrags[0].proof = None
    with pytest.raises(cfrag.NoProofProvided):
        capsule.attach_cfrag(cfrags[0])

    # The remaining CFrags are fine, so they can be attached correctly 
    for cfrag in cfrags[1:]:
        capsule.attach_cfrag(cfrag)


def test_inconsistent_cfrags(bobs_keys, kfrags, prepared_capsule):

    receiving_privkey, receiving_pubkey = bobs_keys

    capsule = prepared_capsule

    cfrags = []
    for kfrag in kfrags:
        cfrag = pre.reencrypt(kfrag, capsule)
        cfrags.append(cfrag)
    
    # For all cfrags that belong to the same policy, the values 
    # cfrag._point_noninteractive and cfrag._point_noninteractive
    # must be the same. If we swap them, it shouldn't be possible 
    # to attach the cfrag to the capsule. Let's mangle the first CFrag
    cfrags[0]._point_noninteractive, cfrags[0]._point_xcoord = cfrags[0]._point_xcoord, cfrags[0]._point_noninteractive
    with pytest.raises(pre.UmbralCorrectnessError):
        capsule.attach_cfrag(cfrags[0])

    # The remaining M cfrags should be fine. 
    for cfrag in cfrags[1:]:   
        capsule.attach_cfrag(cfrag)

    # Just for fun, let's try to reconstruct the capsule with them:
    capsule._reconstruct_shamirs_secret(receiving_privkey)

    
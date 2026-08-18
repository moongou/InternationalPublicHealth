from __future__ import annotations

import secrets

from gmssl import sm2


def key_pair() -> tuple[str, str]:
    order = int(sm2.default_ecc_table["n"], 16)
    while True:
        private = secrets.token_hex(32)
        if 0 < int(private, 16) < order:
            break
    codec = sm2.CryptSM2(public_key="", private_key=private)
    public = codec._kg(int(private, 16), sm2.default_ecc_table["g"])
    return private, public


recipient_private, recipient_public = key_pair()
signing_private, signing_public = key_pair()
print(f"SM2_RECIPIENT_PRIVATE_KEY={recipient_private}")
print(f"SM2_RECIPIENT_PUBLIC_KEY={recipient_public}")
print(f"SM2_SIGNING_PRIVATE_KEY={signing_private}")
print(f"SM2_SIGNING_PUBLIC_KEY={signing_public}")

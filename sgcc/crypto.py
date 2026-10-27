"""请求 / 响应的加密封装（SM2 + SM4 + SM3）。"""

import json
import os
import secrets
import time

from gmssl import sm2, sm3
from gmssl.sm4 import CryptSM4, SM4_DECRYPT, SM4_ENCRYPT

from .config import load_json, APP_DIR

SERVER_PUB = (
    "BCB9F08A84A76E539366A8E1830808875C36561E985E02306E179185FC7F4202"
    "B4446F93638C0F6A52DBE3016A827A8DCB9B7F5C7C5192B25705A964499826EA"
)
PRIV_NAME = "crypto.json"
PRIV_HINT = (
    "缺少 SM2 客户端私钥（用于解密服务端响应）。请设置环境变量 SGCC_CLIENT_PRIV，"
    f"或写入 {APP_DIR / PRIV_NAME}：{{\"client_priv\": \"<64 位 hex>\"}}"
)

_sm2_dec = None
_sm2_enc = sm2.CryptSM2(private_key="", public_key=SERVER_PUB, mode=1)


def client_priv() -> str:
    """客户端私钥不随仓库分发，由使用者自行提供。"""
    key = os.environ.get("SGCC_CLIENT_PRIV", "").strip()
    if not key:
        key = (load_json(APP_DIR / PRIV_NAME, {}) or {}).get("client_priv", "").strip()
    if len(key) != 64:
        raise RuntimeError(PRIV_HINT)
    try:
        bytes.fromhex(key)
    except ValueError:
        raise RuntimeError(PRIV_HINT) from None
    return key.upper()


def _decryptor() -> sm2.CryptSM2:
    global _sm2_dec
    if _sm2_dec is None:
        _sm2_dec = sm2.CryptSM2(private_key=client_priv(), public_key="", mode=1)
    return _sm2_dec


def sm2_decrypt(ct_hex: str) -> bytes:
    b = bytes.fromhex(ct_hex)
    if b[0] != 0x04:
        raise ValueError("not an uncompressed SM2 point")
    return _decryptor().decrypt(b[1:])


def sm2_encrypt(plain: bytes) -> str:
    return "04" + _sm2_enc.encrypt(plain).hex()


def sm4_decrypt_ecb(key16: bytes, ct_hex: str) -> bytes:
    c = CryptSM4()
    c.set_key(key16, SM4_DECRYPT)
    return c.crypt_ecb(bytes.fromhex(ct_hex))


def sm4_encrypt_ecb(key16: bytes, plain: bytes) -> str:
    c = CryptSM4()
    c.set_key(key16, SM4_ENCRYPT)
    return c.crypt_ecb(plain).hex()


def sign_envelope(skey_hex: str, data_hex: str, timestamp: str) -> str:
    return sm3.sm3_hash(list((skey_hex + data_hex + timestamp).encode()))


def open_response(resp: dict) -> dict:
    kstr = sm2_decrypt(resp["respKey"]).decode("ascii")
    plain = sm4_decrypt_ecb(kstr[:16].encode(), resp["encryptData"])
    return json.loads(plain.decode("utf-8"))


def new_sm4_key() -> str:
    """32 位 ASCII hex（16 字节），与客户端行为一致。"""
    return secrets.token_hex(16)


def seal_request(obj: dict, key_hex: str | None = None) -> dict:
    """把请求 JSON 封成 {data, timestamp, skey, sign}。"""
    key_hex = key_hex or new_sm4_key()
    data = sm4_encrypt_ecb(
        key_hex[:16].encode(),
        json.dumps(obj, separators=(",", ":"), ensure_ascii=False).encode(),
    )
    skey = sm2_encrypt(key_hex.encode("ascii"))
    ts = str(int(time.time() * 1000))
    return {"data": data, "timestamp": ts, "skey": skey, "sign": sign_envelope(skey, data, ts)}

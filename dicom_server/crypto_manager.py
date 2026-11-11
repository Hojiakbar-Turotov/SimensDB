"""
crypto_manager.py - Bemor ma'lumotlarini uchdan-uchga (End-to-End Encryption) shifrlash moduli
Standart: AES-256-GCM (Harbiy darajadagi autentifikatsiyalangan shifrlash)

Faqat Agent va Admin dasturlarida bir xil kalit (Secret Key) bo'lgandagina ochiladi.
GitHub yoki internet orqali faqat qorong'i shifrlangan baytlar (ciphertext) o'tadi.
Hech kim, hatto GitHub ma'muriyati ham bemor ma'lumotlarini ocholmaydi.
"""
import os
import sys
import json
import base64
import hashlib
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC
from cryptography.hazmat.primitives import hashes

# Standart tuz (Salt) - kalit hosil qilish uchun
DEFAULT_SALT = b"Siemens_Fuji_DICOM_E2EE_2026_Salt"

class E2EESecurity:
    def __init__(self, secret_key: str):
        self.key = self._derive_key(secret_key)
        self.aesgcm = AESGCM(self.key)

    def _derive_key(self, secret: str) -> bytes:
        """Ixtiyoriy matnli paroldan 256-bitli (32 bayt) xavfsiz AES kaliti hosil qilish"""
        if not secret:
            secret = "DEFAULT_HOSPITAL_MASTER_KEY_CHANGE_ME"
        kdf = PBKDF2HMAC(
            algorithm=hashes.SHA256(),
            length=32,
            salt=DEFAULT_SALT,
            iterations=100000,
        )
        return kdf.derive(secret.encode('utf-8'))

    def encrypt_payload(self, data_dict: dict) -> str:
        """
        Bemor ma'lumotlari, tasvirlar va metama'lumotlarni AES-256-GCM bilan shifrlash
        Natija: Xavfsiz Base64 matni (.enc fayl)
        """
        raw_json = json.dumps(data_dict, ensure_ascii=False).encode('utf-8')
        nonce = os.urandom(12) # GCM uchun 96-bitli yagona tasodifiy son
        ciphertext = self.aesgcm.encrypt(nonce, raw_json, None)
        # Birlashtirish: nonce (12 bayt) + ciphertext
        payload = nonce + ciphertext
        return base64.b64encode(payload).decode('ascii')

    def decrypt_payload(self, encrypted_b64: str) -> dict:
        """
        Shifrlangan Base64 matnini asliga qaytarish (Decryption)
        Agar kalit mos kelmasa yoki ma'lumot o'zgartirilgan bo'lsa, xatolik beradi.
        """
        raw = base64.b64decode(encrypted_b64.encode('ascii'))
        if len(raw) < 28: # 12 bayt nonce + 16 bayt tag
            raise ValueError("Shifrlangan fayl hajmi juda kichik yoki buzilgan")
        nonce = raw[:12]
        ciphertext = raw[12:]
        decrypted_bytes = self.aesgcm.decrypt(nonce, ciphertext, None)
        return json.loads(decrypted_bytes.decode('utf-8'))

    def encrypt_file(self, src_path: str, dst_path: str):
        with open(src_path, 'rb') as f:
            raw = f.read()
        nonce = os.urandom(12)
        ct = self.aesgcm.encrypt(nonce, raw, None)
        with open(dst_path, 'wb') as f:
            f.write(nonce + ct)

    def decrypt_file(self, src_path: str, dst_path: str):
        with open(src_path, 'rb') as f:
            data = f.read()
        nonce = data[:12]
        ct = data[12:]
        pt = self.aesgcm.decrypt(nonce, ct, None)
        with open(dst_path, 'wb') as f:
            f.write(pt)

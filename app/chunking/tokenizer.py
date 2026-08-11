"""Yaklaşık token sayımı (spec §16 — chunk boyutu hedefleri için).

Tam bir BPE tokenizer'a (tiktoken, transformers vb.) bağımlı olmak
yerine karakter/4 yaklaşımı kullanılıyor: proje zaten numpy gibi
temel bir bağımlılığı bile içermiyor, ve spec'teki token hedefleri
("başlangıç değerleri" olarak tanımlı) kesin bir kısıt değil, kaba
bir boyut kılavuzu. Formül-ağırlıklı metinde (örn. "I=Q/t") kelime
sayımı boşluksuz semboller yüzünden güvenilir değil; karakter tabanlı
yaklaşım buna karşı daha dayanıklı.
"""

_CHARS_PER_TOKEN = 4


def estimate_tokens(text: str) -> int:
    return max(1, len(text) // _CHARS_PER_TOKEN)

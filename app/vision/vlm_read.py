"""Kullanıcının kendi devre fotoğrafını bir VLM ile okuyup netlist taslağına çevirir.

Kitap şekilleri için VLM'e hiç gerek yok (`pdf_figure.py`/`schematic.py`
PDF'in vektör verisinden geometrik olarak okuyor, kesin). Kullanıcının
kendi yüklediği fotoğraf/kırpma ise raster'dır — vektör yolu burada
kullanılamaz, bu yüzden ayrı bir VLM tabanlı okuma gerekiyor.

Model seçimi ve bilinen doğruluk sınırı: `docs/vlm-karsilastirma-sonuclari.md`.
**Kritik:** hem denenen VLM'ler (qwen3-vl, minicpm-v) hem literatür (SINA,
arXiv:2607.01609) aynı zaafı gösteriyor — kaynak POLARİTESİ (+/- ucu)
güvenilir okunamıyor, model bağımsız. Bu yüzden bu modülün çıktısı asla
doğrudan çözülmez: kullanıcı onayı/düzeltmesi zorunlu (bkz. `docs/vision.md`).

Tasarım kararı: bu modül `app.circuit.netlist.Element` NESNESİ üretmez,
düzenlenebilir DICT satırları üretir. Sebep: bir VLM okuması geçersiz bir
devre üretebilir (örn. aynı düğüme iki kez bağlı bir eleman) ve `Element`
bunu constructor'da reddeder (bkz. netlist.py) — o taslağı sessizce atmak
yerine kullanıcıya GÖSTERİP düzelttirmek gerekiyor. `Element`/`Netlist`
doğrulaması yalnızca kullanıcı onayladıktan SONRA (bkz. `draft_to_netlist`)
devreye girer.

Bağımlı kaynaklar (VCVS/CCVS) bu modülde BİLEREK okunmuyor: kontrol
referansının geometrisi (hangi elemanın hangi büyüklüğü kontrol ettiği)
zaten kitap şekillerinde bile zahmetli bir eşleştirmeydi (bkz.
`pdf_figure.py`), rastgele bir fotoğrafta VLM için çok daha belirsiz.
Kullanıcı düzeltme formunda elle ekleyebilir.
"""

import json
import re

import requests

from app.circuit.netlist import Element, Netlist

OLLAMA_CHAT_URL = "http://localhost:11434/api/chat"
VLM_MODEL = "minicpm-v4.5:8b"
CALL_TIMEOUT_SECONDS = 300
KEEP_ALIVE = "10m"

# VLM'den beklenen türler — dependent source YOK (bkz. modül docstring'i).
READABLE_KINDS = {"resistor", "voltage_source", "current_source", "capacitor", "inductor"}
SOURCE_KINDS = {"voltage_source", "current_source"}

_JSON_BLOCK_RE = re.compile(r"\{.*\}", re.DOTALL)

_SYSTEM_PROMPT = """Sen bir devre şeması okuyucususun. Sana bir devre şeması görseli verilecek.
Şekildeki HER elemanı ve bağlantısını çıkar.

KURALLAR:
- Şekildeki her düğüme (bağlantı noktası) bir HARF ver (A, B, C, ...). Şekilde zaten yazılı düğüm/uç etiketi varsa onu kullan.
- Toprak sembolü (yere doğru kısalan yatay çizgiler) varsa o düğümün adı "gnd" olsun.
- Direnç/kapasitör/bobin gibi YÖNSÜZ elemanlar için "node_a"/"node_b" kullan (sıra önemsiz).
- Gerilim/akım kaynağı gibi YÖNLÜ elemanlar için "node_plus"/"node_minus" kullan: gerilim kaynağında + işaretli uç, akım kaynağında okun İÇİNE GİRDİĞİ uç "node_plus" olur.
- Kaynak fazör olarak yazılmışsa ("10∠30° V" gibi) "phase_degrees" derece cinsinden yaz; yoksa 0 yaz.
- Devrede bir frekans/açısal frekans yazılıysa ("f=60Hz", "ω=100 rad/s") "frequency_hz" alanına Hz cinsinden yaz (ω verilmişse f=ω/(2π) hesapla); yoksa null yaz.
- Bağımlı (kontrollü) kaynak (baklava şeklinde, "2vx" gibi) görürsen dahil ETME, "notlar" alanına yaz.
- Emin olmadığın bir değeri UYDURMA — o alanı null bırak.

ÇIKTI BİÇİMİ — yalnızca şu JSON'u yaz, başka hiçbir şey yazma:
{
  "elements": [
    {"name": "R1", "kind": "resistor", "value": 10, "node_a": "A", "node_b": "B"},
    {"name": "V1", "kind": "voltage_source", "value": 12, "node_plus": "A", "node_minus": "gnd", "phase_degrees": 0}
  ],
  "frequency_hz": null,
  "notlar": ""
}"""


class VLMReadError(RuntimeError):
    """VLM çıktısı ayrıştırılamadı/beklenen biçimde değil.

    Sessizce eksik bir devre üretmek yerine ham yanıtı taşıyarak (`raw`)
    açıkça durur — çağıran taraf bunu kullanıcıya gösterip elle giriş ya
    da yeniden deneme seçeneği sunmalı.
    """

    def __init__(self, message: str, raw: str = "") -> None:
        super().__init__(message)
        self.raw = raw


def _call_vlm(image_base64: str) -> str:
    response = requests.post(
        OLLAMA_CHAT_URL,
        json={
            "model": VLM_MODEL,
            "messages": [
                {"role": "system", "content": _SYSTEM_PROMPT},
                {
                    "role": "user",
                    "content": "Bu devre şemasındaki elemanları ve bağlantılarını çıkar.",
                    "images": [image_base64],
                },
            ],
            "stream": False,
            "keep_alive": KEEP_ALIVE,
            "options": {"temperature": 0.1},
        },
        timeout=CALL_TIMEOUT_SECONDS,
    )
    response.raise_for_status()
    return response.json()["message"]["content"]


def _parse_element(item: dict, index: int) -> dict:
    kind = item.get("kind")
    if kind not in READABLE_KINDS:
        raise VLMReadError(f"Eleman {index + 1}: bilinmeyen/desteklenmeyen tür {kind!r}")

    name = str(item.get("name") or f"{kind[:1].upper()}{index + 1}").strip()
    value = item.get("value")
    if value is not None:
        try:
            value = float(value)
        except (TypeError, ValueError) as exc:
            raise VLMReadError(f"Eleman {index + 1} ({name}): sayısal olmayan değer {value!r}") from exc

    if kind in SOURCE_KINDS:
        node_a, node_b = item.get("node_plus"), item.get("node_minus")
        if not node_a or not node_b:
            raise VLMReadError(f"Eleman {index + 1} ({name}): node_plus/node_minus eksik")
    else:
        node_a, node_b = item.get("node_a"), item.get("node_b")
        if not node_a or not node_b:
            raise VLMReadError(f"Eleman {index + 1} ({name}): node_a/node_b eksik")

    phase = item.get("phase_degrees") or 0
    try:
        phase = float(phase)
    except (TypeError, ValueError) as exc:
        raise VLMReadError(f"Eleman {index + 1} ({name}): sayısal olmayan faz {phase!r}") from exc

    return {
        "name": name,
        "kind": kind,
        "value": value,
        "node_a": str(node_a).strip(),
        "node_b": str(node_b).strip(),
        "phase_degrees": phase,
    }


def parse_vlm_response(raw: str) -> dict:
    """VLM'in ham metin yanıtını taslak eleman listesine çevirir.

    Dönen: {"elements": [{"name","kind","value","node_a","node_b","phase_degrees"}, ...],
            "frequency_hz": float | None, "notlar": str}

    Biçime uymayan bir yanıt SESSİZCE eksik bir devre üretmez — `VLMReadError`
    fırlatılır, ham metin `error.raw`'da taşınır (bkz. modül docstring'i).
    """
    match = _JSON_BLOCK_RE.search(raw)
    if not match:
        raise VLMReadError("VLM yanıtında JSON bulunamadı.", raw=raw)
    try:
        payload = json.loads(match.group(0))
    except json.JSONDecodeError as exc:
        raise VLMReadError(f"VLM yanıtı geçerli JSON değil: {exc}", raw=raw) from exc

    raw_elements = payload.get("elements")
    if not isinstance(raw_elements, list) or not raw_elements:
        raise VLMReadError("VLM yanıtında 'elements' listesi yok/boş.", raw=raw)

    elements = [_parse_element(item, i) for i, item in enumerate(raw_elements)]

    frequency = payload.get("frequency_hz")
    if frequency is not None:
        try:
            frequency = float(frequency)
        except (TypeError, ValueError) as exc:
            raise VLMReadError(f"Sayısal olmayan frequency_hz: {frequency!r}", raw=raw) from exc

    return {
        "elements": elements,
        "frequency_hz": frequency,
        "notlar": str(payload.get("notlar") or "").strip(),
    }


def read_circuit_image(image_base64: str) -> dict:
    """Base64 kodlu bir devre görselini VLM ile okuyup taslak netlist döner.

    Ön koşul: Ollama çalışıyor, `minicpm-v4.5:8b` çekilmiş
    (`ollama pull minicpm-v4.5:8b`).
    """
    raw = _call_vlm(image_base64)
    return parse_vlm_response(raw)


def draft_to_netlist(rows: list[dict]) -> Netlist:
    """Kullanıcının onayladığı/düzelttiği taslak satırları gerçek bir `Netlist`'e çevirir.

    `Element`/`Netlist` kendi kuralları burada devreye girer (tür geçerliliği,
    tekrarsız eleman adı, bir elemanın iki ucunun aynı düğüm olmaması) —
    hâlâ geçersizse `ValueError` fırlatır; çağıran taraf bunu kullanıcıya
    göstermeli, sessizce yutmamalı.
    """
    elements = [
        Element(
            name=row["name"],
            kind=row["kind"],
            nodes=(str(row["node_a"]).strip(), str(row["node_b"]).strip()),
            value=None if row.get("value") in (None, "") else float(row["value"]),
            phase=float(row.get("phase_degrees") or 0.0),
        )
        for row in rows
    ]
    return Netlist(elements)

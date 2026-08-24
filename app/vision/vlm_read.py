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

import cmath
import json
import math
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


_VALUE_SYSTEM_PROMPT = """Sen bir devre şeması okuyucususun. Sana TEK BİR devre elemanının
(ve varsa yanındaki değer yazısının) kırpılmış görüntüsü verilecek.
Elemanın BAĞLANTISIYLA İLGİLENME, yalnızca ÜZERİNDEKİ/YANINDAKİ değeri oku.

KURALLAR:
- "number" alanına yazıda AYNEN YAZILI sayıyı yaz (birim çevirisi YAPMA,
  hesap YAPMA) — örn. "4 Ω" görürsen 4 yaz, "5 kΩ" görürsen 5 yaz.
- "unit" alanına yaziyi AYNEN kopyala (BUYUK/kucuk harf DAHIL): "ohm",
  "kohm", "V", "mA", "kV", "uF" vb. — KRİTİK: "mΩ" (miliohm) ile "MΩ"
  (megaohm) SADECE harf büyüklüğüyle ayrışır, birbirine ÇEVİRME/normalize
  ETME, gördüğün harfi (küçük m mi büyük M mi) AYNEN yaz.
- Fazör olarak yazılmışsa ("10∠30° V" gibi) "phase_degrees" derece cinsinden yaz; yoksa 0.
- Bir frekans/açısal frekans yazılıysa Hz cinsinden "frequency_hz" yaz (ω verilmişse f=ω/(2π)); yoksa null.
- KRİTİK: görüntüde SAYISAL bir değer YAZILI DEĞİLSE (yalnızca "R_eq", "v",
  "i", "R1", "Vs" gibi bir SEMBOL/DEĞİŞKEN harfi görüyorsan, ya da hiçbir
  yazı yoksa), "number" alanını KESİNLİKLE null bırak. Yokluğunda bir sayı
  TAHMİN ETME/UYDURMA — devre elemanının TİPİK bir değeri olabileceğini
  düşünüp sayı üretmek YASAK, sadece görüntüde GERÇEKTEN YAZILI olanı bildir.

ÇIKTI BİÇİMİ — yalnızca şu JSON'u yaz, başka hiçbir şey yazma:
{"number": 5, "unit": "kohm", "phase_degrees": 0, "frequency_hz": null}"""

_VALUE_JSON_RE = re.compile(r"\{.*\}", re.DOTALL)

# SI taban birime carpan -- VLM'e MATEMATIK YAPTIRMIYORUZ (OLCULDU: "kΩ->Ω
# cevir" kurali VLM'e verilince model "k" olmadan da BOLU 1000 uyguluyordu,
# Figure 2.28'deki 3 direncin UCU DE 1000 kat buyuk okundu -- 4 Ω -> 4000
# gibi). Cevrim burada, deterministik Python'da yapiliyor; VLM'den sadece
# YAZIDAKI HAM SAYI ve birim ADI isteniyor.
_UNIT_MULTIPLIERS = {
    "ohm": 1.0, "ω": 1.0, "kohm": 1e3, "kω": 1e3, "megaohm": 1e6,
    "v": 1.0, "kv": 1e3, "mv": 1e-3,
    "a": 1.0, "ma": 1e-3, "ua": 1e-6, "µa": 1e-6,
    "f": 1.0, "uf": 1e-6, "µf": 1e-6, "nf": 1e-9, "pf": 1e-12,
    "h": 1.0, "mh": 1e-3, "uh": 1e-6, "µh": 1e-6,
}
# Omega'nin "m" oneki BUYUK/kucuk harfe DUYARLI: "MΩ"/"Mohm" (MEGA, 1e6)
# ile "mΩ"/"mohm" (MILI, 1e-3) SADECE bu harften ayrisir -- diger tum
# birimlerde (mV/mA/mH) "m" HER ZAMAN mili, karisiklik yok, o yuzden onlar
# genel tabloda kucuk harfle sabit. Miliohm GERCEKTEN KULLANILIYOR
# (kullanici teyit etti, 2026-08-21) -- bu yuzden ohm'un "m" oneki ozel
# olarak, kucuk/buyuk harf KORUNARAK ele alinir (asagida _unit_multiplier).
_OHM_M_PREFIX_MULTIPLIER = {"m": 1e-3, "M": 1e6}
_OHM_TAILS = {"ohm", "ω"}


def _unit_multiplier(unit: str | None) -> float:
    """Birim -> SI carpani. Prompt VLM'e birimi AYNEN kopyalamasini soyluyor
    (bkz. _VALUE_SYSTEM_PROMPT) -- yani kitapta gecen HERHANGI bir yazim
    gelebilir, sabit bir kume degil. Tanimadigimiz bir birim gelince eskiden
    SESSIZCE 1.0 (birimsiz) varsayiliyordu -- OLCULDU (kod incelemesi):
    "MΩ" (megaohm) gibi tabloda olmayan bir birim gorulse deger carpansiz
    kalir, 1.000.000 kat kucuk okunurdu, hicbir hata/uyari vermeden. Artik
    aciktan hata veriyor -- sessiz yanlis cevap yerine.
    """
    if not unit:
        return 1.0
    stripped = unit.strip().replace("μ", "µ").replace(" ", "")
    # Buyuk/kucuk harf AYRIMI burada BILEREK korunuyor (genel yol asagida
    # hepsini kucultuyor) -- "MΩ" ile "mΩ" 1e9 kat FARKLI deger, ikisini
    # ayni sanmak (eski davranis) miliohm'u megaohm okurdu.
    if len(stripped) > 1 and stripped[0] in _OHM_M_PREFIX_MULTIPLIER and stripped[1:].lower() in _OHM_TAILS:
        return _OHM_M_PREFIX_MULTIPLIER[stripped[0]]
    key = stripped.lower()
    if key not in _UNIT_MULTIPLIERS:
        raise ValueError(f"bilinmeyen birim: {unit!r}")
    return _UNIT_MULTIPLIERS[key]


_OCR_VALUE_RE = re.compile(r"^(\d+(?:\.\d+)?)\s*(.*)$")


def parse_ocr_value_hint(text: str) -> dict | None:
    """OCR'ın (devre-yolo-dedektor/extract_for_solve.py `ocr_value_hint`)
    bulduğu TEK, açık deger-benzeri metni deterministik ayrıştırır.

    Neden var: VLM çağrısı pipeline'ın en yavaş adımı (ağ üzerinden model
    çalıştırma) -- OCR zaten kirpimin yakınında net, TEK bir sayı+birim
    bulmuşsa (bkz. ocr_value_hint'in 0/1/2+ aday ayrımı) VLM'e sormaya
    gerek yok, doğrudan burada parse edilir.

    GÜVENLİ BAŞARISIZLIK: sayı/birim ayrıştırılamazsa (OCR'ın Ω'yi "0"/"Q"
    okuması gibi -- bkz. ocr_text.py modül docstring'i) None döner, çağıran
    taraf VLM'e düşer -- asla tahmin ETMEZ, olsa olsa VLM'i gereksiz çağırır.
    Faz/frekans (fazör gösterimi, "10∠30°") bu basit sayı+birim kalıbına
    UYMAZ -- böyle bir metin burada ayrıştırılamayıp doğal olarak VLM'e
    düşer, yanlış sıfır faz/frekans varsayılmaz.
    """
    match = _OCR_VALUE_RE.match(text.strip())
    if not match:
        return None
    number_str, unit = match.groups()
    # Birimsiz (cıplak sayı) TAMAMEN reddedilir -- bu domainde ders kitabı
    # şemalarında bir bileşen değeri HER ZAMAN birimle yazılır (Ω/V/A/F/H).
    # Birimsiz bir OCR sonucu = OCR birim sembolünü (Ω/kΩ vb.) kaybetmiş
    # demektir, ve bu genelde YALNIZ birimi değil RAKAMI DA bozar. GERCEK
    # VERIDE IKI AYRI ORNEKTE YAKALANDI (2026-08-21 denetimi): Figure 4.9
    # resistor5'in gercek etiketi "1 Ω" iken OCR hint'i cıplak "10" (10 kat
    # yanlis); Figure 2.27 resistor1'in gercek etiketi "6 Ω" iken OCR hint'i
    # cıplak "9" (yanlis rakam + birim ikisi de kayip). Eskiden yalnizca
    # birimsiz "0" reddediliyordu (Figure 2.23: "6 Ω" -> "0" okunup
    # ZeroDivisionError'a kadar gitmisti) -- ayni kirinti riski SIFIR
    # OLMAYAN birimsiz sayilarda da var, sadece daha sessiz (gecerli
    # gorunen ama yanlis bir deger uretiyor). VLM'e (gorsel baglami gorur)
    # birakiliyor, tahmin YAPILMAZ.
    if not unit:
        return None
    try:
        value = float(number_str) * _unit_multiplier(unit or None)
    except ValueError:
        return None
    return {"value": value, "phase_degrees": 0.0, "frequency_hz": None}


def read_component_value(image_base64: str) -> dict:
    """TEK bir bilesen kirpiminin degerini okur -- topolojiyle ilgilenmez.

    Neden ayri: `read_circuit_image` butun sahneyi tek seferde okuyup KENDI
    dugum/baglanti grafini de uretiyor -- degerde dogru cikarken (OLCULDU,
    Figure 2.8: 30V/5kOhm dogru okundu) topolojide halusinasyon gorebiliyor
    (ayni ornekte TEK direnci iki hayali direnc sandi). Bu fonksiyon o
    zaafi devreden tamamen cikarir: `devre-yolo-dedektor`'un YOLO+connectivity
    pipeline'i topolojiyi zaten dogru veriyor, VLM'den SADECE deger istenir
    -- her YOLO kutusu kendi kirpimiyla 1:1 eslenir, VLM'in kendi kurdugu
    dugum adlarina hic ihtiyac kalmaz, eslestirme belirsizligi ortadan kalkar.

    Donen: {"value": float|None, "phase_degrees": float, "frequency_hz": float|None}
    """
    raw = _call_vlm_with_prompt(image_base64, _VALUE_SYSTEM_PROMPT, "Bu elemanın değerini oku.")
    match = _VALUE_JSON_RE.search(raw)
    if not match:
        raise VLMReadError("VLM yanıtında JSON bulunamadı.", raw=raw)
    try:
        payload = json.loads(match.group(0))
    except json.JSONDecodeError as exc:
        raise VLMReadError(f"VLM yanıtı geçerli JSON değil: {exc}", raw=raw) from exc

    number = payload.get("number")
    value = None
    if number is not None:
        try:
            value = float(number) * _unit_multiplier(payload.get("unit"))
        except (TypeError, ValueError) as exc:
            raise VLMReadError(f"deger/birim okunamadi ({number!r}, {payload.get('unit')!r}): {exc}", raw=raw) from exc

    phase = payload.get("phase_degrees") or 0
    try:
        phase = float(phase)
    except (TypeError, ValueError) as exc:
        raise VLMReadError(f"Sayısal olmayan faz {phase!r}", raw=raw) from exc

    frequency = payload.get("frequency_hz")
    if frequency is not None:
        try:
            frequency = float(frequency)
        except (TypeError, ValueError) as exc:
            raise VLMReadError(f"Sayısal olmayan frequency_hz: {frequency!r}", raw=raw) from exc

    return {"value": value, "phase_degrees": phase, "frequency_hz": frequency}


_DEPENDENT_SYSTEM_PROMPT = """Sen bir devre şeması okuyucususun. Sana bağımlı (kontrollü)
bir kaynağın (baklava/eşkenar dörtgen gövdeli sembol) kırpılmış görüntüsü
verilecek. Üzerinde "2vx", "4Io" gibi bir KATSAYI + KONTROL DEĞİŞKENİ yazar
(değişken devrenin BAŞKA bir elemanının gerilimi/akımı, harfle başlar).

KURALLAR:
- "gain" alanına sayısal katsayıyı yaz (örn. "2vx" -> 2, "0.5Io" -> 0.5).
- "control_symbol" alanına kontrol değişkeninin ALT İNDİSİNİ yaz, KÜÇÜK
  HARFLE (örn. "Vx"/"vx" -> "x", "Io"/"i_o" -> "o").
- "control_is_current" alanına kontrol büyüklüğü bir AKIM ise (i/I ile
  başlıyorsa) true, GERİLİM ise (v/V ile başlıyorsa) false yaz.
- Emin olmadığın bir alanı UYDURMA — null bırak.

ÇIKTI BİÇİMİ — yalnızca şu JSON'u yaz, başka hiçbir şey yazma:
{"gain": 2, "control_symbol": "x", "control_is_current": false}"""


def read_dependent_source(image_base64: str) -> dict:
    """Bağımlı kaynağın KENDİ etiketini okur: katsayı + kontrol ettiği
    büyüklüğün adı (bkz. `_DEPENDENT_SYSTEM_PROMPT`).

    Bu, kontrol büyüklüğünün DEVREDEKİ HANGİ ELEMANA ait olduğunu SÖYLEMEZ
    -- yalnızca sembol/isim döner ("x", "o" gibi). O eşleştirme (hangi
    diğer elemanın yakınında "Vx"/"Io" etiketi var) `scripts/
    solve_from_extraction.py`'de, `devre-yolo-dedektor/extract_for_solve.py`
    `control_label_hint`'in ürettiği veriyle yapılır -- bu fonksiyon o
    eşleştirme için gereken YARIM bilgiyi sağlar.

    Donen: {"gain": float, "control_symbol": str, "control_is_current": bool}
    """
    raw = _call_vlm_with_prompt(
        image_base64, _DEPENDENT_SYSTEM_PROMPT, "Bu bağımlı kaynağın katsayısını ve kontrol değişkenini oku."
    )
    match = _VALUE_JSON_RE.search(raw)
    if not match:
        raise VLMReadError("VLM yanıtında JSON bulunamadı.", raw=raw)
    try:
        payload = json.loads(match.group(0))
    except json.JSONDecodeError as exc:
        raise VLMReadError(f"VLM yanıtı geçerli JSON değil: {exc}", raw=raw) from exc

    gain, symbol, is_current = payload.get("gain"), payload.get("control_symbol"), payload.get("control_is_current")
    if gain is None or not symbol or is_current is None:
        raise VLMReadError(f"bağımlı kaynak alanları eksik/null: {payload}", raw=raw)
    try:
        gain = float(gain)
    except (TypeError, ValueError) as exc:
        raise VLMReadError(f"Sayısal olmayan katsayı {gain!r}", raw=raw) from exc

    return {"gain": gain, "control_symbol": str(symbol).strip().lower(), "control_is_current": bool(is_current)}


_IMPEDANCE_SYSTEM_PROMPT = """Sen bir devre şeması okuyucususun. Sana bir empedans kutusunun
(dikdörtgen sembol, üzerinde "Z = 8+j6 Ω" ya da "10∠30° Ω" gibi karmaşık
bir değer yazan) kırpılmış görüntüsü verilecek.

KURALLAR:
- Değer DİKDÖRTGEN (kartezyen) biçimde yazılmışsa ("8+j6", "5-j3" gibi):
  "resistance" alanına gerçek kısmı (8), "reactance" alanına sanal kısmı
  (6; "-j3" ise -3) yaz, "magnitude"/"phase_degrees" alanlarını null bırak.
- Değer KUTUPSAL (polar) biçimde yazılmışsa ("10∠30°" gibi): "magnitude"
  alanına büyüklüğü (10), "phase_degrees" alanına açıyı (30) yaz,
  "resistance"/"reactance" alanlarını null bırak.
- Birim çevirisi YAPMA, hesap YAPMA — yazıda AYNEN ne varsa onu bildir.
- Emin olmadığın bir alanı UYDURMA, null bırak.

ÇIKTI BİÇİMİ — yalnızca şu JSON'u yaz, başka hiçbir şey yazma:
{"resistance": 8, "reactance": 6, "magnitude": null, "phase_degrees": null}"""


def read_impedance(image_base64: str) -> dict:
    """Empedans kutusunun değerini okur -- kartezyen (R+jX) ya da kutupsal
    (Z∠θ) HANGİSİ YAZILIYSA onu okur; VLM'e HESAP YAPTIRMADAN (bkz. modül
    docstring'i, `parse_ocr_value_hint`'teki aynı ilke), Python'da
    magnitude/phase_degrees'e çevrilir -- `app/circuit/ac.py`'nin
    `impedance()`/`_add_fixed_impedance()` fonksiyonlarının beklediği biçim.

    Dönen: {"value": float (büyüklük, Ω), "phase_degrees": float}
    """
    raw = _call_vlm_with_prompt(image_base64, _IMPEDANCE_SYSTEM_PROMPT, "Bu empedansın değerini oku.")
    match = _VALUE_JSON_RE.search(raw)
    if not match:
        raise VLMReadError("VLM yanıtında JSON bulunamadı.", raw=raw)
    try:
        payload = json.loads(match.group(0))
    except json.JSONDecodeError as exc:
        raise VLMReadError(f"VLM yanıtı geçerli JSON değil: {exc}", raw=raw) from exc

    resistance, reactance = payload.get("resistance"), payload.get("reactance")
    magnitude, phase = payload.get("magnitude"), payload.get("phase_degrees")

    if resistance is not None and reactance is not None:
        try:
            z = complex(float(resistance), float(reactance))
        except (TypeError, ValueError) as exc:
            raise VLMReadError(f"Sayısal olmayan direnç/reaktans: {resistance!r}/{reactance!r}", raw=raw) from exc
        return {"value": abs(z), "phase_degrees": math.degrees(cmath.phase(z))}
    if magnitude is not None and phase is not None:
        try:
            return {"value": float(magnitude), "phase_degrees": float(phase)}
        except (TypeError, ValueError) as exc:
            raise VLMReadError(f"Sayısal olmayan büyüklük/faz: {magnitude!r}/{phase!r}", raw=raw) from exc
    raise VLMReadError(f"empedans alanları eksik/null: {payload}", raw=raw)


_SWITCH_SYSTEM_PROMPT = """Sen bir devre şeması okuyucususun. Sana bir ANAHTAR
sembolünün (iki temas noktası arasında eğik bir kol/çizgi) kırpılmış
görüntüsü verilecek. Anahtar, ÇİZİLDİĞİ (t=0 ANINDAN ÖNCEKİ) durumda
AÇIK mı KAPALI mı?

KURALLAR:
- Kol iki temas noktasına da DEĞİYORSA (düz, kesintisiz bir çizgi gibi
  görünüyorsa) — KAPALI (true).
- Kol temas noktalarından birinden AYRIKSA (açı yapıyor, aralarında boşluk
  varsa) — AÇIK (false).
- Emin değilsen "closed" alanını null bırak, TAHMİN ETME.

ÇIKTI BİÇİMİ — yalnızca şu JSON'u yaz, başka hiçbir şey yazma:
{"closed": true}"""


def read_switch_state(image_base64: str) -> dict:
    """Anahtarın ÇİZİLDİĞİ (t=0 ÖNCESİ, "before") durumunu okur.

    t=0'da anahtar HER ZAMAN ters duruma geçer -- bu, "anahtarlı geçici
    rejim" probleminin kendi tanımı (bkz. `app/circuit/transient.py` modül
    docstring'i, Sadiku Fig. 7.43 "(a) t<0, (b) t≥0" örneği): burada
    okunan "before" durumu, "after" devrede TERSİ olarak kullanılır --
    bu fonksiyon yalnızca ÇİZİLEN (before) hali okur.

    Dönen: {"closed": bool} -- t<0 durumundaki hali.
    """
    raw = _call_vlm_with_prompt(image_base64, _SWITCH_SYSTEM_PROMPT, "Bu anahtar açık mı kapalı mı?")
    match = _VALUE_JSON_RE.search(raw)
    if not match:
        raise VLMReadError("VLM yanıtında JSON bulunamadı.", raw=raw)
    try:
        payload = json.loads(match.group(0))
    except json.JSONDecodeError as exc:
        raise VLMReadError(f"VLM yanıtı geçerli JSON değil: {exc}", raw=raw) from exc
    closed = payload.get("closed")
    if closed is None:
        raise VLMReadError(f"anahtar durumu belirsiz: {payload}", raw=raw)
    return {"closed": bool(closed)}


_CONTROL_TARGET_SYSTEM_PROMPT = """Sen bir devre şeması okuyucususun. Sana birden
fazla kırpılmış görüntü verilecek: İLK görüntü bağımlı (kontrollü) bir
kaynağın gövdesi (üzerinde "150iβ", "2vx" gibi bir KATSAYI+DEĞİŞKEN yazar).
SONRAKİ görüntüler (2, 3, 4...) devredeki DİĞER elemanlar, her biri
numaralandırılmış.

GÖREV: İlk görüntüdeki değişkenin alt indisiyle (harften SONRAKİ kısım,
örn. "iβ" -> "β") AYNI harf/sembolün yazılı olduğu elemanı numaralı
görüntüler arasından bul. Yunanca/Latin fark etmez, SADECE görsel olarak
AYNI karakter mi diye bak, anlamını değil.

KURALLAR:
- Kaç numaralı görüntüde o TAM sembol yazıyorsa o numarayı yaz.
- Hiçbirinde yoksa, birden fazlasında varsa, ya da emin değilsen "index"
  alanını null bırak -- TAHMİN ETME.

ÇIKTI BİÇİMİ — yalnızca şu JSON'u yaz, başka hiçbir şey yazma:
{"index": 2}"""


def read_control_variable_target(dependent_crop_b64: str, candidates: list[tuple[str, str]]) -> str | None:
    """Bagimli kaynagin kontrol degiskenini, METIN OKUMADAN, gorsel olarak
    hangi ADAY elemana ait oldugunu bularak coz.

    `control_label_hint` (devre-yolo-dedektor/extract_for_solve.py, EasyOCR
    tabanli) SADECE Latin alfabesini taniyor -- kutuphane Yunanca'yi (`el`)
    HIC DESTEKLEMIYOR (dogrulandi: `easyocr.Reader(['en','el'])` "is not
    supported" hatasi veriyor), OCR bu yuzden "iΔ" gibi bir etiketi asla
    bulamiyor, `_resolve_dependent_sources` "0 aday bulundu" ile
    reddediyordu. Once tek-tek kirpim okuyup METIN karsilastiran bir
    fallback denendi -- calisti ama kirpim cerceveleri birbirine yakin
    elemanlarda ORTUSTUGU icin (BULUNDU, 2026-08-24, 75.png/86.png: ayni
    "δ"/"β" birden fazla komsu kirpimda "gorulup" belirsizlik yaratti)
    tek basina yetmedi.

    Bu fonksiyon FARKLI bir strateji kullanir (kullanicinin onerisi): sembolu
    OKUYUP ANLAMAYA calismak yerine, TUM adaylari TEK bir cok-gorselli VLM
    cagrisinda yan yana koyup "hangisi gorsel olarak ayni karakter" diye
    sorar -- Ollama'nin chat API'si `images` alaninda BIRDEN FAZLA gorseli
    ayni mesajda kabul ediyor (minicpm-v coklu-gorsel destekliyor), bu
    yuzden ek bir kutuphane/model gerekmiyor. Karsilastirma piksel-gorsel
    seviyesinde oldugu icin OCR'in Yunanca kisitlamasindan tamamen bagimsiz.

    `candidates`: [(eleman_adi, kirpim_base64), ...] -- sirayla 2, 3, 4...
    olarak numaralandirilir (1 = bagimli kaynagin kendisi).

    Donen: eslesen adayin eleman adi, ya da bulunamadi/belirsizse None.
    """
    if not candidates:
        return None
    images = [dependent_crop_b64] + [b64 for _, b64 in candidates]
    numbered = "\n".join(f"{i + 2}: {name}" for i, (name, _) in enumerate(candidates))
    raw = _call_vlm_with_images(
        images, _CONTROL_TARGET_SYSTEM_PROMPT,
        f"1. görüntü bağımlı kaynak, aşağıdaki numaralar diğer elemanlar:\n{numbered}\nHangisi eşleşiyor?",
    )
    match = _VALUE_JSON_RE.search(raw)
    if not match:
        raise VLMReadError("VLM yanıtında JSON bulunamadı.", raw=raw)
    try:
        payload = json.loads(match.group(0))
    except json.JSONDecodeError as exc:
        raise VLMReadError(f"VLM yanıtı geçerli JSON değil: {exc}", raw=raw) from exc
    index = payload.get("index")
    if index is None:
        return None
    try:
        pos = int(index) - 2
    except (TypeError, ValueError) as exc:
        raise VLMReadError(f"Sayısal olmayan index {index!r}", raw=raw) from exc
    if not (0 <= pos < len(candidates)):
        return None
    return candidates[pos][0]


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
    return _call_vlm_with_prompt(image_base64, _SYSTEM_PROMPT, "Bu devre şemasındaki elemanları ve bağlantılarını çıkar.")


def _call_vlm_with_prompt(image_base64: str, system_prompt: str, user_text: str) -> str:
    return _call_vlm_with_images([image_base64], system_prompt, user_text)


def _call_vlm_with_images(images: list[str], system_prompt: str, user_text: str) -> str:
    """`_call_vlm_with_prompt` ile AYNI, ama birden fazla goruntu kabul eder --
    Ollama chat API'sindeki `images` alani zaten liste (bkz. minicpm-v'nin
    coklu-gorsel destegi), tek goruntulu cagri bunun ozel hali."""
    response = requests.post(
        OLLAMA_CHAT_URL,
        json={
            "model": VLM_MODEL,
            "messages": [
                {"role": "system", "content": system_prompt},
                {
                    "role": "user",
                    "content": user_text,
                    "images": images,
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

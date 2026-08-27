"""`devre-yolo-dedektor/extract_for_solve.py`'nin ciktisini (topoloji+kirpimlar)
okur, her kirpimin degerini VLM ile okur, `Netlist` kurup `solve_dc` ile cozer.

Neden IKI ASAMALI: bkz. `extract_for_solve.py` docstring'i -- gorme
(ultralytics/cv2) ve cozme (PySpice/ngspice) AYRI venv'lerde, JSON dosyasi
uzerinden aktariliyor.

Deger okuma TOPOLOJIYLE ILGILENMEZ (bkz. `app/vision/vlm_read.py`
`read_component_value` docstring'i): her YOLO kutusu kendi kirpimiyla 1:1
eslenir, VLM'in kendi kurdugu dugum adlarina hic ihtiyac kalmaz.

Ground (toprak) sembolu bir DEVRE ELEMANI degil, referans isaretidir:
degdigi TEK net "gnd" adiyla anilir (bkz. `app.circuit.solve.GROUND_NODES`),
kendisi Netlist'e eleman olarak eklenmez.
"""
from __future__ import annotations

import argparse
import base64
import cmath
import json
import math
import sys
from pathlib import Path

# Windows konsolu cp1254 -- gercek devre verisinde gecen "∠", Yunan harfleri
# ve "Ω" bu kod sayfasinda YOK ve print() UnicodeEncodeError ile COKUYOR
# (OLCULDU: fazorlu bir AC devrenin sonucunu yazdirirken). batch_solve.py'de
# ayni koruma zaten vardi, tek devrelik CLI yolunda yoktu.
for _stream in (sys.stdout, sys.stderr):
    if hasattr(_stream, "reconfigure"):
        _stream.reconfigure(errors="backslashreplace")

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.circuit.ac import element_results_ac, power_balance_ac, solve_ac  # noqa: E402
from app.circuit.netlist import Element, Netlist  # noqa: E402
from app.circuit.page_text import extract_frequency_hz, mentions_unsupported_element  # noqa: E402
from app.circuit.solve import (  # noqa: E402
    GROUND_NODES,
    ElementResult,
    SolverError,
    element_results,
    power_balance,
    solve_dc,
)
from app.circuit.theorems import thevenin_resistance  # noqa: E402
from app.circuit.topology import equivalent_impedance, equivalent_resistance  # noqa: E402
from app.circuit.transient import rc_step_response, rl_step_response  # noqa: E402
from app.vision.vlm_read import (  # noqa: E402
    VLMReadError,
    is_ohm_unit,
    looks_like_symbol_not_value,
    mentions_step_function,
    parse_ocr_value_hint,
    read_component_value,
    read_control_variable_target,
    read_dependent_source,
    read_impedance,
    read_switch_state,
    unit_implies_kind,
)

# YOLO/taxonomy sinif adi -> Netlist eleman turu. Kapsam disi kalanlar (diyot,
# transistor, transformator, op-amp, AC-fazor bagimli kaynak) BILEREK
# yok -- solve_dc/solve_ac yalnizca direnc+bagimsiz kaynak+kapasitor/bobin
# (+DC bagimli kaynak, +AC empedans kutusu, +TEK anahtarli gecici rejim)
# cozuyor, digerleri icin sessizce yanlis sonuc uretmek yerine acikca
# "desteklenmiyor" denir. "switch" burada da YOK -- KIND_MAP'teki gibi
# SABIT bir Netlist turune gitmiyor (asla kalici bir Element olmuyor),
# asagida ozel islenip BEFORE/AFTER netlist ciftine donusuyor (bkz. ana
# dongu sonrasindaki "ANAHTARLI GECICI REJIM" blogu). source_ac_sine bir
# GERILIM kaynagi (bkz. devre-yolo-dedektor/symbols.py draw_source_ac_sine)
# -- egitim verisinde +/- ayrimi yapilmadigi icin YOLO'nun kendisi polarite
# OGRENEMEDI, ama connectivity.py'deki _POLARITY_READERS artik source_v ile
# AYNI (SAF PIKSEL, YOLO'dan bagimsiz) source_orientation okuyucusunu
# kullaniyor -- gercek kitap sekli +/- ciziyorsa net sirasi dogru okunur,
# cizmiyorsa guvenli sekilde yonsuz kalir (2026-08-21 denetiminde eklendi,
# oncesinde bu sinif HIC bir okuyucuya sahip degildi). source_ac_i bir AKIM
# kaynagi (source_i ile ayni
# ok govdesi + sinus -- bkz. devre-yolo-dedektor/classes.py); daha once
# burada eksikti, source_i gibi cozulebilir oldugu halde "desteklenmiyor"
# diye reddediliyordu.
#
# "dependent_vcvs" burada YOK -- KIND_MAP'teki gibi SABIT bir Netlist turune
# gitmiyor, ayri bir ikinci gecişte cozuluyor (bkz. asagidaki
# _resolve_dependent_sources). Sebep: devre-yolo-dedektor'daki YOLO sinifi
# "dependent_vcvs" yalnizca SEMBOL SEKLINI (baklava + '+/-' = GERILIM ciktisi)
# tanimliyor, kontrol turunu (gerilim mi akim mi kontrol ediyor) DEGIL --
# o ancak etiketten (VLM: "2vx" -> gerilim-kontrollu, "4Io" -> akim-kontrollu)
# okunabilir, ayrica HANGI baska elemanin kontrol degiskenini tasidigi
# (control_label_hint ile) coz baglamde tekrar aranmali. "dependent_ccvs"
# YOLO sinifi (ok ucu = AKIM ciktisi, gercek VCCS/CCCS) BILEREK KIND_MAP'te
# yok -- netlist.py CIKISI AKIM olan bagimli kaynaklari (VCCS/CCCS) henuz
# desteklemiyor (bkz. o dosyanin ELEMENT_KINDS yorumu), bu YOLO tespit
# hatasi degil, gercek bir cozucu kapsam siniri.
#
# "impedance_box" da burada YOK, dependent_vcvs ile AYNI sebepten: deger
# okuma read_component_value'nun basit "sayi+birim" kalibina UYMUYOR --
# "8+j6 Ω" gibi karmasik bir ifade, ayri bir okuyucu (read_impedance) ve
# ayri bir parse/donusum (kartezyen -> buyukluk+faz) gerektiriyor (bkz.
# asagidaki ozel dal + app/vision/vlm_read.py read_impedance docstring'i).
# Saf fazor devresinde (tum reaktif elemanlar "jX Ω" olarak verilmis)
# cozum frekansi sonucu ETKILEMEZ -- ac.py her empedansi secilen frekansta
# tam o Z'yi verecek sekilde kuruyor. Yine de ngspice'a BIR frekans vermek
# gerekiyor; 50 Hz secildi (nots: deger tamamen keyfi, 1 Hz de olurdu --
# sadece "ders kitabi sebeke frekansi" olarak okunabilir olsun diye).
_PHASOR_REFERENCE_HZ = 50.0

# Kaynaksiz "Zeq bul" yolunda indirgenebilen eleman turleri (bkz.
# topology.equivalent_impedance) -- kaynak/bagimli kaynak varsa o yol gecersiz.
_PASSIVE_KINDS = ("resistor", "inductor", "capacitor", "impedance")

KIND_MAP = {
    "resistor": "resistor",
    "source_v": "voltage_source",
    "source_i": "current_source",
    "source_ac_sine": "voltage_source",
    "source_ac_i": "current_source",
    "capacitor": "capacitor",
    "inductor": "inductor",
}


class SolveFromExtractionError(RuntimeError):
    """Netlist kurulamadi ya da cozulemedi -- mesaj kullaniciya gosterilebilir."""


def _terminal_nodes(data: dict, netlist: Netlist, node_name) -> list[str]:
    """Kaynaksiz ("Req/Zeq bul") devrenin TERMINAL dugumleri.

    Once extraction'daki `open_end_nets` (SERBEST TEL UCU / terminal
    daireleri -- bkz. devre-yolo-dedektor/connectivity.py `_open_end_nets`)
    kullanilir. Bu, "o net'e kac ELEMAN degiyor" sezgisinden dogru olani:
    GERCEK VERIDE OLCULDU (Sadiku Figure 2.38) alt ray terminali "b" UC
    dirence degiyor, derece-1 DEGIL -- eski sezgi onu goremeyip devreyi
    tumuyle reddediyordu.

    `open_end_nets` yoksa (eski extraction dosyalari) eski derece-1
    sezgisine duser -- davranis degismez.
    """
    open_ends = data.get("open_end_nets")
    if open_ends:
        return [node_name(n) for n in open_ends]
    return netlist.dangling_nodes()


def _with_shorted(results: dict, shorted: list[tuple[str, str, str]]) -> dict:
    """Kisa devre edilmis elemanlari sonuclara ekler: V = 0, I = 0, P = 0.

    Guc dengesi HESAPLANDIKTAN SONRA eklenir -- sifir katkili olduklari icin
    dengeyi degistirmezler, ama ogrencinin sorusu tam da bu eleman olabilir
    (Test Sorulari/Soru3: "60 Ω direnc uzerindeki gerilim nedir" -> 0 V).
    """
    for name, kind, _node in shorted:
        results[name] = ElementResult(name=name, kind=kind, current=0.0, voltage=0.0, power=0.0)
    return results


def _control_is_current(dep: dict) -> bool:
    """Bagimli kaynak AKIM mi GERILIM mi kontrollu -- once ETIKET METNI, sonra bayrak.

    `control_is_current` bayragi VLM'in yorumu ve guvenilmez (OLCULDU,
    2026-08-25, 86.png: figurde "iβ" -- bir AKIM -- yaziyor, VLM "gerilim"
    dedi; yanlis tipte kaynak kurulur, power_balance ~0 cikar, cevap SESSIZCE
    yanlis olur). Ayni cagrida donen `control_symbol` metninin oneki ise
    dogrudan okunan yazidir: "i..." akim, "v..." gerilim. Onek varsa o
    kazanir; onek yoksa (orn. sadece "β") bayraga duseriz.
    """
    symbol = dep["control_symbol"]
    if symbol[:1] in ("i", "v"):
        return symbol[0] == "i"
    return bool(dep["control_is_current"])


def solve_extraction(data: dict, reference: str | None = None, verbose: bool = True) -> dict:
    """Tek bir extraction.json icerigini cozer.

    Donen: {"elements": [{"name","kind","value","nodes"}...], "results": {...},
    "power_balance": float}. Basarisizlikta `SolveFromExtractionError` firlatir
    (mesaj neden basarisiz oldugunu acikca soyler -- CLI'daki `raise SystemExit`
    ile ayni bilgiyi tasir, sadece toplu kosumda process durdurmak yerine
    yakalanabilir bir istisna olarak).
    """
    components: dict[str, dict] = data["components"]

    # KARSILIKLI ENDUKTANS: yan yana cizilmis sargi cifti (trafo ya da
    # "j1200 Ω" ile etiketlenmis kuplaj -- bkz. devre-yolo-dedektor/
    # extract_for_solve.py coupled_winding_pairs). Bu cozucu eslesmeyi
    # MODELLEMIYOR: iki bagimsiz bobin gibi cozerse butun degerler dogru
    # okunsa BILE cevap yanlis cikar, ustelik power_balance ~0 oldugu icin
    # sessizce (OLCULDU, 1-100/31.png: 9 degerin 9'u dogru okundu, cevap
    # yine de yanlisti ve "cozuldu" diye raporlandi).
    coupled = data.get("coupled_winding_pairs") or []
    if coupled:
        eslesmeler = ", ".join(f"{a}+{b}" for a, b in coupled)
        raise SolveFromExtractionError(
            f"karsilikli enduktans (yan yana sargi cifti: {eslesmeler}) -- bu cozucu "
            "kuplaji modellemiyor, bagimsiz bobin gibi cozmek sessizce yanlis cevap uretir"
        )

    # Sayfanin duz metni -- export_sadiku_test_set.py PNG'nin yanina ayni
    # adla .txt yaziyor (bkz. o script + app/circuit/page_text.py). Yoksa
    # (Fiore figurleri, ya da eski bir extraction) sessizce atlanir --
    # bu YEDEK bir kaynak, zorunlu degil.
    page_text = None
    image_path = data.get("image")
    if image_path:
        text_path = Path(image_path).with_suffix(".txt")
        if text_path.exists():
            page_text = text_path.read_text(encoding="utf-8")
    if page_text is not None:
        unsupported = mentions_unsupported_element(page_text)
        if unsupported is not None:
            raise SolveFromExtractionError(
                f"sayfa metninde {unsupported!r} geciyor -- bu devre turu desteklenmiyor "
                "(YOLO bu elemani tespit edemeyebilir, sessizce yanlis cozmek yerine reddediliyor)"
            )

    ground_net = None
    for comp in components.values():
        if comp["kind"] == "ground" and len(comp["nets"]) == 1:
            ground_net = comp["nets"][0]
            break

    def node_name(net_id: int) -> str:
        return "gnd" if net_id == ground_net else f"n{net_id}"

    elements = []
    element_log = []
    frequencies: dict[str, float] = {}
    # control_label_hint'i olan HER elemani (bagimli kaynak olsun olmasin --
    # kontrol degiskeni herhangi bir direnc/kaynagin uzerinde olabilir)
    # sembol -> (isim, dugumler) olarak topluyoruz; ayni sembol 2+ elemanda
    # gecerse ("Vo" iki yerde) BILEREK belirsiz sayilir (None), tahmin
    # yapilmaz -- bkz. _resolve_dependent_sources.
    control_targets: dict[str, list[tuple[str, tuple[str, str]]]] = {}
    pending_dependent: list[dict] = []
    # Anahtar (switch) bir DEVRE ELEMANI degil -- gecici rejim (transient)
    # dispatch'inin BEFORE/AFTER netlist'lerini kurmak icin gereken bir
    # DURUM bilgisi (bkz. asagidaki, ana dongu SONRASI islenen blok).
    switches: list[dict] = []
    # Uzerinden tel gecirilmis (iki ucu ayni dugumde) elemanlar.
    shorted: list[tuple[str, str, str]] = []
    # Ω ile yazildigi icin reaktansa cevrilen bobin/kondansatorler -- gecici
    # rejimde (anahtarli devre) bu FIZIKSEL OLARAK IMKANSIZ, asagida kontrol
    # edilir (bkz. "if switches:" blogu).
    reactance_reads: list[str] = []
    for name, comp in components.items():
        kind = comp["kind"]
        if kind == "ground":
            continue
        nets = comp["nets"]
        if len(nets) != 2:
            raise SolveFromExtractionError(
                f"{name}: {len(nets)} net'e degiyor, 2 bekleniyor (extraction.json'daki uyarilara bak)"
            )
        node_pair = (node_name(nets[0]), node_name(nets[1]))

        # KISA DEVRE: iki ucu da AYNI dugumde olan eleman (uzerinden tel
        # gecirilmis). Bu bir cikarim hatasi degil, devrenin kendisi --
        # GERCEK VERI (Test Sorulari/Soru3): 60 Ω direncin ustunden gecen
        # tel onu kisa devre ediyor ve sorunun cevabi da bu: gerilim 0 V.
        # Boyle bir eleman netlist'e KONULAMAZ (iki ucu ayni dugum) ama
        # sonuclarda gorunmeli: uzerindeki gerilim 0, akimi 0.
        if node_pair[0] == node_pair[1]:
            shorted.append((name, KIND_MAP.get(kind, kind), node_pair[0]))
            if verbose:
                print(f"  {name} ({kind}): KISA DEVRE -- iki ucu da {node_pair[0]} dugumunde (V = 0)")
            continue

        if kind in ("dependent_vcvs", "dependent_ccvs"):
            # control_search_crop kullanilir: katsayi ("0.5i" gibi) cogu
            # zaman elmasin GOVDESINDE degil, YANINDA yazili -- OLCULDU
            # (Test Sorulari/Soru12): dar kirpim "0.5i"yi TAMAMEN disarida
            # birakiyordu, VLM sembolu goruyor ama yaziyi goremeyince
            # katsayi/kontrol degiskenini UYDURUYORDU (gain=1,
            # control_symbol="null" -- sessizce yanlis, hata da vermiyordu).
            image_b64 = base64.b64encode(
                Path(comp.get("control_search_crop", comp["crop"])).read_bytes()
            ).decode()
            try:
                dep = read_dependent_source(image_b64)
            except VLMReadError as exc:
                raise SolveFromExtractionError(f"{name}: bagimli kaynak okunamadi -- {exc}") from exc
            # YOLO sinifi CIKISIN turunu soyler (baklava icinde +/- = GERILIM,
            # ok = AKIM); kontrolun turunu ise etiket metni soyler. Ikisi
            # BIRBIRINDEN BAGIMSIZ ve dordu de gercek bir eleman turudur
            # (vcvs/ccvs/vccs/cccs) -- asagidaki ikinci geciste birlestirilir.
            pending_dependent.append(
                {"name": name, "nodes": node_pair, "current_output": kind == "dependent_ccvs", **dep}
            )
            if verbose:
                gain, sym = dep["gain"], dep["control_symbol"]
                kontrol = "akim" if _control_is_current(dep) else "gerilim"
                cikis = "akim" if kind == "dependent_ccvs" else "gerilim"
                print(f"  {name} ({kind}): {cikis} cikisi = {gain:g} * {kontrol}({sym})"
                      f"  [{node_pair[0]} <-> {node_pair[1]}]")
            continue

        if kind == "impedance_box":
            image_b64 = base64.b64encode(Path(comp["crop"]).read_bytes()).decode()
            try:
                reading = read_impedance(image_b64)
            except VLMReadError as exc:
                raise SolveFromExtractionError(f"{name}: empedans okunamadi -- {exc}") from exc
            elements.append(
                Element(name=name, kind="impedance", nodes=node_pair, value=reading["value"], phase=reading["phase_degrees"])
            )
            element_log.append({"name": name, "kind": "impedance", "value": reading["value"], "nodes": node_pair})
            if verbose:
                print(f"  {name} (impedance): {reading['value']:g} Ω ∠ {reading['phase_degrees']:g}°  [{node_pair[0]} <-> {node_pair[1]}]")
            continue

        if kind == "switch":
            image_b64 = base64.b64encode(Path(comp["crop"]).read_bytes()).decode()
            try:
                state = read_switch_state(image_b64)
            except VLMReadError as exc:
                raise SolveFromExtractionError(f"{name}: anahtar durumu okunamadi -- {exc}") from exc
            switches.append({"name": name, "nodes": node_pair, "closed_before": state["closed"]})
            if verbose:
                durum = "kapali" if state["closed"] else "acik"
                print(f"  {name} (switch): t<0'da {durum}  [{node_pair[0]} <-> {node_pair[1]}]")
            continue

        # BAGIMLI kaynagin KENDI govdesindeki etiket ("2vx") burada
        # KAYDEDILMEZ -- bir bagimli kaynak asla baska bir bagimli kaynagin
        # kontrol hedefi OLAMAZ (bu domainde). OLCULDU (Figure 4_21): bu
        # kontrol olmadan dependent_vcvs1'in KENDI "x" etiketi de adaylara
        # karisip gercekte TEK olan eslesmeyi (resistor1/resistor3'ten
        # sadece biri gercek hedef) yapay olarak belirsizlestiriyordu.
        label = comp.get("control_label_hint")
        if label:
            control_targets.setdefault(label, []).append((name, node_pair))

        mapped = KIND_MAP.get(kind)
        if mapped is None:
            raise SolveFromExtractionError(f"{name} ({kind}): bu tur henuz desteklenmiyor, cozulemez")

        # DEGERIN KAYNAGI: bu elemana ATANAN etiket (bkz. devre-yolo-dedektor/
        # label_assign.py -- global, esiksiz atama). "Kirpimda ne gorunuyorsa
        # o" yaklasimi BIRAKILDI: kirpim sinirlari cizim olcegine gore
        # degistigi icin komsunun etiketi iceri girip sessizce yanlis deger
        # uretiyordu (OLCULDU: 1-100/11.png, Figure 2.10).
        #
        # Etiketin metni deterministik ayristirilabiliyorsa VLM HIC
        # CAGRILMAZ. Ayristirilamiyorsa (OCR "Ω"yi "0" okumus olabilir) VLM'e
        # ETIKETIN KENDI KIRPIMI gonderilir -- icinde tek bir yazi vardir,
        # "hangi degeri okuyayim" belirsizligi yapisal olarak yoktur.
        ocr_hint = comp.get("ocr_value_hint")
        reading = parse_ocr_value_hint(ocr_hint) if ocr_hint else None
        if reading is not None and verbose:
            print(f"  {name}: etiketten dogrudan okundu ({ocr_hint!r}), VLM atlandi")
        if reading is None:
            label_crop = comp.get("value_label_crop")
            if label_crop is None:
                raise SolveFromExtractionError(
                    f"{name}: bu elemana hicbir deger etiketi eslesmedi -- sekilde degeri "
                    "yazmiyor olabilir (sembolik devre) ya da OCR etiketi bulamamis"
                )
            image_b64 = base64.b64encode(Path(label_crop).read_bytes()).decode()
            try:
                reading = read_component_value(image_b64)
            except VLMReadError as exc:
                raise SolveFromExtractionError(f"{name}: VLM deger okuyamadi -- {exc}") from exc
        # ISIM SAYI SANILDI MI: VLM "I2"yi 12, "I1"i 11 diye dondurebiliyor
        # (OLCULDU, 132-170/164.png -- iki kaynak degeri de uydurmaydi, devre
        # yine de "cozuldu"). Ham yazi bir ISIM ise okunan sayi gecersizdir.
        # BIRIM BASAMAK (step) KAYNAK: "16u0(t) A" zamana bagli bir kaynaktir,
        # DC calisma noktasi gibi cozmek yanlis cevap uretir -- OLCULDU
        # (101-131/106.png, 109.png): sabit 16 A / 9 mA sanilip "cozuldu".
        # Gecici rejim yolu (transient.py) TEK anahtar + TEK depolama elemani
        # icin yazilmis, basamak kaynagi kapsaminda degil.
        if mentions_step_function(reading.get("text")):
            raise SolveFromExtractionError(
                f"{name}: birim basamak kaynagi ({reading['text']!r}) -- zamana bagli, "
                "bu yolda desteklenmiyor (DC calisma noktasi gibi cozmek yanlis olur)"
            )
        if looks_like_symbol_not_value(reading.get("text")):
            raise SolveFromExtractionError(
                f"{name}: kirpimda deger degil bir ISIM yaziyor ({reading['text']!r}) -- "
                "sembolik devre ya da etiket kirpima girmemis; sayi uydurulmadi"
            )
        if reading["value"] is None:
            # Iki AYRI durum ayni mesaji aliyordu (OLCULDU, 2026-08-25, 121
            # null vakasinin kirpimlari incelendi): (1) sekilde gercekten
            # sayi YOK -- deger yerine sembol yazili (Figure 2.29 "R2/v2",
            # 2.19 "v4", 2.18 "I3"): bu devre SEMBOLIKTIR, null DOGRU
            # cevaptir, okuma hatasi degildir; (2) sayi var ama okunamadi.
            # Ikisini ayirmadan "elle girilmeli" demek kullaniciyi olmayan
            # bir hatayi aramaya gonderiyordu.
            raise SolveFromExtractionError(
                f"{name}: sayisal deger okunamadi -- sekilde deger yerine SEMBOL yaziyorsa "
                "(R1, v_o, I3 gibi) devre semboliktir ve sayisal cozulemez; sayi yaziliysa "
                "okuma basarisiz, elle girilmeli"
            )
        if reading["frequency_hz"] is not None:
            frequencies[name] = reading["frequency_hz"]

        # FAZOR BOLGESI: bir bobinin/kondansatorun degeri Ω ile yazilmissa o
        # bir INDUKTANS/KAPASITANS DEGIL, REAKTANStir ("j2 Ω" / "-j16 Ω" --
        # Sadiku Bolum 9-11'de standart gosterim). Boyle bir eleman zaten
        # var olan `impedance` turune cevrilir: buyukluk = okunan sayi, faz
        # = bobinde +90°, kondansatorde -90° (isaretin kendisi YOLO'nun
        # sembol sinifindan gelir -- "j" mi "-j" mi oldugunu ayrica okumaya
        # gerek yok, bobin her zaman +jX, kondansator her zaman -jX).
        #
        # BULUNDU (2026-08-25, Devre Fotoları 1-100/28.png): bu ayrim
        # yokken j2Ω -> 2 HENRY, -j16Ω -> 16 FARAD okunuyordu ve devrede
        # hic frekans yazmadigi icin DC saniliip kondansator acik devre /
        # bobin kisa devre olarak cozulecekti -- sessizce, tamamen yanlis.
        value = reading["value"]
        if mapped in ("inductor", "capacitor") and is_ohm_unit(reading.get("unit")):
            mapped, kind_label = "impedance", f"{kind}->impedance"
            phase = 90.0 if kind == "inductor" else -90.0
            # VLM "-j16 Ω" icin sayiyi -16 dondurebiliyor (eksi isareti
            # okuyup birlikte veriyor). Isaret ZATEN sembol sinifindan
            # geliyor (faz +90/-90); negatif buyukluk birakmak isareti IKI
            # KEZ uygulayip kapasitifi induktife CEVIRIR -- sessizce yanlis
            # devre. Buyukluk her zaman pozitif.
            value = abs(value)
            reactance_reads.append(name)
        else:
            kind_label, phase = kind, reading["phase_degrees"]
            # BIRIM <-> SINIF CELISKISI: etiketteki birim YOLO'nun sembol
            # sinifiyla uyusmuyorsa (kondansator sanilan bir sembolde "30 V",
            # gerilim kaynagi sanilan bir sembolde "1 A") biri yanlis ve
            # etiket daha guclu kanittir -- ama HANGI ucun arti oldugu
            # (kaynak yonu) sembolden gelir, o yuzden sessizce tur
            # DEGISTIRMEK de yanlis isaretli bir cevap uretebilir.
            # OLCULDU (2026-08-25 kosusu): 132-170/154.png'de "30 V" pil
            # kondansator sinifina dusup 30 FARAD olarak, 1-100/51.png'de
            # "1 A" akim kaynagi gerilim kaynagi olarak cozuldu -- ikisi de
            # "basarili" raporlandi, guc dengesi 0 cikti, cevap yanlis.
            implied = unit_implies_kind(reading.get("unit"))
            if implied is not None and implied != mapped:
                raise SolveFromExtractionError(
                    f"{name}: sembol '{kind}' olarak taninmis ama etiketin birimi "
                    f"({reading['unit']!r}) '{implied}' diyor -- biri yanlis, sessizce "
                    "cozmek yerine duruluyor (elemani elle duzeltin)"
                )

        elements.append(Element(name=name, kind=mapped, nodes=node_pair, value=value, phase=phase))
        element_log.append({"name": name, "kind": mapped, "value": value, "nodes": node_pair})
        if verbose:
            print(f"  {name} ({kind_label}): {value:g}  [{node_pair[0]} <-> {node_pair[1]}]")

    # IKINCI GECIS: her bekleyen bagimli kaynak icin, control_symbol'unu
    # TASIYAN TEK elemani control_targets'tan bul (bkz. yukaridaki toplama
    # ve modul basindaki KIND_MAP yorumu). GERCEK VERIDE DOGRULANDI (Fiore
    # Figure 2.23): dependent_vcvs govdesinde "2vo" yaziyor, resistor1'in
    # KENDI kirpiminda ayrica "+ vo -" etiketi var -- OCR bunu "Vo" olarak
    # ayirt edilebilir sekilde buluyor (bkz. devre-yolo-dedektor/
    # extract_for_solve.py control_label_hint).
    for dep in pending_dependent:
        symbol = dep["control_symbol"]
        matches = control_targets.get(symbol, [])
        if not matches:
            # OCR eslesmesi sifir -- BULUNDU (2026-08-24): en sık sebep
            # Yunanca kontrol degiskeni (EasyOCR Yunanca'yi HIC desteklemiyor,
            # bkz. read_control_variable_target docstring'i), ama ASCII
            # sembolde de OCR kacirabiliyor. Yedek yol: her aday kirpima
            # "bu goruntude 'ix' yaziyor mu" diye TEK TEK sorup TEK isabet
            # arıyoruz -- OCR/dil kisitindan tamamen bagimsiz.
            #
            # Aranan sey SADECE ALT INDIS ("x", "δ"): read_dependent_source
            # bazen alt indisi ("δ"), bazen tam adi ("i_δ") donuyor (OLCULDU,
            # 38.png) -- oneki soyup tek bicime getiriyoruz. Onek ARAMAYA
            # KATILMIYOR, cunku control_is_current bayragi guvenilmez (bkz.
            # crop_has_label docstring'i, 86.png).
            core = symbol[2:] if symbol[:2] in ("i_", "v_") else (
                symbol[1:] if symbol[:1] in ("i", "v") and len(symbol) > 1 else symbol
            )
            candidates = [
                (name, comp)
                for name, comp in components.items()
                if comp["kind"] not in ("ground", "dependent_vcvs", "dependent_ccvs", "switch")
                and len(comp["nets"]) == 2
            ]
            try:
                # DENENDI, GERI ALINDI (Test Sorulari/Soru12, 2026-08-27):
                # control_search_crop (genis kirpim) burada kullanilinca
                # komsu bir bagimli kaynagin KENDI katsayi yazisi ("0.5i")
                # de kirpima giriyor ve VLM "i" var diye orayi da isaretliyor
                # -- iki aday (dogru eleman + komsu) 1 yerine, "TEK olmali"
                # reddediyor. 3 farkli prompt denendi, kucuk VLM (8B) katsayi
                # ile bagimsiz kontrol harfini guvenilir ayiramadi. Dar kirpim
                # (c["crop"]) bu belirsizligi yaratmiyor, riskli kazanc
                # yerine BILINEN davranis tercih edildi.
                found = read_control_variable_target(
                    core,
                    [(name, base64.b64encode(Path(c["crop"]).read_bytes()).decode()) for name, c in candidates],
                )
            except VLMReadError:
                found = None
            if found is not None:
                comp = components[found]
                matches = [(found, (node_name(comp["nets"][0]), node_name(comp["nets"][1])))]
        if len(matches) != 1:
            raise SolveFromExtractionError(
                f"{dep['name']}: kontrol degiskeni {symbol!r} icin {len(matches)} aday bulundu "
                f"(TEK olmali) -- {matches}"
            )
        control_name, control_nodes = matches[0]
        if _control_is_current(dep):
            netlist_kind = "cccs" if dep.get("current_output") else "ccvs"
            extra = {"control_element": control_name}
        else:
            netlist_kind = "vccs" if dep.get("current_output") else "vcvs"
            extra = {"control_nodes": control_nodes}
        elements.append(
            Element(name=dep["name"], kind=netlist_kind, nodes=dep["nodes"], value=dep["gain"], **extra)
        )
        element_log.append(
            {"name": dep["name"], "kind": netlist_kind, "value": dep["gain"], "nodes": dep["nodes"],
             "control": control_name}
        )

    # ANAHTARLI GECICI REJIM (transient) -- normal DC/AC dispatch'ten TAMAMEN
    # AYRI bir mod, o yuzden burada erken donuyor. Sadiku Bolum 7'nin
    # tanimi geregi TEK anahtar + TEK depolama elemani (kapasitor YA DA
    # bobin, ikisi birden degil -- o "ikinci derece" olur, ayri bir konu,
    # burada desteklenmiyor). `app/circuit/transient.py`'nin BEFORE/AFTER
    # netlist mantigi (bkz. o modulun docstring'i) burada kullanilir:
    # anahtarin CIZILI (t<0) durumu kapaliysa iki ucu BIRLESTIRILIR (tel),
    # aciksa hic eklenmez (kopuk) -- t>=0'da (after) TERSI uygulanir.
    if switches:
        # Gecici rejim ZAMAN BOLGESIDIR: bir bobinin/kondansatorun degeri H/F
        # cinsindendir, reaktans (Ω) diye bir sey YOKTUR (reaktans ancak
        # sinusoidal kararli hal/fazor bolgesinde tanimli). Boyle bir okuma
        # geldiyse deger YANLIS okunmustur (OLCULDU, 133.png: bobinin degeri
        # "667 kΩ" okundu) -- sessizce yanlis cozmek yerine acikca durur.
        if reactance_reads:
            raise SolveFromExtractionError(
                f"{', '.join(reactance_reads)}: anahtarli (gecici rejim) devrede deger Ω olarak "
                "okundu -- zaman bolgesinde reaktans tanimsiz, H/F bekleniyor; okuma hatali, elle girilmeli"
            )
        if len(switches) != 1:
            raise SolveFromExtractionError(
                f"{len(switches)} anahtar bulundu -- su an yalnizca TEK anahtarli devreler destekleniyor"
            )
        switch = switches[0]
        node_a, node_b = switch["nodes"]
        # "gnd" HER ZAMAN hayatta kalmali -- BULUNDU (test sirasinda,
        # 2026-08-24): hangi net'in nets[0]/nets[1] oldugu YOLO/connectivity
        # siralamasina bagli, "gnd" bazen node_b olup SILINEBILIYORDU (asagida
        # her zaman node_b elenir) -- devrede referans dugum tumden
        # kayboluyor, solve_dc "referans yok" hatasi veriyordu.
        if node_b.lower() in GROUND_NODES:
            node_a, node_b = node_b, node_a

        def _merged(els: list[Element], old: str, new: str) -> list[Element]:
            return [
                Element(
                    name=e.name,
                    kind=e.kind,
                    nodes=tuple(new if n == old else n for n in e.nodes),
                    value=e.value,
                    control_nodes=(
                        tuple(new if n == old else n for n in e.control_nodes)
                        if e.control_nodes is not None
                        else None
                    ),
                    control_element=e.control_element,
                    phase=e.phase,
                )
                for e in els
            ]

        if switch["closed_before"]:
            before_elements, after_elements = _merged(elements, node_b, node_a), elements
        else:
            before_elements, after_elements = elements, _merged(elements, node_b, node_a)

        capacitors = [e.name for e in elements if e.kind == "capacitor"]
        inductors = [e.name for e in elements if e.kind == "inductor"]
        if len(capacitors) == 1 and not inductors:
            reactive_name, solver = capacitors[0], rc_step_response
        elif len(inductors) == 1 and not capacitors:
            reactive_name, solver = inductors[0], rl_step_response
        else:
            raise SolveFromExtractionError(
                f"gecici rejim icin TAM OLARAK 1 kapasitor YA DA 1 bobin gerekiyor "
                f"(bulunan: {len(capacitors)} kapasitor, {len(inductors)} bobin -- "
                "ikisi birden 'ikinci derece' devre olur, henuz desteklenmiyor)"
            )

        try:
            response = solver(Netlist(before_elements), Netlist(after_elements), reactive_name, reference=reference)
        except SolverError as exc:
            raise SolveFromExtractionError(f"gecici rejim cozulemedi: {exc}") from exc
        if verbose:
            print(f"  (anahtarli gecici rejim -- {switch['name']} t=0'da durum degistiriyor)")
            print(f"  {response.describe()}")
        return {"elements": element_log, "results": {"gecici_yanit": response}, "power_balance": 0.0}

    # Bir devrede frekans yazılıysa (VLM en az bir kaynakta "f=..."
    # okuduysa) devre AC'dir -- kapasitör/bobin artık açık/kısa devre
    # değil, empedanslı fazör çözümü gerekir (bkz. app/circuit/ac.py).
    # Frekans TEK olmalı: aynı devrede iki farklı kaynak frekansı fiziksel
    # olarak anlamsız (bu çözücü/kitap kapsamında iki frekanslı analiz yok).
    distinct = set(frequencies.values())
    if len(distinct) > 1:
        raise SolveFromExtractionError(f"devrede birden fazla farkli frekans okundu: {frequencies}")

    # YEDEK: hicbir bilesenin kirpiminda frekans yoksa ama devrede reaktif
    # eleman (kapasitor/bobin/empedans kutusu) varsa, sayfa metninde bir
    # frekans ifadesi olabilir (bkz. app/circuit/page_text.py modul
    # docstring'i -- OLCULDU, Sadiku'da kural bu: frekans hemen hic sema
    # uzerinde yazmiyor). Bu bir SEZGI (sayfada birden fazla problem
    # olabilir) -- yalnizca semanin KENDISI hicbir sey vermediginde
    # devreye giriyor. "impedance" de BURAYA DAHIL -- read_impedance hic
    # frekans okumaz (Z zaten sabit, frekanstan bagimsiz -- bkz. ac.py
    # impedance() docstring'i), yani SADECE impedans kutusu iceren bir AC
    # devrede frekans HER ZAMAN bu yedekten gelmek zorunda.
    has_reactive = any(e.kind in ("capacitor", "inductor", "impedance") for e in elements)
    if not distinct and has_reactive and page_text is not None:
        page_freq = extract_frequency_hz(page_text)
        if page_freq is not None:
            distinct = {page_freq}
            if verbose:
                print(f"  (frekans semada yok, sayfa metninden alindi: {page_freq:g} Hz)")

    # SAF FAZOR DEVRESI: butun reaktif elemanlar `impedance` (yani semada
    # zaten "jX Ω" olarak verilmis) ise devre FAZOR BOLGESINDEDIR ve
    # frekansa HIC IHTIYAC YOKTUR -- empedanslar dogrudan biliniyor.
    # ac.py'nin `_add_fixed_impedance`'i her empedansi COZUM FREKANSINDA
    # tam o Z'yi verecek R+L/C'ye ceviriyor, yani hangi frekansi sectigimiz
    # sonucu DEGISTIRMEZ (bkz. ac.py impedance() docstring'i + o modulun
    # "frekanstan bagimsiz" testi).
    #
    # Sart BILEREK dar: H/F cinsinden GERCEK bir bobin/kondansator varsa
    # frekans sonucu degistirir, o zaman uydurmak YASAK -- eskisi gibi
    # sayfa metni/sema frekansi sart kalir.
    #
    # FAZLI KAYNAK da ayni gerekce: "150∠30° V" yazan bir kaynak fazor
    # bolgesindedir. Devre SADECE dirençliyse eskiden hic reaktif eleman
    # olmadigi icin DC yoluna dusuyordu ve faz SESSIZCE atiliyordu
    # (solve_dc fazi hic bilmez) -- akimlarin acisi 0 sanilip yanlis
    # cevap uretiliyordu.
    phased_source = any(
        e.kind in ("voltage_source", "current_source") and (e.phase or 0.0) != 0.0
        for e in elements
    )
    if (
        not distinct
        and (any(e.kind == "impedance" for e in elements) or phased_source)
        and not any(e.kind in ("capacitor", "inductor") for e in elements)
    ):
        distinct = {_PHASOR_REFERENCE_HZ}
        if verbose:
            print("  (saf fazor devresi -- empedanslar/fazlar verilmis, frekans gerekmiyor)")

    netlist = Netlist(elements)

    # Kaynaksiz devre: "Req/Geq bul" tarzi sorular (Fiore/Sadiku'da sik) --
    # bunlar gecersiz DEGIL, sadece nodal-analiz + kaynak yerine seri/paralel
    # (+ yildiz-ucgen) indirgeme ister (bkz. app/circuit/topology.py
    # equivalent_resistance, ayni fonksiyon theorems.py'de Thevenin direnci
    # icin de kullaniliyor). Devrenin acik uclari = tam olarak 1 elemana
    # deyen (derece-1) iki net; digerleri (0, 1 veya 3+ ucuk) belirsiz
    # sayilir, tahmin edilmez.
    has_source = any(e.kind in ("voltage_source", "current_source", "vcvs", "ccvs") for e in elements)
    if not has_source:
        if elements and all(e.kind == "resistor" for e in elements):
            # AYNI sifir-deger riski burada da var (BULUNDU, 2026-08-21
            # denetimi, gercek cagriyla dogrulandi: iki 0 Ω direnc paralel
            # olunca _parallel_value'nin (r1*r2)/(r1+r2) hesabi 0/0 ile
            # coker) -- solve_dc/solve_ac'teki AYNI koruma burada YOKTU,
            # cunku bu yol o fonksiyonlara hic ugramiyor.
            zero_valued = [e.name for e in elements if e.value == 0]
            if zero_valued:
                raise SolveFromExtractionError(
                    f"{', '.join(zero_valued)}: direnç değeri 0 -- muhtemelen okuma hatası, çözülemez"
                )
            # dangling_nodes() Netlist'in KENDI derece-1 hesabi -- burada
            # AYNI mantigi elle tekrar yazmak yerine onu kullaniyoruz
            # (BULUNDU, 2026-08-21 denetimi: eskiden burada elle bir
            # degree-dict kuruluyordu, netlist.py'deki dangling_nodes()'un
            # BIREBIR kopyasiydi).
            terminals = _terminal_nodes(data, netlist, node_name)
            if len(terminals) == 2:
                req = equivalent_resistance(netlist, terminals[0], terminals[1])
                if req is not None:
                    if verbose:
                        print(f"  (kaynaksiz devre -- {terminals[0]}-{terminals[1]} arasi esdeger direnc)")
                        print(f"  R_esdeger = {req:g} Ohm")
                    return {
                        "elements": element_log,
                        "results": {"esdeger_direnc_ohm": req, "terminals": terminals},
                        "power_balance": 0.0,
                    }
        # KAYNAKSIZ, TEK DEPOLAMA ELEMANLI devre: "zaman sabitini bulun" tarzi
        # sorular (Sadiku Bolum 7, Test Sorulari/Soru11) -- ne kaynak ne
        # anahtar var, sadece direncler + TEK bobin/kondansator. tau = R_th*C
        # (kondansator) ya da L/R_th (bobin); R_th depolama elemani
        # CIKARILMIS devrede, onun eski uclarindan Thevenin direnci --
        # transient.py'nin anahtarli akista zaten kullandigi AYNI yontem
        # (_thevenin_resistance_without), burada anahtar/before-after
        # olmadan DOGRUDAN uygulanir. IKI depolama elemani varsa (RLC,
        # ikinci derece) BILEREK reddedilir -- bu cozucu birinci derece
        # icin yazildi, ikinci derece farkli bir denklem gerektirir.
        # Bu dal SADECE devrenin ACIK IKI UCU YOKSA (kapali, kendi icinde
        # tam bir ag) devreye girer -- iki acik ucu OLAN devreler zaten
        # "Zeq/Req bul" sorusudur (asagidaki mevcut yollar), onlarla
        # KARISTIRILMAMALI. OLCULDU (test_sourceless_ac_circuit_returns_
        # equivalent_impedance, test_sourceless_real_lc_without_frequency_
        # refuses): ikisi de tek reaktif eleman + direnc ama IKI ACIK UCU
        # var -- bu dal onlari yanlislikla yakalayip Zeq yerine tau
        # dondurmemeli.
        reactive = [e for e in elements if e.kind in ("capacitor", "inductor")]
        terminals_probe = _terminal_nodes(data, netlist, node_name)
        if (
            len(terminals_probe) != 2
            and len(reactive) == 1
            and all(e.kind in ("resistor", "capacitor", "inductor") for e in elements)
        ):
            storage = reactive[0]
            remaining = Netlist([e for e in elements if e.name != storage.name])
            node_a, node_b = storage.nodes
            # thevenin_resistance kendi ic solve_dc'si icin bir referans
            # dugume ihtiyac duyar -- ana akistaki OTOMATIK referans secimi
            # (asagida, "sekilde toprak yok" bloğu) bu daldan SONRA calisiyor,
            # burada erken donuldugu icin AYNI mantik tekrarlanir.
            tau_reference = reference
            if tau_reference is None and not any(
                node in GROUND_NODES for e in remaining.elements for node in e.nodes
            ):
                tau_reference = sorted({node for e in remaining.elements for node in e.nodes})[0]
            try:
                r_th = thevenin_resistance(remaining, node_a, node_b, reference=tau_reference)
            except SolverError as exc:
                raise SolveFromExtractionError(
                    f"{storage.name} cikarilmis devrede Thevenin direnci bulunamadi: {exc}"
                ) from exc
            if storage.kind == "capacitor":
                tau = r_th * storage.value
            elif r_th == 0:
                raise SolveFromExtractionError(
                    f"{storage.name}: Thevenin direnci 0 -- zaman sabiti (L/R) tanimsiz"
                )
            else:
                tau = storage.value / r_th
            if verbose:
                print(f"  (kaynaksiz devre, tek depolama elemani -- zaman sabiti tau = {tau:g} s)")
            return {
                "elements": element_log,
                "results": {"zaman_sabiti_s": tau, "depolama_elemani": storage.name},
                "power_balance": 0.0,
            }

        # KAYNAKSIZ AC ("Zeq bul"): reaktif eleman varsa esdeger DIRENC degil
        # esdeger EMPEDANS aranir -- ayni seri/paralel/Y-Δ kurallari, kompleks
        # sayilarla (bkz. topology.equivalent_impedance). OLCULDU (14.png,
        # 48.png, Figure 9.81): ucu de sirf "hepsi resistor degil" diye
        # reddediliyordu.
        # FREKANS SARTI: H/F cinsinden GERCEK bir bobin/kondansator varsa
        # Zeq FREKANSA BAGLIDIR -- frekans bilinmiyorken bir sayi uretmek
        # (fazor referans frekansini uydurmak) SESSIZCE YANLIS cevap olurdu.
        # Yalnizca butun reaktif elemanlar "jX Ω" (impedance) ise devre
        # fazor bolgesindedir ve secilen frekans sonucu DEGISTIRMEZ -- ayni
        # gerekce yukaridaki saf fazor dispatch'inde de yaziyor.
        real_reactive = any(e.kind in ("capacitor", "inductor") for e in elements)
        if elements and all(e.kind in _PASSIVE_KINDS for e in elements) and (distinct or not real_reactive):
            terminals = _terminal_nodes(data, netlist, node_name)
            if len(terminals) == 2:
                omega = 2 * math.pi * (next(iter(distinct)) if distinct else _PHASOR_REFERENCE_HZ)
                zeq = equivalent_impedance(netlist, terminals[0], terminals[1], omega)
                if zeq is not None:
                    if verbose:
                        print(f"  (kaynaksiz AC devre -- {terminals[0]}-{terminals[1]} arasi esdeger empedans)")
                        print(f"  Z_esdeger = {abs(zeq):g} Ohm, aci {math.degrees(cmath.phase(zeq)):g} derece "
                              f"({zeq.real:g} {'+' if zeq.imag >= 0 else '-'} j{abs(zeq.imag):g})")
                    return {
                        "elements": element_log,
                        "results": {"esdeger_empedans_ohm": zeq, "terminals": terminals},
                        "power_balance": 0.0,
                    }
        # Tek bir "hesaplanamadi" mesaji BES AYRI durumu ayni cop kutusuna
        # atiyordu (OLCULDU, 2026-08-25, 15 gercek vaka) -- hangi adimda
        # takildigi soylenmezse hata ayiklanamaz.
        terminals = _terminal_nodes(data, netlist, node_name)
        if not elements:
            detail = "devrede hic eleman yok (tespit basarisiz)"
        elif real_reactive and not distinct:
            detail = (
                "esdeger empedans frekansa bagli ama devrede/sayfa metninde frekans yok -- "
                "bobin/kondansator degeri H/F cinsinden verilmis, uydurma frekansla sayi uretilmez"
            )
        elif len(terminals) != 2:
            detail = (
                f"esdeger direnc/empedans icin TAM 2 acik uc gerekiyor, {len(terminals)} bulundu "
                f"({', '.join(terminals) if terminals else 'hicbiri'}) -- baglanti cikarimi eksik olabilir"
            )
        else:
            detail = (
                f"{terminals[0]}-{terminals[1]} arasi indirgeme tek elemana inmedi "
                "(seri/paralel/Y-Δ yetmiyor ya da desteklenmeyen eleman turu var)"
            )
        raise SolveFromExtractionError(f"devrede kaynak yok ve cozulemedi: {detail}")

    # ACIK UC (derece-1 dugum) kontrolu -- SADECE kaynakli yolda. Kaynaksiz
    # (Req) yol acik uclara MUHTAC (terminaller onlar, bkz. yukarisi), ama
    # kaynakli bir devrede tek elemana degen bir dugum akim akitamaz: ngspice
    # o dugum icin gerilim URETMEZ, `element_results` da onu sorunca ham bir
    # KeyError ile COKER -- SolveFromExtractionError degil, yani cagiran
    # taraf icin ne anlasilir ne de duzgun yakalanabilir bir hata.
    # BULUNDU (2026-08-24, Devre Fotoları 1-100/31.png ve 101-131/116.png):
    # ikisinde de connectivity bir kondansatoru devrenin geri kalanina hic
    # baglayamamis (her iki ucu da sadece kendisine degiyor), sonuc
    # `KeyError: "'n7' dugumu cozumde yok"` seklinde anlamsiz bir cokme
    # oluyordu. Devre GERCEKTEN boyle cizilmis olamaz (o eleman akim
    # tasiyamazdi), yani bu bir cikarim hatasi -- sessizce eksik bir devre
    # cozup fiziksel olarak yanlis cevap vermek yerine acikca reddediliyor.
    dangling = netlist.dangling_nodes()
    if dangling:
        touching = sorted({e.name for e in elements if set(e.nodes) & set(dangling)})
        raise SolveFromExtractionError(
            f"acik uc: {', '.join(touching)} elemani devrenin geri kalanina baglanmamis "
            f"(dugum {', '.join(dangling)} yalnizca tek elemana degiyor) -- "
            "baglanti cikarimi eksik, cozulemez"
        )

    # REFERANS (toprak) SECIMI: ders kitabi sekillerinin cogunda toprak
    # sembolu YOKTUR (Test Sorulari/Soru1 ve Soru4 dahil) -- devre havada
    # cizilir. Boyle bir devrede referans dugum SERBESTCE secilebilir:
    # elemanlarin gerilim ve akimlari secimden BAGIMSIZDIR (yalnizca dugum
    # potansiyellerinin ortak ofseti degisir). Cagiran acikca bir referans
    # vermediyse ilk dugumu sec -- eskiden cozucu "referans yok" diye
    # reddediyordu ve toprak cizilmemis her devre bu yuzden cozulemiyordu.
    if reference is None and not any(node in GROUND_NODES for e in elements for node in e.nodes):
        reference = sorted({node for e in elements for node in e.nodes})[0]
        if verbose:
            print(f"  (sekilde toprak yok -- referans dugum {reference} secildi; "
                  "eleman gerilim/akimlari bu secimden etkilenmez)")

    if distinct:
        frequency = distinct.pop()
        try:
            solution = solve_ac(netlist, frequency, reference=reference)
        except SolverError as exc:
            raise SolveFromExtractionError(f"cozulemedi (AC): {exc}") from exc
        results = element_results_ac(netlist, solution, frequency)
        balance = power_balance_ac(results)
        results = _with_shorted(results, shorted)
        if verbose:
            print(f"  (AC, f = {frequency:g} Hz)")
    else:
        try:
            solution = solve_dc(netlist, reference=reference)
        except SolverError as exc:
            raise SolveFromExtractionError(f"cozulemedi (DC): {exc}") from exc
        results = element_results(netlist, solution)
        balance = power_balance(results)
        results = _with_shorted(results, shorted)

    return {"elements": element_log, "results": results, "power_balance": balance}


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--extraction", required=True, help="extract_for_solve.py ciktisi (extraction.json)")
    parser.add_argument("--reference", default=None, help="toprak yoksa referans dugum adi")
    args = parser.parse_args()

    data = json.loads(Path(args.extraction).read_text(encoding="utf-8"))
    try:
        out = solve_extraction(data, reference=args.reference, verbose=True)
    except SolveFromExtractionError as exc:
        raise SystemExit(str(exc)) from exc

    print("\nSonuclar:")
    # Kaynaksiz (Req/Geq) yolu farkli bir sekil dondurur -- ElementResult
    # DEGIL, {"esdeger_direnc_ohm": float, "terminals": [a, b]} (bkz.
    # solve_extraction'daki kaynaksiz devre dali). BULUNDU (2026-08-21
    # denetimi): asagidaki .describe()/.power erisimleri bu yolda
    # AttributeError ile CLI'yi cokertiyordu -- batch_solve.py etkilenmedi
    # (o .describe() hic cagirmiyor), yalnizca burasi.
    if "esdeger_direnc_ohm" in out["results"]:
        req = out["results"]["esdeger_direnc_ohm"]
        a, b = out["results"]["terminals"]
        print(f"  R_esdeger({a}, {b}) = {req:g} Ohm")
        return
    # Kaynaksiz AC yolu (Zeq) da ayni sekilde .describe()'i olmayan bir
    # kompleks sayi dondurur (bkz. equivalent_impedance dali).
    if "esdeger_empedans_ohm" in out["results"]:
        z = out["results"]["esdeger_empedans_ohm"]
        a, b = out["results"]["terminals"]
        print(f"  Z_esdeger({a}, {b}) = {z.real:g} {'+' if z.imag >= 0 else '-'} j{abs(z.imag):g} Ohm "
              f"(buyukluk {abs(z):g}, aci {math.degrees(cmath.phase(z)):g} derece)")
        return
    # Anahtarli gecici rejim yolu da farkli bir sekil dondurur --
    # {"gecici_yanit": FirstOrderResponse} (bkz. solve_extraction'daki
    # switch dali). FirstOrderResponse'un KENDI .describe()'u var (Req'in
    # aksine) ama .power YOK -- asagidaki guc dengesi/Tellegen kontrolu bu
    # yolda ANLAMSIZ (tek bir DC calisma noktasi degil, zamana bagli bir
    # yanit), o yuzden erken donuluyor.
    if "gecici_yanit" in out["results"]:
        print(f"  {out['results']['gecici_yanit'].describe()}")
        return
    for r in out["results"].values():
        print(f"  {r.describe()}")

    balance = out["power_balance"]
    print(f"\nguc dengesi (0 olmali): {balance!s}")
    # UYARI: bu kontrol Tellegen teoreminden gelir -- solve_dc HANGI DEGERI
    # verirsen ver KVL/KCL'yi cozerek dogal olarak 0 uretir (OLCULDU: VLM
    # yanlis deger okudugunda -- 2 ohm yerine 4 ohm -- bu kontrol yine de
    # ~0 verdi). Yani SADECE topoloji/cozucu gecerliligini dogrular, VLM'in
    # DOGRU DEGERI okudugunu KANITLAMAZ. Deger dogrulugu icin bagimsiz bir
    # kaynak (kitabin bastigi cevap, elle olcum) gerekir.
    ok = abs(balance) < 1e-6 * max(1.0, sum(abs(r.power) for r in out["results"].values()))
    print("(cozucu/topoloji tutarli)" if ok else "(TUTARSIZ -- topoloji/polarite hatali olabilir)")
    print("NOT: bu kontrol VLM'in okudugu DEGERLERIN dogrulugunu KANITLAMAZ, sadece cozumun ic tutarliligini gosterir.")


if __name__ == "__main__":
    main()

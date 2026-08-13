"""Ders kitabındaki GERÇEK devrelerle doğrulama.

Neden ayrı bir dosya: diğer devre testleri elle uydurulmuş devreler
kullanıyordu. Bunlar ise Sadiku'nun kendi alıştırmaları — devre şekilden
okundu, sonuç kitabın BASILI CEVABIYLA karşılaştırıldı.

Bu testler aynı anda iki şeyi doğruluyor:
  1. Çözücünün doğruluğu (kitabın cevabını tutturuyor mu)
  2. Topoloji okumasının doğruluğu (şekil doğru okunmuş mu)
İkisinden biri yanlışsa sonuç tutmaz — öz-doğrulama döngüsünün mantığı bu.

Netlist'ler ÖNCE açıkça yazıldı, sonra iddia edildi (bkz.
`app/circuit/netlist.py` docstring'i: bu projede bir devre topolojisi
"göze bakarak" okunup doğrudan sonuç söylendiğinde hata yapılmıştı).
"""

import pytest

from app.circuit.netlist import Element, Netlist
from app.circuit.topology import equivalent_resistance, reduce_resistors


def R(name, a, b, value):
    return Element(name, "resistor", (a, b), value)


# --- Sadiku vol.1, Practice Problem 2.9 (Figure 2.36) ----------------------
# Kitabın cevabı: Req = 6 Ω
# Üstte 2-3-4 Ω seri; 6 Ω ve 4 Ω dikeyleri alt raya; sağda 5 Ω;
# altta solda 1 Ω, sağda 3 Ω.
PRACTICE_2_9 = [
    R("R2", "t", "A", 2),
    R("R3top", "A", "B", 3),
    R("R4top", "B", "C", 4),
    R("R6", "A", "M", 6),
    R("R4mid", "B", "M", 4),
    R("R5", "C", "F", 5),
    R("R1", "b", "M", 1),
    R("R3bot", "M", "F", 3),
]

# --- Sadiku vol.1, Practice Problem 2.10 (Figure 2.39) --------------------
# Kitabın cevabı: Rab = 11 Ω
# a→8 Ω→merkez C; C-D arasında 20 ∥ 5; C'den alta 9 ve 18; C'den çapraz 20;
# sağda 1 Ω; altta 2 Ω.
PRACTICE_2_10 = [
    R("R8", "a", "C", 8),
    R("R20top", "C", "D", 20),
    R("R5", "C", "D", 5),
    R("R9", "C", "b", 9),
    R("R18", "b", "C", 18),
    R("R20diag", "C", "E", 20),
    R("R1", "D", "E", 1),
    R("R2", "b", "E", 2),
]


@pytest.mark.parametrize(
    ("label", "elements", "terminals", "expected"),
    [
        ("Sadiku 1 - Practice Problem 2.9", PRACTICE_2_9, ("t", "b"), 6.0),
        ("Sadiku 1 - Practice Problem 2.10", PRACTICE_2_10, ("a", "b"), 11.0),
    ],
)
def test_matches_printed_textbook_answer(label, elements, terminals, expected):
    """Şekilden okunan devre, kitabın basılı cevabını vermeli."""
    net = Netlist(list(elements))
    computed = equivalent_resistance(net, *terminals)
    assert computed is not None, f"{label}: indirgenemedi"
    assert computed == pytest.approx(expected, rel=1e-6), label


def test_reduction_steps_follow_textbook_method():
    """İndirgeme, kitabın öğrettiği sırayla ilerlemeli (paralel/seri adımları).

    Practice Problem 2.10 için beklenen: 20∥5=4, sonra 1+4=5, 20∥5=4,
    2+4=6, 9∥18=6, 6∥6=3, 8+3=11.
    """
    net = Netlist(list(PRACTICE_2_10))
    _, steps = reduce_resistors(net, protected_nodes=("a", "b"))
    assert steps, "adım üretilmedi"
    # Son adım toplam direnci vermeli
    assert steps[-1].result_value == pytest.approx(11.0, rel=1e-6)
    # Her adım öğrenciye gösterilebilir olmalı
    for step in steps:
        assert step.kind in {"seri", "paralel"}
        assert "→" in step.describe()


def test_netlist_is_printable_for_student_confirmation():
    """Onay adımının temeli: netlist okunabilir satırlar halinde verilmeli."""
    lines = Netlist(list(PRACTICE_2_9)).to_lines()
    assert "R6 = 6: A-M" in lines
    assert len(lines) == len(PRACTICE_2_9)

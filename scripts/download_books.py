"""Açık lisanslı destekleyici ders kitaplarını data/raw/open/ altına indirir.

Not: Ana kaynak (Sadiku, Fundamentals of Electric Circuits) telifli olduğu
için bu scriptte yer almaz; kullanıcı kendi satın aldığı kopyayı elle
data/raw/ altına yerleştirmelidir. Bkz. docs/kaynaklar.md.
"""

from pathlib import Path
from urllib.request import urlretrieve

BOOKS = {
    "Fiore_DC_Electrical_Circuit_Analysis.pdf": (
        "http://www.dissidents.com/resources/DCElectricalCircuitAnalysis.pdf"
    ),
    "Fiore_AC_Electrical_Circuit_Analysis.pdf": (
        "https://www2.mvcc.edu/users/faculty/jfiore/Circuits2/"
        "ACElectricalCircuitAnalysis.pdf"
    ),
}

OUTPUT_DIR = Path(__file__).resolve().parent.parent / "data" / "raw" / "open"


def main() -> None:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    for filename, url in BOOKS.items():
        target = OUTPUT_DIR / filename
        if target.exists():
            print(f"Zaten mevcut, atlanıyor: {filename}")
            continue
        print(f"İndiriliyor: {filename}")
        urlretrieve(url, target)
        print(f"Tamamlandı: {target}")


if __name__ == "__main__":
    main()

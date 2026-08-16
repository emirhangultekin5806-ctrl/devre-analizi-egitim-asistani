# Kaynak Kayıtları

## Ana Ders Kitabı

| Alan | Bilgi |
|---|---|
| Başlık | Fundamentals of Electric Circuits |
| Yazar | Sadiku (C.K. Alexander, M.N.O. Sadiku) |
| Yayıncı | McGraw-Hill |
| Lisans | Ticari / telifli — kullanıcı tarafından satın alınmış, kişisel kullanım |
| Kapsam | Devre Analizi 1 (DC/AC temel devreler) ve Devre Analizi 2 (ileri konular, üç fazlı sistemler vb.) |
| Kaynak dosya | `Devre analizi.pdf` — tek dosya, 1056 sayfa, bölüm 1-19 (document_id `sadiku_full`) |
| İndirilme/edinilme tarihi | 2026-08-03 |

**Dosya biçimi notu:** Kitap ilk makinede iki cilde bölünmüş olarak
tutuluyordu (`Devre analizi-1.pdf` 550 sayfa / bölüm 1-12 → `sadiku_1`,
`Devre analizi-2.pdf` 506 sayfa / bölüm 13-19 → `sadiku_2`). İkinci
makinede tek birleşik dosya kullanılıyor. Bölüm numaralandırması ve basılı
sayfa numaraları cilt sınırında kesintisiz devam ettiği için birleşik dosya
sorunsuz işleniyor: sayfa ofseti tüm kitapta 31 (bölünmüş hâlde 31 ve -519
olmak üzere iki ayrı ofset gerekiyordu) ve cilt-1 sayfa indeksleri birebir
aynı kalıyor — bu, `tests/sadiku_pdf.py`'de ölçülerek doğrulandı. Eski
`sadiku_1`/`sadiku_2` document_id'leri kodda hâlâ tanınıyor.

**Dağıtım kısıtı:** Bu kitap telifli olduğu için PDF dosyaları repository'ye eklenmez (`.gitignore` → `data/raw/*`). Yalnızca kişisel/lokal kullanım için işlenecek; sistem paylaşılırsa veya teslim edilirse kaynak PDF'ler hariç tutulmalıdır.

## Destekleyici Açık Lisanslı Kaynaklar

### DC Electrical Circuit Analysis: A Practical Approach

| Alan | Bilgi |
|---|---|
| Başlık | DC Electrical Circuit Analysis: A Practical Approach |
| Yazar | James M. Fiore |
| Lisans | Creative Commons BY-NC-SA (atıfla, ticari olmayan, aynı lisansla paylaşım) |
| Kapsam | Devre Analizi 1 (DC devreler) |
| Kaynak dosya | `data/raw/open/Fiore_DC_Electrical_Circuit_Analysis.pdf` (374 sayfa) |
| Kaynak adresi | https://open.umn.edu/opentextbooks/textbooks/884 |
| İndirme adresi | http://www.dissidents.com/resources/DCElectricalCircuitAnalysis.pdf |
| İndirilme tarihi | 2026-08-03 |

### AC Electrical Circuit Analysis: A Practical Approach

| Alan | Bilgi |
|---|---|
| Başlık | AC Electrical Circuit Analysis: A Practical Approach |
| Yazar | James M. Fiore |
| Lisans | Creative Commons BY-NC-SA (atıfla, ticari olmayan, aynı lisansla paylaşım) |
| Kapsam | Devre Analizi 2 (AC devreler) |
| Kaynak dosya | `data/raw/open/Fiore_AC_Electrical_Circuit_Analysis.pdf` (422 sayfa) |
| Kaynak adresi | https://open.umn.edu/opentextbooks/textbooks/883 |
| İndirme adresi | https://www2.mvcc.edu/users/faculty/jfiore/Circuits2/ACElectricalCircuitAnalysis.pdf |
| İndirilme tarihi | 2026-08-03 |

**Not:** Bu iki kitap açık lisanslı olduğu için repo'da paylaşılabilir/dağıtılabilir; proje dokümanının "en az 2 açık ders kitabı" şartını karşılar. Sadiku kitabı (telifli) ile birlikte, sistemde hem "ana/telifli" hem "açık/paylaşılabilir" kaynak katmanı bulunacak.

## Ek Kaynak: Video Kurs

- Kullanıcının kendi Udemy kursu — video formatında, henüz metin/transkript hâlinde işlenmedi.
- İşlenmesi için transkript (.srt/.vtt) veya ders notu (slayt/PDF) gerekiyor.

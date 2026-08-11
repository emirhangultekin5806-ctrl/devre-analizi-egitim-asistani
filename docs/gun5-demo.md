# 5. Gün — Uçtan Uca Demo Kaydı

> BARIKAT Stajyer Programı, 5. Gün gereksinimi: 5 dakikalık demo akışı. Bu doküman, o akışı canlı sunum yerine yazılı olarak kayıt altına alır — konuşmanın kendisi demo yerine geçiyor.

## 1. Problem ve kabul kriteri

VLM'lerin (Qwen3-VL, MiniCPM-V) devre şeması okurken en sık yaptığı hata **terminal polaritesi** (pil sembolünde hangi ucun + hangi ucun − olduğu) — hem farklı model ailelerinde hem de basit/karmaşık devrelerde tekrar tekrar aynı hatayı gördük. Görev: bunu VLM'e bağımlı olmadan, deterministik bir görüntü-işleme katmanıyla çözmek.

**Kabul kriteri:** En az birkaç gerçek örnekte (kitaptan alınmış, doğrulanmış) doğru polarite tespiti + pytest testleriyle güvence altına alınmış, `app/` altında kalıcı bir modül.

## 2. Claude'a verilen bağlam ve plan

Görevi Claude'a bırakmadan önce iki karar sorulup netleştirildi:
- **Nereye koyalım?** → Yeni `app/vision/` klasörü (mevcut `app/ingestion` PDF-metin işleme ile karışmasın, ileride VLM entegrasyonu da buraya gelecek).
- **Kapsam nerede dursun?** → Yalnızca fonksiyonu taşı + testle; sayfada pil sembolünü **otomatik bulma** (bounding box tespiti) kapsam dışı bırakıldı — bugünkü görev için gereksiz büyürdü.

## 3. Değişen dosyalar ve önemli karar

- `app/vision/__init__.py`, `app/vision/battery_polarity.py` (yeni)
- `tests/test_battery_polarity.py` (yeni, 5 test)

**Önemli karar:** Scratchpad'deki prototip (scan_lines + largest_cluster + detect_battery_polarity) neredeyse değişmeden taşındı — "çalışan, doğrulanmış kod varken yeniden yazmaya gerek yok" ilkesi. Commit'e yalnızca bu görevle ilgili 3 dosya eklendi; aynı anda bekleyen ilgisiz `docs/*.md` değişiklikleri bilerek dışarıda bırakıldı.

## 4. Test ve doğrulama kanıtı

```
pytest tests/ -v  → 45 passed
ruff check .      → All checks passed!
```

4 gerçek örnek (Fiore DC, Figure 3.8 ve 3.26 — 3V/6V yatay, 24V/4V dikey) + 1 edge-case testi (pil deseni bulunamayınca `None` dönmesi).

## 5. Claude'un hatalı önerisi ve kullanıcının müdahalesi

Günün en önemli anı burada: Kullanıcının kendi çektiği bir devre fotoğrafını (24V kaynak, R1-R6) VLM'e verip test ederken, **Claude da** (VLM değil, doğrudan görseli yorumlayan Claude) devrenin topolojisini **yanlış okudu** — "R2 ve R4 seri" dedi. Kullanıcı bunu doğrudan reddetti: *"R2 ve R4 seri değil, R4 ve R5 seri, bunların toplamı R3'e paralel, bu da R2'ye seri, bu da R1'e paralel."*

Claude görseli yeniden inceleyip düzeltti; kullanıcının verdiği R_toplam=10Ω ve I=2.4A sonuçlarıyla yeni okuma birebir tutarlı çıktı — yani kullanıcı haklıydı, Claude'un ilk okuması yanlıştı.

**Bunun sonucu:** Bu olay, projenin "VLM okuması tek başına yeterli değil, zorunlu onay adımı şart" tasarım kararını yalnızca teoride değil, **canlı kanıtla** doğruladı — hatta bunu sadece küçük bir VLM değil, bu konuşmayı yürüten model bile yaşadı.

## 6. Git commit ve öğrenilen en önemli nokta

```
fa72db3 Pil polarite tespiti: app/vision modulu ekle
```

**Öğrenilen en önemli nokta:** Bir AI'ın (büyüklüğünden/yeteneğinden bağımsız) karmaşık, görsel/çıkarımsal bir okumasına — özellikle sonuç sayısal ve doğrulanabilirse — körü körüne güvenilmemeli. Bu ders, hem kişisel çalışma standardıma (`docs/kisisel-workflow.md`) hem de ürün tasarımına (zorunlu onay/düzeltme adımı, `docs/vision.md`) doğrudan yansıdı.

# Kişisel Claude Code Çalışma Standardım

> BARIKAT Stajyer Programı, 5. Gün çıktısı — Emirhan Gültekin

## Bir görev geldiğinde nasıl çalışıyorum

1. **Hazırlık** — Doğru branch'te miyim, working tree temiz mi kontrol ederim (`git status`).
2. **Keşif** — Claude'un ilgili dosyayı değiştirmeden önce mevcut kodu/deseni okumasını isterim.
3. **Brif ve Plan** — Küçük olmayan işlerde görevi netleştiririz (amaç, kapsam, kabul kriteri), ama bunu ağır bir "Plan Mode" seremonisiyle değil, Auto Mode içinde yaparız (aşağıya bkz.).
4. **Uygulama** — Küçük adımlarla ilerlenmesini isterim; büyük bir işi (örn. pil polaritesi tespiti) tek seferde değil, önce 1 örnekte, sonra birkaç örnekte doğrulatarak büyütürüz.
5. **Doğrulama** — Her değişiklikten sonra gerçek test/lint çıktısına bakılmasını isterim (`pytest`, `ruff check`).
6. **Git** — İlgisiz dosyalar (kendi kişisel dosyalarım gibi) commit dışında bırakılır; commit mesajı değişikliği gerçekten açıklamalı.
7. **Dokümantasyon** — Önemli kararlar (`docs/vision.md`, karşılaştırma sonuçları vb.) yazılı hale getirilir, sohbette kaybolmaz.

## Plan Mode hakkında kararım

Hafta başında "her önemsiz olmayan iş için önce plan" diye düşünüyordum. Bir haftalık gerçek kullanımdan sonra fikrimi değiştirdim: **Plan Mode'u varsayılan olarak kullanmıyorum, çünkü Auto Mode zaten tam olarak sorulması gereken şeyi doğru zamanda soruyor** — Plan Mode'un kendi seremonisi (ayrı onay turu, ayrı dosya) çoğu zaman gereksiz vakit kaybı oluyor. Plan Mode'u yalnızca gerçekten büyük/belirsiz kapsamlı işlerde bilerek istiyorum.

## Bir görevin "bittiğine" nasıl karar veriyorum

Genellikle Claude'a güveniyorum — test/log çıktısı varsa ona bakarım, yoksa "bitti" dediğinde çoğunlukla kabul ederim. Güvencem şu: eksik bir şey varsa zaten ilerleyen aşamalarda ortaya çıkar, o zaman çözerim — her adımda her şeyi tek tek kanıtlamaya çalışmam, bu beni yavaşlatır.

**Tek istisnam:** Görsel/çıkarımsal bir okumadan (bir diyagram, bir fotoğraf) doğrulanabilir bir sayısal sonuç çıkıyorsa, buna körü körüne güvenmiyorum. Bunu bir devre şemasını yanlış okuyup beni de yanlış yönlendirdiği bir anda fark ettim (11 Ağustos 2026) — bu beni "acaba bu daha önce de oldu mu" diye düşündürdü. Artık bu tür durumlarda çapraz kontrol istiyorum.

## Öğrendiğim en önemli üç nokta

1. Claude da (küçük bir model kadar olmasa da) karmaşık görsel okumalarda yanılabilir — "AI söyledi" tek başına kanıt değil, özellikle sonucu ölçülebilir/doğrulanabilir olan işlerde.
2. Plan Mode her zaman "daha güvenli" demek değil — bazen sadece yavaşlatıyor. Asıl güvenlik, küçük adımlar + gerçek test kanıtında.
3. İyi bir onay/doğrulama adımı, kullanıcıdan "bunu çözebilir misin" değil "bu sana tanıdık geliyor mu" diye sormalı — özellikle kullanıcı konuyu henüz öğreniyorsa.

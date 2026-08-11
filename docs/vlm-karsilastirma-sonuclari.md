# VLM Karşılaştırma Sonuçları (Devre Görseli Okuma)

> Proje dokümanının §9.1 "Model Karşılaştırma Zorunluluğu" ve §35 "Teslim Edilecekler" #11 gereksinimini karşılar.

## Ortam

- Donanım: NVIDIA GeForce GTX 1650 (4096 MiB VRAM), 16 GB RAM, Intel i5-9300H.
- Ollama 0.32.7.
- Test görseli: Fiore DC kitabından (`data/raw/open/Fiore_DC_Electrical_Circuit_Analysis.pdf`, sayfa 78) kırpılmış **Figure 3.8** — iki gerilim kaynağının (3V, 12V) seri bağlandığı basit bir şema, terminaller `a` ve `b`.
- Gerçek/beklenen cevap (kitabın kendi çözümünden, Example 3.2): 2 kaynak var, seri bağlı, terminal `a` **3V kaynağın negatif (sağ) ucuna** bağlı, terminal `b` 12V kaynağın negatif ucuna bağlı, toplam `Vab = 9V` (kutuplar ters yönde olduğu için basit toplama değil, çıkarma gerekiyor — 3+12=15V YANLIŞ).
- Prompt (tüm testlerde aynı): "Bu bir devre şeması. Kaç tane gerilim kaynağı (voltage source) var, değerleri ne, nasıl bağlılar (seri mi?), ve a ile b terminalleri nereye bağlı? Kısaca açıkla."
- Çağrı yöntemi: Ollama'nın `/api/generate` endpoint'i, görsel base64 olarak `images` alanında.

## Sonuçlar

| Model | Varyant | Süre | GPU/CPU | Cevap |
|---|---|---|---|---|
| `qwen3-vl:4b` | varsayılan | **516.4s** (8.6 dk) | %50/%50 (VRAM'e tam sığmadı) | Dolu ama hatalı |
| `qwen3-vl:4b` | `think: false` | 516.6s | %50/%50 | **Boş** — hız kazancı yok |
| `qwen3-vl:4b` | `num_gpu: 0` (saf CPU) | 730.7s | %100 CPU | Boş/yarım — daha da yavaş |
| `qwen3-vl:2b` | `think: false` | 67.8s | tam GPU (muhtemelen) | **Boş** |
| `qwen3-vl:2b` | varsayılan | 53.0s | tam GPU (muhtemelen) | **Boş** |
| `minicpm-v4.5:8b` | varsayılan | **67.7s** | — | Dolu |

**`qwen3-vl:2b` notu:** Her denemede `eval_count` ~2970-2984 token'da sabitleniyor (context/output limiti), ama görünür `response` alanı boş — model "thinking" (görünmez muhakeme) bloğunda takılıp kalıp hiç gerçek cevaba geçemiyor. Bu, küçük modelin bu görev için yetersiz olduğunu ya da Ollama'nın bu model/sürüm kombinasyonundaki chat template/thinking entegrasyonunda bir sorun olduğunu gösteriyor — kesin kök neden netleştirilmedi, sadece kullanılamaz olduğu doğrulandı.

### Doğruluk detayı — `qwen3-vl:4b` (varsayılan, tek dolu cevap)

- ✅ 2 gerilim kaynağı, 3V ve 12V
- ✅ Seri bağlantı doğru tespit edildi
- ✅ Terminal b → 12V kaynağın negatif ucu (doğru)
- ❌ Terminal a → "3V kaynağın **pozitif** ucu" dedi (gerçekte negatif/sağ uç)
- ❌ Bu yüzden "toplam gerilim 3+12=**15V**" dedi (gerçek cevap: 9V, kutuplar ters yönde)

### Doğruluk detayı — `minicpm-v4.5:8b`

- ✅ 2 gerilim kaynağı, 3V ve 12V
- ⚠️ "Seri" kelimesini doğru kullandı ama tanımını yanlış açıkladı ("pozitif uçlar birbirine, negatif uçlar birbirine bağlanır" — bu paralel bağlantının tanımı)
- ❌ Terminal a → "3V kaynağın **pozitif** ucu" dedi (aynı hata, `qwen3-vl:4b` ile birebir örtüşüyor)
- ✅ Terminal b → 12V kaynağın negatif ucu (doğru)

## Karar

**`minicpm-v4.5:8b`** — hem hız (67.7s, kullanılabilir aralıkta) hem de en azından dolu bir cevap üretmesi nedeniyle VLM adayı olarak seçildi.

**Doğruluk sınırı model seçiminden bağımsız:** iki farklı model ailesi de aynı polarite hatasını yaptı. Bu, akademik literatürle örtüşüyor (SINA, arXiv:2607.01609 — GPT-4o gibi çok daha büyük modeller için de aynı sorun rapor ediliyor). Sonuç: VLM tek başına devre topolojisini güvenilir okuyamıyor — bu yüzden `docs/vision.md`'deki zorunlu kullanıcı onay/düzeltme adımı tasarımın vazgeçilmez bir parçası, ek bir güvenlik önlemi değil.

## Denenmeyen / ileride değerlendirilebilecek yollar

- `qwen3-vl` için Ollama güncellemesi sonrası tekrar test (thinking-döngüsü sorunu bir sürüm hatası olabilir).
- Bileşen tespiti (nesne tanıma) + bağlantı çıkarımı + VLM'i yalnızca doğrulama/etiketleme için kullanan hibrit mimari (Sensors dergisi, doi: 10.3390/s26113440 gibi çalışmaların önerdiği yaklaşım) — daha güvenilir ama önemli ek mühendislik gerektiriyor, bu milestone'un kapsamı dışında bırakıldı.

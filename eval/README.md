# QuantumLabs — Eval Harness

Self-improvement çarkının **ölçüm zemini**. Ölçemediğini geliştiremezsin: prompt,
model veya kod her değiştiğinde bu harness'ı koş, kaliteyi say. Fine-tuning / prompt
optimizasyonu bu skorlara göre **insan-onaylı** olarak yapılır (bkz. aşağıda).

## Parçalar

| Dosya | İş |
|---|---|
| `tasks.jsonl` | Versiyonlanmış görev seti (id, kategori, prompt, rubric, max_steps). Salt-okunur görevler. |
| `harness.py` | Görevleri gerçek agent'la **izole** koşar (transcript/memory geçici dizine; repo kirlenmez, memory+profil KAPALI → çekirdek yetenek), metrik toplar, `reports/`'a rapor yazar. |
| `judge.py` | LLM-as-judge: rubric + cevap → `{score, passed, reason}`. Judge modeli `QL_JUDGE_*` ile ayrılabilir. |
| `compare.py` | Aday raporunu baseline'a kıyaslar; **regresyon** (baseline'da geçip adayda kalan) tespit eder; promotion gate'i (exit 0/1). |
| `reports/` | Koşu çıktıları (gitignored). Zaman-damgalı; trend takibi. |

## Kullanım

```bash
# 1) Baseline al (mevcut prod prompt/model)
python -m eval.harness --label baseline

# 2) Bir değişiklik yap (prompt düzenle / yeni model id), aday koş + kıyasla
python -m eval.harness --label cand --model efeacil/qwen3-4b-quantum-v2 \
    --baseline eval/reports/<baseline-dosyasi>.json

# Hızlı deneme: ilk N görev
python -m eval.harness --label smoke --limit 3
```

## Metrikler
- **pass_rate** — judge'ın geçirdiği görev oranı (score ≥ 0.7).
- **avg_score** — ortalama rubric skoru (0–1).
- **avg_steps** — görev başına ReAct adımı (verimlilik).
- **tool_error_rate** — hatalı tool sonuçları / toplam tool çağrısı.
- **p50_latency_s** — medyan görev süresi.

## İnsan-onaylı promotion (gate)
1. `baseline` raporu = mevcut prod.
2. Aday (yeni prompt/model) koş → `compare.py` regresyon var mı bakar.
3. **Regresyon yoksa** exit 0 → sen raporu inceler, onaylarsan promote edersin.
   **Regresyon varsa** exit 1 → promote etme, önce incele.

> CI'da: `python -m eval.harness --label ci --baseline <baseline>` exit kodu regresyonda
> 1 döner → PR gate olarak kullanılabilir.

## Bilinen sınırlamalar
- **Zayıf judge**: judge da 4B pod ise skorlar gürültülü olabilir. Daha güçlü bir judge
  (büyük model / API) `QL_JUDGE_BASE_URL` + `QL_JUDGE_API_KEY` + `QL_JUDGE_MODEL` ile takılır.
- **Salt-okunur görevler**: repo'yu değiştiren (edit) eval'ler için izole bir repo kopyası
  gerekir (henüz yok) — aksi halde eval gerçek repoyu değiştirir.
- Görevler `cwd = repo` ile koşar; dosya araçları gerçek repoda okur.

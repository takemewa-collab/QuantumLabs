# QuantumLabs — Eval Harness

Self-improvement çarkının **ölçüm zemini**. Ölçemediğini geliştiremezsin: prompt,
model veya kod her değiştiğinde bu harness'ı koş, kaliteyi say. Fine-tuning / prompt
optimizasyonu bu skorlara göre **insan-onaylı** olarak yapılır (bkz. aşağıda).

## Parçalar

| Dosya | İş |
|---|---|
| `tasks.jsonl` | Versiyonlanmış görev seti. Üç tip: **salt-okunur** (prompt+rubric, LLM judge), **çok-turlu** (`turns[]` — follow-up; history her turdan sonra transcript'ten kurulur), **edit** (`files`+`check` — izole fixture'da düzenle, dosya durumu deterministik doğrulanır). |
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

## Görev tipleri (tasks.jsonl şeması)
- **Salt-okunur** — `{"id","category","prompt","rubric","max_steps"}`. `cwd = repo`;
  dosya araçları gerçek repoda **okur** (yazmaz).
- **Çok-turlu (follow-up)** — `prompt` yerine `"turns": [{"prompt":...}, ...]`. Aynı
  session'da sırayla koşar; her turdan sonra `history` **transcript'ten** kurulur
  (`runtime.transcript.rebuild_history` — API follow-up ile TEK kaynak → prod paritesi).
  Judge, final cevabı önceki turların ışığında değerlendirir. Rubric son turu tanımlar.
- **Edit/write** — `"files": {yol: içerik}` (izole fixture'a yazılır) + `"check"`
  (`{file, contains[], not_contains[], equals}`; dict ya da liste). Workspace repo
  **değil** izole bir tmp dizin → repo asla kirlenmez. Puanlama **deterministik**
  (dosya durumu; LLM judge yok). `turns` ile birleşebilir (hatırla + düzenle).

## Bilinen sınırlamalar / notlar
- **Zayıf judge**: judge da 4B pod ise skorlar gürültülü olabilir. Daha güçlü bir judge
  (büyük model / API) `QL_JUDGE_BASE_URL` + `QL_JUDGE_API_KEY` + `QL_JUDGE_MODEL` ile takılır.
  (Edit görevleri judge kullanmaz — deterministik dosya-check.)
- **Edit fixture'ı repo değil**: edit görevleri kendi kendine yeten küçük fixture'larda
  koşar (repo kopyası değil) → deterministik ve hızlı, repo içeriği drift'inden bağımsız.
- **Bulgu (baseline)**: 4B model edit görevlerinde sık sık **mutlak yol** deneyip
  (kural #8 ihlali) izole workspace dışına çıkıyor ve fail ediyor → prompt/fine-tune
  için net bir iyileştirme hedefi.

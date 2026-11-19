# LLM memorization versus Cutoff date

Research for issue #35 (parent #30). Compiled 2026-11-19. This repo has no existing convention for research notes, so this lives in `docs/research/`.

## Bottom line

- **Every current Claude model has a knowledge cutoff of June 2026.** Any Cutoff date before that is inside what the model may have seen, including the repo's later commits and bug fixes.
- **A Run is only free of "future knowledge" if its scoring window starts after the model's training data cutoff.** That pushes the Cutoff date to about the model cutoff, so the "backtest" is nearly a forward test with a short window.
- **Contamination is documented in code evaluations, but it is not always inflating.** Effects range from large (SWE-bench file localization) to small or negative (Glasserman and Lin's finance backtest).
- **The cheapest strong design is a dose-response comparison, not a single clean Run.** Run several Cutoff dates that straddle the model cutoff and see whether the LLM's lead over churn x complexity changes across the boundary.
- **Membership-inference scores are weak evidence for this project.** Behavioral probes and the pre/post-cutoff comparison are better value.

## 1. Model knowledge cutoffs (checked against official docs on 2026-11-19)

Source: Anthropic [Models overview](https://platform.claude.com/docs/en/about-claude/models/overview) (redirects to `/docs/en/models/overview`) and the per-model pages.

| Model | API ID | Reliable knowledge cutoff | Training data cutoff |
| --- | --- | --- | --- |
| Claude Fable 5.2 | `claude-fable-5-2` | Jun 2026 | Jun 2026 |
| Claude Opus 5.5 | `claude-opus-5-5` | Jun 2026 | Jun 2026 |
| Claude Sonnet 5.5 (released Sep 28, 2026) | `claude-sonnet-5-5` | Jun 2026 | Jun 2026 |
| Claude Haiku 5.5 | `claude-haiku-5-5` | Jun 2026 | Jun 2026 |
| Claude Sonnet 4.5 (deprecated, retires Nov 30, 2026) | `claude-sonnet-4-5-20250929` | Jan 2025 | Jul 2025 |

Facts and caveats:

- The docs define "reliable knowledge cutoff" as the date through which knowledge is "most extensive and reliable", and "training data cutoff" as the broader range of data used. The two differ by 6 months for Sonnet 4.5 and are equal for the 5.5 generation.
- Sources for the Sonnet 4.5 row: [Sonnet 4.5 model page](https://platform.claude.com/docs/en/models/sonnet-4-5/overview). Sources for the 5.5 rows: the [Models overview](https://platform.claude.com/docs/en/about-claude/models/overview) and [Sonnet 5.5 page](https://platform.claude.com/docs/en/models/sonnet-5-5/overview).
- The [Transparency Hub](https://www.anthropic.com/transparency) lists a "Knowledge Cutoff Date" per model and, as read by the fetch tool, gave Opus 5 as May 2026 and Opus 4.7, Opus 4.8, Sonnet 5, Fable 5 and Mythos 5 as January 2026. It did not list the 5.5 models in the part I could read (I read about the first 100K of 180K characters). Treat the Hub values as unverified until someone reads the whole page.
- Cutoffs are stated at month granularity. Content near the boundary is sparse in training data, so "reliable" understates the risk window: material from after the reliable cutoff but before the training cutoff can still be partly known.
- Model IDs are pinned snapshots, per the Models overview. That fits [ADR 0001](../adr/0001-reproducibility-means-replay.md): the Manifest can record a model ID whose cutoff is fixed and documented. Retired models can no longer be called, but Replay does not need them.
- I did not verify the cutoffs of Haiku 4.5, Opus 4.5, Sonnet 4.6 or Opus 4.6 beyond what is above. The Sonnet 4.5 page lists the 5.x models and Sonnet 4.5 only.

### What this means for the Cutoff date

Let `K` be the model's training data cutoff and `C` the Cutoff date. A Run ranks files using history before `C` and is scored on bug fixes in a window `(C, C + W]`.

- If `C + W` is before `K`, the scoring labels (later fixes) are inside the model's possible training data. This is the contaminated case, and it applies to any repo history before about June 2026 for the current models.
- If the window starts after `K` (`C >= K`), the labels are post-cutoff and the model cannot have memorized them. The model can still have memorized the repo up to `K`, but that is the legitimate "history before the Cutoff date" it is allowed to see.
- Today is 2026-11-19, so with `K` = Jun 2026 the usable window is at most about 5 months and grows only with time. Fixes are also reported late: a bug fix merged after `C` may only be linked to a bug weeks later. That argues for waiting, not for shortening `W`.
- Using an older model with an earlier `K` (for example Sonnet 4.5, `K` = Jul 2025) allows a longer clean window (Aug 2025 onward) but is deprecated and retires Nov 30, 2026. A Run needs live API calls, so it could not be repeated after that date, only replayed ([ADR 0001](../adr/0001-reproducibility-means-replay.md)).
- `C < K` does not make a Run useless; it makes the result an upper bound on LLM skill that must be reported with its contamination status. See section 4.

The [Leakage test](../../GLOSSARY.md) proves that nothing after `C` reaches a prompt. It does not address what the model already knows. The two are separate risks, and this issue is about the second.

## 2. Evidence of memorization and contamination in code evaluations

| Study | Finding | Strength of evidence |
| --- | --- | --- |
| Carlini et al., [Quantifying Memorization Across Neural Language Models](https://arxiv.org/abs/2202.07646) | Memorization grows log-linearly with model capacity, example duplication, and prompt context length; warns it "will likely get worse as models continue to scale, at least without active mitigations". | Strong, controlled, but on open models. |
| Liang et al., [The SWE-Bench Illusion](https://arxiv.org/abs/2506.12286) | Given only an issue description, with no repo context, models name the buggy file path with up to 76% accuracy on SWE-bench versus up to 53% on repos outside SWE-bench. Function reproduction reaches up to 35% consecutive 5-gram accuracy on SWE-bench versus up to 18% on other benchmarks. | Correlational: a gap, not direct proof. Very close to this project's task (file-level localization). |
| Jain et al., [LiveCodeBench](https://arxiv.org/abs/2403.07974) | Problems carry release dates; evaluating only after a model's cutoff avoids contamination. Reports a sharp drop for some models on problems released after their cutoff, and overfitting on HumanEval. | Strong for competitive programming; a direct pre/post-cutoff comparison. |
| Ramos et al., [Are LLMs Memorizing Bug Benchmarks?](https://arxiv.org/abs/2411.13323) | Combines presence in training corpora, negative log-likelihood (NLL), and n-gram accuracy. Older models (codegen-multi) show significant memorization of Defects4J; newer models trained on larger datasets (Llama 3.1) show limited signs. | Medium: open models only; shows the size of the effect varies by model. |
| Metamorphic testing paper, [arXiv 2604.21579](https://arxiv.org/abs/2604.21579) (Apr 2026) | Semantics-preserving transformations of Defects4J and GitBug-Java cut patch success by 4.1% (GPT-4o) to 15.98% (Llama-3.1); the drop correlates with NLL on the original code. | Medium: supports memorization as a cause, not proof. |
| Cao et al., [Concerned with Data Contamination?](https://arxiv.org/abs/2403.16898) | Tests countermeasures for code models; reports that refactoring operators such as identifier renaming change data more and help reduce contamination effects. | Not opened in full; abstract-level only. |
| Badertdinov et al., [SWE-rebench](https://arxiv.org/abs/2505.20411) and [SWE-bench Goes Live!](https://arxiv.org/abs/2505.23419) | Continuously refreshed benchmarks from recent issues. SWE-bench-Live reports 19.25% for the best configuration versus 43.20% on SWE-bench Verified under the same setup. SWE-rebench argues some models look inflated on Verified. | Suggestive, but the two benchmarks also differ in difficulty and repo mix, so the gap is not purely contamination. |

Two cautions on reading this evidence:

- **Contamination does not always inflate scores.** [Glasserman and Lin](https://arxiv.org/abs/2309.17322) separate look-ahead bias (the model recalls what happened) from a "distraction effect" (general knowledge about an entity skews the output). Anonymizing headlines raised in-sample returns, which implies the distraction effect was negative there. A [2026 study of pretrained forecasting models](https://arxiv.org/abs/2609.20554) concludes that future-data exposure is an information-set violation but does not by itself prove inflated accuracy. The sign of the bias is an empirical question.
- **Most numbers come from other models and tasks.** None of these studies tested a Claude 5.x model on file-level debt ranking. Effect size for this project is unknown.

Provenance note: for several rows I relied on abstracts and the fetch tool's summaries of them, not the full papers. Figures are the papers' own claims.

## 3. Mitigations used by comparable studies

| Mitigation | Used by | Cost | Validity tradeoff |
| --- | --- | --- | --- |
| **Post-cutoff data** (test only on items newer than `K`) | LiveCodeBench, SWE-bench-Live, SWE-rebench | Low compute; the window is small and shrinks the sample. Needs a refresh each time a model with a later `K` ships. | Strongest guarantee against label leakage. Cannot say anything about older history, and it needs enough post-`K` fixes in each Target repo. |
| **Time-aware or dated models** | Finance work such as [DatedGPT](https://arxiv.org/abs/2603.11838) (annual-vintage pretraining, per its listing; not opened in full) | Very high; not available for Claude. | Clean by construction, but not an option here. Listed to show the frontier approach. |
| **Obscure or private repos** | SWE-Bench Illusion compares in-benchmark with out-of-benchmark repos | Medium: need repos the model likely never saw; private repos limit publication and replication. | Removes repo-specific memory but changes the population. Small repos have less churn signal and fewer bug fixes. |
| **Identifier or name obfuscation** | Metamorphic testing (2604.21579), Cao et al., Glasserman and Lin (company names removed) | Medium: a transformation pipeline plus tests that it preserves behavior. | Reduces retrieval cues but also removes real signal. Here the ranked unit is a file path, and path names carry legitimate meaning. File-path recall is also exactly what the SWE-Bench Illusion measures, so hiding paths hits the core of the task. Partial obfuscation (file contents only) is weaker. |
| **Held-out commits** (hide recent history, score on later fixes) | This repo's own Cutoff date design | Zero extra cost. | Does not address memorization at all if the held-out window precedes `K`. It controls only what the prompt shows. |
| **Membership-inference checks** (Min-K% Prob, NLL) | [Shi et al.](https://arxiv.org/abs/2310.16789), Ramos et al. | Low for open models; see below for Claude. | Weak. See below. |
| **Behavioral probes** (verbatim completion of post-`C` code, name the buggy file from a commit message alone) | SWE-Bench Illusion (file path identification and 5-gram reproduction) | Low: a few calls per repo. | Black-box, works on Claude, and directly measures the quantity of concern. Gives evidence, not a proof. |
| **Pre/post-cutoff comparison** (same method, windows on either side of `K`) | LiveCodeBench | Low to medium: more Runs. | Best available validity check. A drop in the LLM's lead after `K` is direct evidence of contamination. Confounded if bug-fix labeling or repo activity changes over time. |

### Membership inference is a poor fit

- [Duan et al.](https://arxiv.org/abs/2402.07841) tested membership inference attacks on Pythia models (160M to 12B) and found they barely outperform random guessing in most settings. Reported successes were often explained by distribution shift, such as members and non-members from the same domain but different time periods. That is exactly the project's setup, so a "detected" signal could just mean "newer code looks different".
- Min-K% Prob and NLL need per-token probabilities. I did not verify whether the Claude API exposes log probabilities, so these methods may not be usable on Claude models at all. Check before planning on them.
- Even with logprobs, a positive score on one file would not say whether the model knows the file's future (the bug fixes), only that it saw the text.

## 4. Implications for this project

- **The claim has to be scoped to the model cutoff.** For `C` before `K`, the honest claim is "ranking performance, possibly inflated by memorization". Only `C >= K` supports "predictive skill".
- **A control group is more convincing than a mitigation.** If the LLM beats churn x complexity only on windows before `K` and the lead vanishes after, that is the contamination signature. If the lead persists after `K`, the result stands without needing obfuscation.
- **Record `K` in the Manifest.** The Manifest already holds the model and Cutoff date. Adding the model's documented training data cutoff, plus the distance `C - K`, makes each Run's contamination status checkable at Replay time. This is consistent with ADR 0001.
- **Repo popularity is a dose variable.** Memorization scales with duplication (Carlini et al.), and the SWE-Bench Illusion gap is largest on well-known repos. Include repos of different popularity and report lift against popularity.
- **A null result is still informative.** If the LLM does not beat the baseline even with possible memorization, contamination cannot explain the result away, which makes the null stronger.

## 5. Decisions the owner must make

1. **What claim to make.** Predictive skill (requires `C >= K`) or measured ranking quality with a stated contamination bound (allows `C < K`)? This decides whether the rest matter.
2. **Which model and `K`.** Current models all have `K` = Jun 2026. Pick one pinned model and record `K`. Consider an older model with an earlier `K` for a longer clean window, accepting that Sonnet 4.5 retires Nov 30, 2026 and could only be replayed afterward.
3. **Cutoff date and scoring window.** Choose `C`, and `W` long enough for fix labels to appear. Decide whether to wait for more post-`K` time before running the main experiment.
4. **Whether to run the straddle design.** Several Cutoff dates around `K`, with the LLM-versus-baseline lead compared across the boundary. Costs more Runs (Sonnet 5.5 is $2 / $10 per MTok input and output, 50% off through the Batch API, per the [Models overview](https://platform.claude.com/docs/en/about-claude/models/overview)).
5. **Repo selection policy.** Popular repos only, or a mix including obscure ones for a dose-response check? Private repos reduce reproducibility.
6. **Obfuscation.** Skip it, apply it to file contents only, or pseudonymize paths? My read is to skip it for the main result, because it removes legitimate signal; use it only as a robustness check. This is a judgment call.
7. **Behavioral probes.** Add a cheap probe (name the buggy file from a post-`C` commit message with no repo context; verbatim completion of post-`C` code) as a contamination canary, reported alongside results?
8. **Whether to pursue membership inference at all.** Verify logprob availability first; given the weak evidence, I recommend not investing unless logprobs are available and cheap.
9. **Reporting.** Report contamination status for every Run (`C - K`, repo popularity, probe results), including for a null result.

## Sources

Official Anthropic docs:

- [Models overview](https://platform.claude.com/docs/en/about-claude/models/overview)
- [Claude Sonnet 5.5](https://platform.claude.com/docs/en/models/sonnet-5-5/overview)
- [Claude Sonnet 4.5](https://platform.claude.com/docs/en/models/sonnet-4-5/overview)
- [Transparency Hub](https://www.anthropic.com/transparency)

Papers (arXiv):

- Carlini et al., [2202.07646](https://arxiv.org/abs/2202.07646)
- Shi et al., [2310.16789](https://arxiv.org/abs/2310.16789)
- Duan et al., [2402.07841](https://arxiv.org/abs/2402.07841)
- Jain et al., [2403.07974](https://arxiv.org/abs/2403.07974)
- Cao et al., [2403.16898](https://arxiv.org/abs/2403.16898)
- Ramos et al., [2411.13323](https://arxiv.org/abs/2411.13323)
- Badertdinov et al., [2505.20411](https://arxiv.org/abs/2505.20411)
- SWE-bench Goes Live!, [2505.23419](https://arxiv.org/abs/2505.23419)
- Liang et al., [2506.12286](https://arxiv.org/abs/2506.12286)
- Glasserman and Lin, [2309.17322](https://arxiv.org/abs/2309.17322)
- Metamorphic testing for program repair, [2604.21579](https://arxiv.org/abs/2604.21579)
- Chen et al., [2609.20554](https://arxiv.org/abs/2609.20554)
- DatedGPT, [2603.11838](https://arxiv.org/abs/2603.11838)

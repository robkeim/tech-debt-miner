# Bug-fix labeling: SZZ versus commit-message heuristics

Research for issue #33 (parent #30, blocks #34). Question: how do SZZ-style tracing and commit-message heuristics (keywords, linked issues) identify bug-fix commits and the files they implicate, how accurate are they, and what did comparable defect-prediction studies choose?

Terms follow [GLOSSARY.md](../../GLOSSARY.md); the backtest is described in [APPROACH.md](../APPROACH.md).

## Summary

- **No labeling method is clean.** The best-measured result is that only about half of the commits SZZ marks as bug fixes are real bug fixes ([Herbold et al. 2022](#herbold-2022)).
- **Two separate steps get conflated.** Step 1 finds bug-fix commits (message keywords, issue links). Step 2 (the SZZ trace-back) finds the commits that introduced the bug. Most accuracy numbers for "SZZ variants" measure step 2 only ([Rosa et al. 2021](#rosa-2021)).
- **This project may only need step 1.** If ground truth is "files touched by fix commits after the Cutoff date", no trace-back is needed. Step 2 matters only if we want "the bug already existed at the Cutoff date" (decision D2 below).
- **The biggest noise sources are issue misclassification, tangled commits and non-fix files inside real fixes**, not the blame algorithm. Each is large enough to move rankings ([Herzig 2013](#herzig-2013), [Herzig and Zeller 2013](#herzig-zeller-2013), [Herbold et al. 2022](#herbold-2022)).
- **Squash merges** make every effect above worse (one commit per PR). The sources do not measure this directly; see [Pitfalls](#pitfalls).

## Background: how the methods work

### Step 1: finding bug-fix commits

- **Original SZZ** splits each commit message into tokens and links a commit to a bug report when it contains a bug number, a plain number, or a keyword matching `fix(e[ds])?|bugs?|defects?|patch`. Each link gets a syntactic confidence (0 to 2) and a semantic confidence (checked against the bug report: resolved as FIXED, same author, description in the message). Only links above a threshold are kept ([Sliwerski et al. 2005](#sliwerski-2005)).
- **Issue-link heuristics** match issue IDs in messages (for example `PROJ-123`, `#123`, `fixes #123`) and then check the tracker: issue type is bug, status is closed or resolved, and the commit date falls near the resolution date ([Bird et al. 2009](#bird-2009), as summarized by [Herbold et al. 2022](#herbold-2022)).
- **Keyword-only classification** (no tracker) is the fallback for repos without usable issue data. The sources reviewed give no accuracy figure for it on its own; the closest evidence is the 11% issue-link coverage in the Rosa oracle below.
- **Link recovery** (ReLink) infers missing links from text and timing. It reported 89% precision and 78% recall against 91% precision and 64% recall for plain heuristics, but an independent benchmark found it precise yet weak at recovering missing links ([Bissyande et al. 2013](#bissyande-2013)). The ReLink figures come from the authors' project page, not the CSMR paper.

### Step 2: SZZ trace-back (bug-introducing commits)

For each line a fix deleted or changed, blame it in the fix's parent to find the commit that last touched it. Variants:

| Variant | Source | What it adds |
| --- | --- | --- |
| B-SZZ | [Sliwerski et al. 2005](#sliwerski-2005) | Baseline: blame deleted or changed lines, drop candidates committed after the bug report date |
| AG-SZZ | [Kim et al. 2006](#kim-2006) | Annotation graph to follow lines through moves; ignores comment and blank-line changes |
| L-SZZ, R-SZZ | Davies et al., as described in [Rosa et al. 2021](#rosa-2021) | Pick the largest or the latest candidate instead of all |
| MA-SZZ | [da Costa et al. 2017](#dacosta-2017) | Drops meta-changes (branch and merge commits, and others) |
| RA-SZZ | [Neto et al. 2018](#neto-2018) | Drops lines touched by detected refactorings (Java only, via RefDiff or RefactoringMiner) |

Tools: PyDriller implements B-SZZ on top of `git blame`; OpenSZZ and SZZ Unleashed also exist ([Rosa et al. 2021](#rosa-2021), Table I and II).

`git blame` itself supports `-w` (ignore whitespace), `-M` and `-C` (follow moved or copied lines), and `--ignore-revs-file` (skip listed commits such as bulk reformatting) ([git-blame docs](#git-blame)). These approximate AG-SZZ and MA-SZZ cleanups without a custom implementation.

## Measured accuracy

### Step 2 (inducing commits)

Rosa et al. built an oracle from commits where developers wrote which commit introduced the bug: 19.6 million commits parsed, 3,585 candidates, 1,930 confirmed by manual review (two evaluators each; conflicts dropped). Only 212 of the 1,930 (11.0%) referenced an issue, so issue-tracker-based methods can run on a minority of real fixes ([Rosa et al. 2021](#rosa-2021)). Results on that oracle (all languages the authors support, no issue-date filter):

| Variant | Recall | Precision | F1 |
| --- | --- | --- | --- |
| B-SZZ | 0.69 | 0.39 | 0.50 |
| AG-SZZ | 0.60 | 0.45 | 0.52 |
| L-SZZ | 0.45 | 0.52 | 0.48 |
| R-SZZ | 0.57 | 0.66 | 0.61 |
| MA-SZZ | 0.64 | 0.36 | 0.46 |
| RA-SZZ* (Java only) | 0.45 | 0.35 | 0.39 |
| PyDriller SZZ | 0.67 | 0.39 | 0.49 |
| SZZ Unleashed | 0.72 | 0.09 | 0.16 |

Takeaways: no variant exceeds F1 0.61; the simplest variant (B-SZZ) has the best recall among the non-outlier tools; R-SZZ is the most precise (about 70% with an issue-date filter); refactoring-aware RA-SZZ* did not help on this oracle. The oracle is biased toward fixes whose authors name the culprit commit, and the authors say it is not exhaustive.

Older and related figures:

- AG-SZZ removed about 38% to 51% of false positives and 14% to 15% of false negatives compared with the original algorithm, on the authors' own checked data ([Kim et al. 2006](#kim-2006)).
- 6.5% of lines SZZ flags as bug-introducing are refactorings (10 Apache projects, 31,518 issues); RA-SZZ cut flagged lines by 20.8% ([Neto et al. 2018](#neto-2018), figures from the abstract and an archive copy; I did not read the full text).
- SZZ implementations report that at least 46% of bugs are caused by changes years apart, and the paper finds earlier improvements tend to inflate incorrect results ([da Costa et al. 2017](#dacosta-2017), abstract only).

### Step 1 (fix commits and files)

All from [Herbold et al. 2022](#herbold-2022) (398 releases, 38 Apache projects, manual validation of links and issue types):

- About one quarter of the commit-to-issue links SZZ detects are wrong (both missed links and false positives).
- For every correctly labeled bug issue there are 0.74 mislabeled ones.
- Combined, only about half of the commits SZZ identifies are real bug fixes, and SZZ misses about one fifth of real fixes.
- Their Jira-ID-pattern linker found a median 99.7% of correct links but also a median 1.7% extra wrong links (up to 59.4% in one project, caused by version numbers in messages). Plain numbers like `1` or `256` are the classic false-positive source.
- Of 1,000 commits with no detected link, 40 had a Bugzilla link in a tracker whose data was gone, so about 4% of unlinked commits may be fixes that cannot be recovered.
- With a six-month window to assign bugs to releases, one file is wrongly labeled defective for each correctly labeled one, and two defective files are missed. The affected-versions field is unreliable.

Issue types ([Herzig et al. 2013](#herzig-2013), 7,401 manually classified reports from five projects): 33.8% of reports typed as bug were not corrective code changes (feature, documentation, refactoring and so on); more than 40% of all reports had the wrong type. As a result, on average 39% of files marked defective never had a bug, and 16% to 40% of the top 10% most defect-prone files did not belong there.

Label noise and model quality:

- Mislabeling is not random; precision is rarely affected, recall drops (models on noisy data reached about 56% to 68% of clean-data recall) ([Tantithamthavorn et al. 2015](#tantithamthavorn-2015), from abstract-level sources).
- For just-in-time models, noise from B-SZZ and MA-SZZ caused no considerable performance drop; AG-SZZ noise caused a statistically significant drop of about 1% to 5% ([Fan et al. 2019](#fan-2019), abstract only).

## Pitfalls

- **Refactor noise.** Refactorings are blamed as the origin of later bugs and appear as "changed files" in fixes. 8.73% of non-fix file changes inside bug-fixing commits are refactorings, and none of the SZZ implementations used for common datasets filters them (as reported by [Herbold et al. 2022](#herbold-2022), citing Mills et al. 2018; I did not read the primary Mills paper).
- **Files in a fix that are not part of the fix.** Per the same report, about 64% of file changes in bug-fixing commits were not part of the fix: pure additions (46.58%), test code (30.90%), refactorings (8.73%) and comment changes (8.49%). This matters directly for us because our score is file-level. Excluding test files and non-source files is cheap; the rest needs diff analysis.
- **Tangled commits.** Up to 15% of bug-fix change sets mix unrelated concerns (five Java projects, 7,000+ change sets), and at least 16.6% of source files are wrongly associated with bug reports when this is ignored. Between 6% and 50% of the files first marked most defect-prone did not belong ([Herzig and Zeller 2013](#herzig-zeller-2013)). The paper also notes the fraction is a floor (it untangled only some change sets).
- **Squash merges.** GitHub squash-and-merge combines all commits of a pull request into one commit on the base branch ([GitHub docs](#github-squash)). Inferences, not measured in the sources above: (a) one commit can carry a whole feature plus a fix, increasing tangling; (b) the default message may be the PR title, so "fix" keywords reflect the PR, and numeric `(#123)` suffixes are PR numbers that numeric linkers can mistake for issue IDs; (c) blame lands on the squash commit, so inducing commits are coarser; (d) Herbold et al. also warn that analyses limited to the main branch lose branch history. Check the squash share in each Target repo before choosing.
- **Missing links bias the sample.** Fixes with explicit links differ systematically from unlinked ones ([Bird et al. 2009](#bird-2009), abstract-level) and only 11% of fixes in the Rosa oracle named an issue.
- **Fix date versus bug age.** A fix after the Cutoff date may fix a bug introduced after the Cutoff date. A file ranked "risky" at the Cutoff date cannot be blamed for that. Only the trace-back step distinguishes the two ([da Costa et al. 2017](#dacosta-2017) frames the same "earliest bug appearance" criterion).
- **Reproducibility of SZZ studies.** A review of 187 SZZ papers examined reproducibility and credibility; the numbers I found for it were secondary, so I do not rely on them ([Rodriguez-Perez et al. 2018](#rodriguez-2018)).

## What comparable studies chose

- **Eclipse defect data (Zimmermann et al. 2007):** mapped bug-database entries to files via SZZ-style commit-to-bug links, with pre- and post-release counts per file ([PROMISE 2007](#promise-2007)). Herbold et al. list this family (and its successors) as the state of practice and find it noisy.
- **Bug-prediction benchmark (D'Ambros et al. 2012):** counted defects reported in the six months after a release, per class, as the prediction target ([MSR 2010 version](#dambros-2010); I did not confirm the linking method).
- **Release-level datasets (Yatish et al. 2019):** compared keyword and issue-ID heuristics with a "realistic" approach using the earliest affected release set by the development team, over 32 releases. The heuristic strongly changes the datasets and the realistic approach improves classification accuracy ([ICSE 2019](#yatish-2019), abstract only).
- **Careful studies validate by hand.** Herzig et al. recommend manual validation of future data; Herbold et al. built a manually validated link and issue-type set; Rosa et al. built a double-reviewed oracle. Nobody in this set trusts raw keyword or SZZ labels without a sample check.
- **Just-in-time prediction** (Kamei et al. 2013) uses fix commits plus trace-back to label inducing changes ([TSE](#kamei-2013); I could not read how they identify fixes from the sources I reached). That is a different unit (changes, not files at a date).

No study I found is a file-level ranking backtest like ours, so none directly specifies the label we should use.

## Decisions for the owner

Recommendations are mine, not established by the sources.

1. **D1: Fix identification rule.** Options: (a) closed issue typed bug linked from the commit (high precision, low coverage; only works where trackers are used and typed); (b) message keywords only (high coverage, noisy; Herbold-style numeric traps); (c) both, reporting each as a separate label set. Recommend (c): primary label = tracker-confirmed where available, sensitivity run with keywords only.
2. **D2: Is trace-back (SZZ step 2) in scope?** If ground truth is "files touched by post-Cutoff fixes", skip it. If it is "bugs present at the Cutoff", we need it, and it only adds value if the inducing commit is before the Cutoff. Recommend skipping for the first version and recording the limitation; if added, use B-SZZ via PyDriller with `-w -M -C` and an ignore-revs file for the best recall, or R-SZZ-style for precision (Rosa et al.).
3. **D3: File-level filtering.** Exclude test files, docs, generated files; consider excluding pure additions and comment-only or whitespace-only changes. Decide how strict, since this removes much of the measured file-level noise (about 64% of file changes in fixes per Herbold et al.).
4. **D4: Tangled and large commits.** Options: ignore; cap by files changed (for example drop fixes touching more than N files or tagged as refactor, feature or merge); or weight files by fix size. Untangling algorithms exist but are heavy. Recommend a simple cap plus keyword exclusion (`refactor`, `cleanup`, `rename`, `merge`, `bump`).
5. **D5: Squash-merge policy.** Per Target repo, decide whether to analyze squashed commits as is or expand to PR commits through the GitHub API (extra network dependency, which ADR 0003 forbids in tests but not in data collection; check). Needs a first check of how many Target repos squash.
6. **D6: Validation budget.** Choose a manual validation sample (for example 100 fixes per Target repo, two reviewers if possible) and an accuracy bar. The Rosa and Herbold protocols are the models. Alternatively, an LLM labeler could stand in, but it would make the ground truth depend on a model; the ground-truth rule should not share a model with the ranker. This is my own caution, not a sourced finding.
7. **D7: Window length.** Herbold et al. found six-month assignment unreliable for release-level labels. Pick the post-Cutoff window deliberately and report sensitivity to two or three lengths.
8. **D8: Report noise as a limitation.** At minimum, state the expected label error (roughly half of SZZ-identified fixes can be false) in the results so a null or weak result is read correctly.

## Gaps in this research

- Accuracy of keyword-only fix classification was not found in primary sources I could read.
- Squash-merge effects are reasoned, not measured.
- Several figures come from abstracts or archive copies (marked above): Neto 2018, da Costa 2017, Fan 2019, Tantithamthavorn 2015, Yatish 2019, Bird 2009, Kamei 2013.
- Mills et al. 2018 and Davies et al. were not read directly.
- I did not find work using LLMs as the labeler for bug fixes that I could verify.

## Sources

<a id="sliwerski-2005"></a>
- Sliwerski, Zimmermann, Zeller. "When do changes induce fixes?" MSR 2005. <https://www.st.cs.uni-saarland.de/papers/msr2005/msr2005.pdf> (read: link confidence scheme, keyword regex).

<a id="kim-2006"></a>
- Kim, Zimmermann, Pan, Whitehead. "Automatic Identification of Bug-Introducing Changes." ASE 2006. <https://thomas-zimmermann.com/publications/files/kim-ase-2006.pdf> (read abstract).

<a id="dacosta-2017"></a>
- da Costa et al. "A Framework for Evaluating the Results of the SZZ Approach for Identifying Bug-Introducing Changes." IEEE TSE 43(7), 2017. <https://rebels.cs.uwaterloo.ca/papers/tse2017_dacosta.pdf> (abstract via search results).

<a id="neto-2018"></a>
- Neto, da Costa, Kulesza. "The Impact of Refactoring Changes on the SZZ Algorithm: An Empirical Study." SANER 2018. <https://danielcalencar.github.io/papers/Edmilson_SANER18.pdf> (abstract via search results).

<a id="rosa-2021"></a>
- Rosa, Pascarella, Scalabrino, Tufano, Bavota, Lanza, Oliveto. "Evaluating SZZ Implementations Through a Developer-informed Oracle." ICSE 2021. <https://arxiv.org/abs/2102.03300> (read: Tables I, III, V).

<a id="herbold-2022"></a>
- Herbold, Trautsch, Trautsch, Ledel. "Problems with SZZ and features: An empirical study of the state of practice of defect prediction data collection." Empirical Software Engineering 27, 42 (2022). <https://arxiv.org/abs/1911.08938> (read: abstract, contributions, sections 2 and 5.3).

<a id="herzig-2013"></a>
- Herzig, Just, Zeller. "It's Not a Bug, It's a Feature: How Misclassification Impacts Bug Prediction." ICSE 2013. <https://www.st.cs.uni-saarland.de/publications/files/herzig-icse-2013.pdf> (read: abstract, intro, tables).

<a id="herzig-zeller-2013"></a>
- Herzig, Zeller. "The Impact of Tangled Code Changes." MSR 2013. <https://www.st.cs.uni-saarland.de/publications/files/herzig-msr-2013.pdf> (read: abstract and intro).

<a id="bird-2009"></a>
- Bird et al. "Fair and Balanced? Bias in Bug-Fix Datasets." ESEC/FSE 2009. <https://www.cs.ucdavis.edu/~filkov/papers/biasbusters.pdf> (abstract via search results; the date-filter claim is as summarized by Herbold et al.).

<a id="bissyande-2013"></a>
- Bissyande et al. "Empirical Evaluation of Bug Linking." CSMR 2013. <https://hal.archives-ouvertes.fr/hal-00807272> (abstract via search results). ReLink figures: <https://cse.hkust.edu.hk/~scc/ReLink.htm>.

<a id="tantithamthavorn-2015"></a>
- Tantithamthavorn, McIntosh, Hassan, Ihara, Matsumoto. "The Impact of Mislabelling on the Performance and Interpretation of Defect Prediction Models." ICSE 2015. <https://swag.uwaterloo.ca/publications/the-impact-of-mislabelling-on-the-performance-and-interpretation-of-defect-prediction-models.html>

<a id="fan-2019"></a>
- Fan, Xia, da Costa, Lo, Hassan, Li. "The Impact of Mislabeled Changes by SZZ on Just-in-Time Defect Prediction." IEEE TSE, 2019. <https://yuanrui-fan.github.io/publication/tse2019> (abstract).

<a id="yatish-2019"></a>
- Yatish, Jiarpakdee, Thongtanunam, Tantithamthavorn. "Mining Software Defects: Should We Consider Affected Releases?" ICSE 2019. <https://2019.icse-conferences.org/details/icse-2019-Technical-Papers/91/Mining-Software-Defects-Should-We-Consider-Affected-Releases-> (abstract).

<a id="rodriguez-2018"></a>
- Rodriguez-Perez, Robles, Gonzalez-Barahona. "Reproducibility and Credibility in Empirical Software Engineering: A Case Study based on a Systematic Literature Review of the use of the SZZ Algorithm." Information and Software Technology 99, 2018. DOI 10.1016/j.infsof.2018.03.009 (bibliographic record only).

<a id="promise-2007"></a>
- Zimmermann, Premraj, Zeller. "Predicting Defects for Eclipse." PROMISE 2007. <https://www.st.cs.uni-saarland.de/publications/details/zimmermann-promise-2007>

<a id="dambros-2010"></a>
- D'Ambros, Lanza, Robbes. "An Extensive Comparison of Bug Prediction Approaches." MSR 2010. <https://www.inf.unibz.it/~rrobbes/p/MSR2010-comparison.pdf> (journal version: EMSE 17, 2012, DOI 10.1007/s10664-011-9173-9).

<a id="kamei-2013"></a>
- Kamei et al. "A Large-Scale Empirical Study of Just-in-Time Quality Assurance." IEEE TSE 39(6), 2013. DOI 10.1109/TSE.2012.70.

<a id="git-blame"></a>
- git-blame documentation. <https://git-scm.com/docs/git-blame>

<a id="github-squash"></a>
- GitHub Docs, "About pull request merges." <https://docs.github.com/en/pull-requests/collaborating-with-pull-requests/incorporating-changes-from-a-pull-request/about-pull-request-merges>

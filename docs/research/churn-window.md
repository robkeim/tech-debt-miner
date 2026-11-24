# Churn window and commit count as churn

Research notes for the heuristic baseline (churn x complexity hotspots). Gathered 2026-11-19 from primary sources where reachable. Anything not verified in a primary source is flagged inline; a later pass checked those items, see "Second-pass checks".

## Question

1. Is there a research-backed basis for the churn window (12 months, 6 months, release-based) used in churn x complexity / hotspot analysis and defect prediction?
2. Which primary sources support commit count (revisions) as the churn measure?

## Short answer

- **No source establishes a scientifically optimal calendar window.** I found no study that sweeps window length for a static churn count and reports a best value. Window choices in the literature are conventions, design choices, or fixed by the data (release boundaries).
- What the sources actually use:
  - Graves et al.: a 2-year history, with older changes down-weighted by about 50% per year (fitted).
  - Nagappan and Ball: the interval between two releases (Windows Server 2003 to its Service Pack 1).
  - Hassan: 6 months for a "recently modified files" set, justified by "belief and experience"; 3 months in his earlier work; 1 month to 1 year given as example period sizes.
  - Tornhill: two to three months for logical coupling in high-activity teams (not hotspot churn); I could not verify a hotspot churn window in a primary source.
  - Kamei et al.: all revisions in the project history, with a stated caveat that project characteristics may change over time.
  - Longitudinal JIT studies: performance decays after about a year; recent data matters; 3 months to retrain, 6+ months of history for stability (McIntosh and Kamei, abstract only).
- Release-based windows are the dominant design in defect-prediction benchmarks (Moser, D'Ambros, Madeyski), but there the window is a consequence of the prediction target (defects per release), not a tuned parameter.
- Defensible position: pick one fixed window, state it as a convention with a stated rationale, pre-register it, and report sensitivity. Do not claim it is empirically optimal.
- Commit count (number of revisions) as a churn measure is well supported as a predictor, but the evidence is mixed on whether it adds value over lines-based churn or in cross-project settings (see below).

## Findings per source

### Tornhill: Your Code as a Crime Scene and code-maat

- Code-maat README: `revisions` is an analysis; `--min-revs` defaults to 5 ("Minimum number of revisions to include an entity in the analysis"); `--temporal-period` treats all commits in the same day as one logical commit; the analysis window is controlled outside the tool via `git log --after=<date>` (README wording is "the last date of interest", which is confusing since `--after` sets a start bound). The README states no recommended window. <https://github.com/adamtornhill/code-maat>
- Tornhill, "Code as a Crime Scene" (ACCU Overload 117, 2013) <https://accu.org/journals/overload/21/117/tornhill_1835>: from a fetched summary of the article, "a temporal window of two or three months is a good heuristic" applies to logical (temporal) coupling when developer activity is high, not to hotspot churn. It also drops modules with too few revisions to avoid skew, and says thresholds and period depend on context and usually need tuning. It cites Nagappan et al. [Nagappan08] for metrics "known to serve as good predictors of defects", but per the summary that citation is organizational-structure work, not change frequency or churn. I verified this only through a page summary, not by reading the full article text.
- Tornhill, "Find Problem Spots With Forensic Methods" (DZone guide, hosted copy) <https://github.com/Code24World/Code-Quality-and-Software-Agility>: states change frequency is "one of the best predictors of software defects" and reports hotspots as about 4% of one project's code linked to 72% of its defects (an anecdotal single-project figure). No time window specified.
- Book text (Pragmatic Bookshelf, 2015; 2nd ed. 2024): the O'Reilly preview pages (<https://www.oreilly.com/library/view/your-code-as/9781680500813/f_0026.html>, `f_0033.html`) returned HTTP 403, so I could not read the book's time-period guidance. Search-result snippets say the book discusses a "temporal period" for hotspot ranking and code churn as an alternative to change frequency, a later pass confirmed this from the preview, see "Second-pass checks".

### Nagappan and Ball, ICSE 2005, "Use of Relative Code Churn Measures to Predict System Defect Density"

- DOI 10.1145/1062455.1062514; PDF read: <https://www.microsoft.com/en-us/research/wp-content/uploads/2016/02/icse05churn.pdf>.
- Window: churn is measured "between" the baseline Windows Server 2003 release and Windows Server 2003 Service Pack 1, and used to predict defect density in SP1. So the window is release-to-service-pack, set by the release schedule, not a calendar length. The paper gives no justification for a duration.
- Measures: churned LOC, deleted LOC, file count, "Weeks of churn" (cumulative time a file was opened for editing), "Churn count" (the number of changes made to the files comprising a binary between the two versions), and "Files churned", combined into relative measures M1 to M8 (e.g., M8 = lines worked on / churn count).
- Key claim from the abstract: absolute churn measures are poor predictors of defect density; relative measures are highly predictive. This is a point against raw absolute counts as the sole churn signal.
- Limitation stated by the authors: version control records only check-in/check-out, so overlapping edits within one check-out period are invisible to churn measures.

### Graves, Karr, Marron, Siy, "Predicting fault incidence using software change history" (IEEE TSE 26(7), 2000)

- DOI 10.1109/32.859533. I read the Waterloo-hosted copy <https://cs.uwaterloo.ca/~m2nagapp/courses/CS846/1171/papers/graves_tse98.pdf>; file name suggests a 1998 version, and I did not confirm it is identical to the published TSE text.
- Data: a 1.5 million line telephone switching subsystem, 80 modules. Faults counted for bug IMRs opened 1 April 1994 to 31 March 1996 (two years). A second prediction interval, 1 Oct 1994 to 30 Sep 1995, was also used.
- Best model: the "weighted time damp model" sums contributions from all past changes to a module, with large and recent changes weighted more; old changes are downweighted "by a factor of about 50 percent per year" (fitted decay).
- Best generalized linear model: "numbers of changes to the module in the past together with a measure of the module's age". Models using number of changes could not be improved by adding module length, and the paper concludes most complexity metrics are of limited use in this context. This is the strongest primary support for change count as a predictor (and a caution on the complexity half of a churn x complexity product).
- Relevance to window: it is the one source here that fits a time-decay parameter instead of picking a cut-off, which suggests older history matters less but does not vanish. One system, one era; the 50%/year figure should not be transferred as a constant.

### Hassan, ICSE 2009, "Predicting faults using the complexity of code changes"

- DOI 10.1109/ICSE.2009.5070510; PDF read: <https://sailresearch.github.io/sail-website/data/pdfs/ICSE2009_PredictingFaultsUsingTheComplexityOfCodeChanges.pdf>.
- Defines a change period (the paper says, for example, a week or a month) over which a file-change probability distribution and entropy are computed; the file change distribution counts "how many times it was changed during a period" (or modified lines in another variant).
- Period options discussed: time-based (e.g., monthly or bimonthly; "In prior work [15], we chose a 3 month period"), modification-limit-based, and burst-based periods.
- Most explicit window statement found in this research: for "recently modified files" sets "In our experiments we used 6 months. Other values could be used. Our choice of six months as a window originates from our belief and our experience developing large software systems." I.e., the author states the window is experience-based, not empirically derived.
- Evaluation: models built from data in years 2 to 3 of each of six open source projects predict faults in years 4 to 5; the paper reports entropy-based change complexity metrics predicted faults better than prior modifications and prior faults.

### Moser, Pedrycz, Succi, ICSE 2008

- DOI 10.1145/1368088.1368114. Full text was not reachable (ACM returned 403; a mirror returned HTML). I verified only bibliographic data and abstract-level claims through search results: Eclipse CVS change metrics (including code churn, past bugs, refactorings, number of authors, file size and age) outperformed static code attributes. I could not verify the release/window definitions, or the metric names and the exact collection window from the paper itself.
- A later paper that builds on it (Lutz et al., PROMISE 2011, <https://robynlutz.com/publications/promise11.pdf>) is reported in search results to say that number of revisions, maximum changeset and number of authors were consistently strong. Not read in full by me.

### D'Ambros, Lanza, Robbes (MSR 2010; extended in EMSE 2012)

- MSR 2010: DOI 10.1109/MSR.2010.5463279. EMSE 2012: DOI 10.1007/s10664-011-9173-9 (Springer paywalled; the author-site and repository PDF links I tried returned 404/410, so I could not read either paper's text).
- Verified from the dataset page <https://bug.inf.usi.ch/index.php>: systems parsed as biweekly snapshots; 15 process metrics from CVS change logs per class citing Moser et al.; post-release defect counts per class. The page does not state the defect-counting period.
- Search-result summaries (not primary text) say the MSR paper predicts defects from release date to six months later, and that process metrics (Moser) ranked at the top with lower variability. I did not verify either from the papers. I also did not verify how process metrics are windowed (the paper reportedly includes weighted/decayed churn variants).

### Kamei et al., IEEE TSE 39(6), 2013, "A large-scale empirical study of just-in-time quality assurance"

- DOI 10.1109/TSE.2012.70; PDF read: <https://sail.cs.queensu.ca/data/pdfs/TSE_ALarge-ScaleEmpiricalStudyOfJust-in-TimeQualityAssurance.pdf>.
- Change-level (not file-window) prediction. Uses all revisions of each project (4,455 to 98,275 changes). Contrasts with Kim et al., who used 500 or 250 revisions, and states that long collection periods may be harder to model "since the characteristics of the project might be changed over time", while arguing that using all data is "a more realistic evaluation scenario".
- Includes history features with decay-by-age: AGE (days since the file's last change, averaged) and REXP (experience weighted by years since each change). No fixed lookback window for churn.

### Madeyski and Jureczko, Software Quality Journal 23, 2015, "Which process metrics can significantly improve defect prediction models?"

- DOI 10.1007/s11219-014-9241-7; PDF read: <https://madeyski.e-informatyka.pl/download/Madeyski15SQJ.pdf>.
- NR (Number of Revisions) is defined as the number of revisions of a Java class "during development of the investigated release", i.e., release-based. They cite Graves 2000, Moser 2008, Nagappan and Ball 2007, Ostrand and Weyuker and others as having used NR or similar.
- Result: across 34 project versions, adding NR to product-metric models improved results slightly but not significantly at alpha .05 ("the NR metric did not prove to be radically useful"). NDC (number of distinct committers) was the metric they recommend; NML had a small effect. This is the main primary counter-evidence to "commit count adds value" and applies to a product-metrics baseline, not directly to churn x complexity.

### Time-window and release-versus-calendar studies

- McIntosh and Kamei, "Are Fix-Inducing Changes a Moving Target?" (IEEE TSE 44(5), 2018), abstract at <https://rebels.cs.uwaterloo.ca/journalpaper/2017/04/04/are-fix-inducing-changes-a-moving-target.html> (PDF not read): on Qt and OpenStack (37,524 changes), model performance drops considerably about a year after training. Stated recommendations: retrain on recent data (within three months), and use six months or more of history for planning. This concerns JIT models, not file-level churn windows.
- Jahanshahi et al., "Does chronology matter in JIT defect prediction?" (PROMISE 2019), arXiv abstract <https://arxiv.org/abs/2103.03506>: compares recent-only and all-data training; recommends weighting recent changes more if chronology is kept. Abstract only.
- Bangash et al., "On the Time-Based Conclusion Stability of Cross-Project Defect Prediction Models" <https://arxiv.org/pdf/1911.06348v3.pdf> (abstract read): defect predictor performance varies depending on which time period is evaluated.
- Majumder et al., "Revisiting process versus product metrics" <https://arxiv.org/pdf/2008.09569> (text skimmed): uses release-based and JIT validation across 700 GitHub projects (train on releases 1 to R-3, test on the last three). It does not choose a calendar window.
- Yatish, Jiarpakdee, Thongtanunam, Tantithamthavorn, "Mining Software Defects: Should We Consider Affected Releases?" (ICSE 2019), DOI 10.1109/ICSE.2019.00075 (abstract via search result only): the common heuristic of labeling post-release defects by a fixed window after release (typically six months) mislabels data compared with affected-release data. This concerns the outcome window, not the churn window, but it is the most direct evidence that fixed 6-month windows are a convention with measurable error.

## Commit count as churn

Primary support:

- Graves 2000: number of changes (deltas) plus module age was the best generalized linear model; added module length did not improve it. Strongest direct support for a change-count signal over lines.
- Nagappan and Ball 2005 include "churn count" (number of changes) as an input and use it in a ratio (M8), but their headline result is for relative lines-based measures; absolute counts were poor predictors.
- Hassan 2009 builds entropy on per-file change counts (or modified lines) per period.
- Madeyski and Jureczko 2015 list NR as used by Graves, Moser, Nagappan and Ball and others, but find it adds only a statistically non-significant improvement over product metrics in their 34-version study.
- Tornhill treats "number of revisions" as the change-frequency measure in hotspot analysis (code-maat `revisions`; ACCU Overload article). Note that his single cited defect-predictor paper appears to be organizational-structure work, so Tornhill's own prediction claim is thinly sourced in what I could verify.

Caveats:

- Commit count is sensitive to commit style (squash vs many small commits, merge commits, bots, formatting sweeps). Code-maat's `--temporal-period` same-day collapsing is one mitigation. Nagappan and Ball note that overlapping edits within one check-out are invisible.
- Absolute counts correlate with file size; Nagappan and Ball specifically argue for relative measures. A churn x complexity product partly reintroduces size.

## Recommendation: pre-registered fixed window

1. Choose one window, record it in the pre-registration before running any analysis, and describe it as a convention. Suggested default: **12 months of calendar history ending at the analysis snapshot**, measured as revision count per file. Rationale to state honestly: it spans multiple release cycles for most repositories, is long enough for the sparse-history issue that makes short windows noisy, and is within the range where the only fitted decay (Graves, 50%/year) and the longitudinal degradation (about one year, McIntosh and Kamei) suggest older history is still informative but fading. None of these sources states 12 months as optimal.
2. If the repository has release tags, use "since the previous release" as the secondary, release-based definition (matches Nagappan and Ball, Madeyski and Jureczko, Moser). Pre-register which is primary.
3. Pre-register sensitivity analyses rather than a single claim: 3, 6, 12 months, plus all-history, and optionally an exponential decay with a 12-month half-life (Graves-style). Report rank stability (e.g., overlap of top-k hotspots) across windows.
4. Pre-register a minimum-activity filter (code-maat default `--min-revs` is 5) and a rule for collapsing same-day commits.
5. Report relative as well as absolute counts (Nagappan and Ball), and keep the complexity measure separate in the write-up (Graves found length added nothing once change counts were in).

Caveats to state with the result:

- The window is a convention. The literature does not identify an optimum, and the cited 6-month (Hassan), 2 to 3 month (Tornhill, coupling), 3 month retraining and 6+ month history (McIntosh and Kamei) values answer different questions.
- Evidence comes mostly from defect prediction (predicting future defects), not from technical-debt or hotspot prioritization; transfer to the latter is an assumption.
- Studies are heterogeneous (telephony switching, Windows, Eclipse, Apache); effect sizes will not transfer.
- Release cadence varies widely, so release-based windows are not comparable across repositories.

## Second-pass checks

A second pass checked the items this note first left unverified. It was done in a separate chat and read secondary pages and previews as well as papers, so treat it as a check, not a full re-read. The inline text above predates it where they differ.

Confirmed:

- **Nagappan08 (cited by Tornhill):** the organizational-structure paper (Nagappan, Murphy and Basili, "The influence of organizational structure on software quality", ICSE 2008, pp. 521-530), not a churn paper.
- **Graves:** the Waterloo PDF header reads IEEE TSE 26(7), July 2000, so it is the published version. The 1998 NISS report (TR80) gives the same numbers: the two-year window, the fitted decay of about 50% per year, and number of changes plus age as the best GLM, with module length adding nothing.
- **Kim et al.:** Kamei et al. section 6.3 says Kim et al. used 500 or 250 revisions per project. The paper is Kim, Whitehead and Zhang, "Classifying Software Changes: Clean or Buggy?", IEEE TSE 34(2), 2008. Kim's paper itself was not opened.
- **D'Ambros et al. (EMSE 2012 preprint):** confirms a six-month post-release defect window and that the process metrics are the Moser set. NR is the count of revisions; the decay variants apply to churn of source-code metrics, not to NR. Snapshots are taken every two weeks. MOSER had the best average AUC rank, but the top groups were not significantly separable. The MSR 2010 version was not checked separately.
- **McIntosh and Kamei:** the lab page confirms performance drops about a year after training, retraining within 3 months and 6+ months of history. TSE 44(5), 412-428, 2018. Full text not read.
- **Yatish et al.:** ICSE 2019, pp. 654-665. The fixed six-month post-release window heuristic has a large impact on the datasets and on classification models, but minimal impact on defect-count models. Trautsch et al. (EMSE 2021, arXiv 1911.08938) report that six months combined with SZZ yields about one false defective label per correct one, and misses two.
- **Tornhill:** the ACCU article's "two or three months" applies to logical coupling and gives no hotspot window. The O'Reilly preview shows the book ranks hotspots by revisions in "the specified temporal period" with relative rank, and covers code churn (absolute vs. relative) as an alternative to change frequency. No hotspot window value was found, and the book is paywalled.

Corrected:

- **Moser et al. 2008:** the paper does not state a six-month window. It uses the Zimmermann PROMISE data for Eclipse 2.0, 2.1 and 3.0 (post-release, file-level defects) with 18 change metrics, including REVISIONS, REFACTORINGS, BUGFIXES, AUTHORS, LOC_ADDED/DELETED, CODECHURN, CHANGESET, AGE and WEIGHTED_AGE. AGE is measured in weeks back from the release date. Whether the six months comes from the Zimmermann data is unchecked, and the text came from a summarizer over a SciSpace copy.
- **Jahanshahi et al.:** PROMISE 2019, pp. 90-99. It contradicts McIntosh and Kamei: predictive power does not significantly decline over time, and all-data models beat short-period models. It still recommends weighted sampling of recent data, mainly for calibration. Read through a summarizer of the arXiv version.

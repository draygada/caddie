# Textbook techniques that could improve the model

Ranked by payoff per hour for this project. Each names the chapter, where it plugs in, and what it buys. None are in the MVP; pick from the top after M1d.

## Tier 1: cheap and clearly worth it

**1. Bayesian shrinkage of the dispersion fit (Ch 4.2).** 50 shots per club is thin for the tail. Put a prior on each club's parameters from Broadie and Ko's skill bands (sigma_theta ~ N(7, 2) deg for a 100-shooter, p ~ Beta(2, 18)) and report the posterior mean instead of the MLE. Plugs into `dispersion.py` as an alternative to `fit_club`. Buys: parameters that do not swing on one bad session, and a clean story for "what happens with 10 shots vs 50 vs 100". Two hours.

**2. Asynchronous value iteration, Gauss-Seidel from the green backward (Ch 7.6).** A hole is nearly one-directional, so updating cells in decreasing-y order in place propagates values from the green in one sweep instead of many. Plugs into `value_iteration.py` as `sweep_order`. Buys: 2 to 4x fewer sweeps, which matters once you bootstrap 50 times. One hour.

**3. Robustness and trade analysis figures (Ch 14.3, 14.4).** Already planned for the bootstrap; add a trade-off plot of expected strokes vs P(blow-up) across the three policies and the three penalty modes. Plugs into `evaluate.py`. Buys: a figure that answers "safer or lower-scoring" directly. One hour.

## Tier 2: moderate work, strong demo value

**4. Risk-sensitive objective (Ch 6.1, 6.2, utility theory).** Expected strokes is one utility. Two alternatives: exponential utility `U = -exp(lambda * strokes)` with lambda > 0 (penalizes blow-ups), and a goal objective "maximize P(score <= par)" which needs strokes-so-far in the state (multiply the state space by ~8). Plugs into `value_iteration.py` as an objective switch. Buys: visibly different policies on hole 11 (go for it vs lay up), the best possible demo moment, and a direct use of chapter 6. Half a day for exponential utility, a day for the goal version.

**5. Rare-event estimation of blow-up probability (Ch 14.2).** P(par + 3 or worse) from 2,000 plain simulations has few samples in the tail. Importance-sample the mishit mixture (raise p during simulation, reweight by the likelihood ratio) to estimate the tail accurately. Plugs into `evaluate.py`. Buys: tight error bars on the number the report will quote. Half a day.

**6. Value of information on more shots (Ch 6.6).** Given the bootstrap, the expected improvement in strokes from collecting 50 more swings per club is computable: solve with the posterior at n shots, at 2n, compare expected strokes under the true-ish model. Plugs into `evaluate.py`. Buys: a quantitative answer to "was 50 shots enough", which the TAs will ask. Half a day once item 1 exists.

## Tier 3: upgrades to the online step

**7. Sparse sampling at depth 2 (Ch 9.4).** The current online step is depth 1 with the grid value at the leaf. Depth 2 with m = 10 at each level costs 700 x 10 x 700 x 10 evaluations, too many; restrict the second level to the grid policy's action and you get a cheap depth-2 check that catches cases where the 5 m grid misleads near hazards. Plugs into `online.py` and `rollout.ts`. Buys: slightly better recommendations at polygon edges, more chapter 9 material. One day including the TS port.

**8. MCTS with progressive widening (Ch 9.6).** Continuous aim direction instead of 2 degree steps, UCB1 over clubs, progressive widening over directions. Plugs into `online.py` as an alternative recommender. Buys: a comparison figure (grid policy vs rollout vs MCTS, strokes and compute time), which is a nice "approach justification" exhibit. One to two days; TS port optional.

## Tier 4: interesting but likely out of scope

**9. Cross-entropy method for an interpretable caddie rule (Ch 10.4).** Parametrize a simple policy (aim offset from pin as a linear function of distance and hazard proximity, club by a carry margin), optimize the few parameters with CEM by simulation. Buys: a human-readable rule to compare against the full DP, answering "how much of the gain comes from two simple heuristics". One day.

**10. On-course posterior updating (Ch 4.2 online, toward Ch 16 Bayes-adaptive MDP).** Treat each on-course shot's start and end fix as an observation and update the club's parameters between shots. The full Bayes-adaptive version is beyond chapter 15; the practical version is item 1 run incrementally and a re-solve overnight. Buys: the "learns as you play" line from the proposal. Two days, and GPS error makes the observations noisy.

**11. Wind as a POMDP (Ch 19 to 20, not yet covered).** Hidden wind state, noisy observation from a forecast, belief update. Proposal mentions it as a stretch. Recommend keeping it as fixed scenarios (calm, moderate) via a carry multiplier instead.

## What I would actually add, in order

1, 2, 3 during M1d (they cost half a day together and improve the report's robustness section). Then 4 (exponential utility) before the video, because the risk-averse vs risk-neutral policy contrast on hole 11 is the single most convincing 20 seconds of footage you can film. Items 7 or 8 only if the online step ends up in the video and you want a compute-vs-quality figure.
